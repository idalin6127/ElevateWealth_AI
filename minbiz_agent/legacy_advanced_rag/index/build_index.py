# src/index/build_index.py
# -*- coding: utf-8 -*-
"""
构建检索索引（兼容 pipeline_light 期望的工件）：
- 输入：data/chunks/*.chunks.jsonl
- 输出（保持向后兼容 + 新增运行时工件）：
  1) 你现有的：
     - data/index/bm25.pkl           # 仍保存分词后的 tokens（向后兼容）
     - data/index/meta.json
     - data/index/faiss.index
     - data/index/faiss_meta.json
  2) 新增（供 pipeline_light 直接加载）：
     - data/index/ids.npy            # 对齐 faiss 的顺序 id 列表
     - data/index/bm25.runtime.pkl.gz（= 直接序列化好的 BM25Okapi + ids + texts）
     - data/index/bm25.pkl.gz        # 同上，名称兼容（两份指向同样内容）
用法：
  python -m src.index.build_index --mode bm25
  python -m src.index.build_index --mode faiss --model intfloat/multilingual-e5-base
  python -m src.index.build_index --mode hybrid --model intfloat/multilingual-e5-base
  python -m src.index.build_index --mode faiss --incremental
"""
import argparse, glob, json, os, pickle, re, sys, gzip
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np

INDEX_DIR = Path("data/index")
CHUNKS_DIR = Path("data/chunks")
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# —— 统一分词器（与你检索端一致）——
from src.index.tokenizers import tokenize_jieba_bigram

# --------- utils ----------
def read_chunks() -> List[Dict]:
    files = sorted(glob.glob(str(CHUNKS_DIR / "*.chunks.jsonl")))
    out = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    d["text"] = d.get("text", d.get("chunk", "")) or ""
                    d["id"] = d.get("id") or d.get("chunk_id") or f"{d.get('source_file','?')}::{d.get('start',0)}"
                    out.append(d)
                except Exception:
                    continue
    return out

def save_json(obj, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --------- BM25 build ----------
def build_bm25():
    try:
        from rank_bm25 import BM25Okapi  # 必须安装：pip install rank-bm25
    except Exception:
        print("[build_index] 需要安装 rank-bm25：pip install rank-bm25", file=sys.stderr)
        sys.exit(1)

    docs = read_chunks()
    if not docs:
        print("[build_index] 未发现 chunks 文件，先运行 ingest pipeline 生成 *.chunks.jsonl")
        return

    doc_ids = [d["id"] for d in docs]
    texts   = [d["text"] for d in docs]

    # —— 用与你检索端一致的中文分词器 —— 
    tokens = [tokenize_jieba_bigram(t) for t in texts]

    # 1) 保持你的旧格式（仅保存 tokens），向后兼容
    obj_tokens = {
        "doc_ids": doc_ids,
        "texts": texts,
        "tokens": tokens,
        "tokenizer": "jieba_bigram"
    }
    with open(INDEX_DIR / "bm25.pkl", "wb") as f:
        pickle.dump(obj_tokens, f)
    print(f"[build_index] 写入 tokens -> {INDEX_DIR/'bm25.pkl'} （向后兼容）")

    # 2) 新增：直接序列化 BM25Okapi，供 pipeline_light 即时加载
    bm25 = BM25Okapi(tokens)
    rt_pack = {"bm25": bm25, "ids": doc_ids, "texts": texts}
    for name in ["bm25.runtime.pkl.gz", "bm25.pkl.gz"]:
        with gzip.open(INDEX_DIR / name, "wb") as f:
            pickle.dump(rt_pack, f)
        print(f"[build_index] 写入运行时 BM25 -> {INDEX_DIR/name}")

    # 3) meta.json（可视化/调试）
    meta = [{
        "id": d["id"],
        "source_file": d.get("source_file"),
        "start": d.get("start"),
        "end": d.get("end"),
        "section_title": d.get("section_title")
    } for d in docs]
    save_json(meta, INDEX_DIR / "meta.json")
    print(f"[build_index] meta.json -> {INDEX_DIR/'meta.json'}")

# --------- FAISS build ----------
def faiss_available():
    try:
        import faiss  # noqa
        return True
    except Exception as e:
        print(f"[build_index] faiss import failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False

def load_sentence_encoder(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except Exception:
        print("[build_index] 需要安装 sentence-transformers：pip install sentence-transformers", file=sys.stderr)
        sys.exit(1)

def build_faiss(model_name: str, incremental: bool=False):
    """
    e5/m3e 风格：
    - 文档侧加前缀 "passage: "
    - encode(..., normalize_embeddings=True)
    - FAISS: IndexFlatIP
    - 额外输出 ids.npy（按 FAISS 顺序存放 chunk_id）
    """
    if not faiss_available():
        print("[build_index] 未检测到 faiss-cpu；请先安装：pip install faiss-cpu", file=sys.stderr)
        sys.exit(1)
    import faiss

    docs = read_chunks()
    if not docs:
        print("[build_index] 未发现 chunks 文件，先运行 ingest pipeline。")
        return

    doc_ids = [d["id"] for d in docs]
    texts   = [d["text"] for d in docs]
    meta_map = {d["id"]: {
        "source_file": d.get("source_file"),
        "start": d.get("start"),
        "end": d.get("end"),
        "section_title": d.get("section_title")
    } for d in docs}

    enc = load_sentence_encoder(model_name)
    dim = enc.get_sentence_embedding_dimension()

    index_path = INDEX_DIR / "faiss.index"
    meta_path  = INDEX_DIR / "faiss_meta.json"
    ids_path   = INDEX_DIR / "ids.npy"

    # —— 增量：只编码新增文档 —— 
    if incremental and index_path.exists() and meta_path.exists() and ids_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            old = json.load(f)
        old_ids_set = set(old["doc_ids"])
        need_ids, need_texts = [], []
        for i, did in enumerate(doc_ids):
            if did not in old_ids_set:
                need_ids.append(did)
                need_texts.append(texts[i])

        if not need_ids:
            print("[build_index] FAISS 增量：没有新增文档。")
            return

        print(f"[build_index] FAISS 增量新增 {len(need_ids)} 条，编码中…")
        enc_texts = [f"passage: {t}" for t in need_texts]
        X = enc.encode(enc_texts, batch_size=128, show_progress_bar=True,
                       convert_to_numpy=True, normalize_embeddings=True).astype("float32")

        index = faiss.read_index(str(index_path))
        index.add(X)
        faiss.write_index(index, str(index_path))

        # 同步 ids.npy
        ids_old = np.load(ids_path, allow_pickle=True).tolist()
        ids_new = ids_old + need_ids
        np.save(ids_path, np.array(ids_new, dtype=object))

        # faiss_meta
        old["doc_ids"] = ids_new
        old["dim"]   = dim
        old["model"] = model_name
        old["meta_map"].update({k: meta_map[k] for k in need_ids})
        save_json(old, meta_path)

        print(f"[build_index] FAISS 增量完成 -> {index_path}")
        return

    # —— 全量重建 —— 
    print(f"[build_index] FAISS 全量：编码 {len(texts)} 条（{model_name}）…")
    enc_texts = [f"passage: {t}" for t in texts]
    X = enc.encode(enc_texts, batch_size=128, show_progress_bar=True,
                   convert_to_numpy=True, normalize_embeddings=True).astype("float32")

    import faiss
    index = faiss.IndexFlatIP(dim)
    index.add(X)
    faiss.write_index(index, str(index_path))

    # ids.npy（供推理端按下标反查 chunk_id）
    np.save(ids_path, np.array(doc_ids, dtype=object))

    faiss_meta = {
        "doc_ids": doc_ids,
        "dim": dim,
        "model": model_name,
        "normalize": True,
        "index_metric": "ip",
        "meta_map": meta_map
    }
    save_json(faiss_meta, meta_path)
    print(f"[build_index] FAISS 索引完成 -> {index_path}, ids.npy")

# --------- CLI ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bm25","faiss","hybrid"], default="bm25")
    ap.add_argument("--model", default="intfloat/multilingual-e5-base", help="sentence-transformers 模型名（FAISS 用）")
    ap.add_argument("--incremental", action="store_true", help="FAISS 增量模式")
    args = ap.parse_args()

    if args.mode in ("bm25", "hybrid"):
        build_bm25()
    if args.mode in ("faiss", "hybrid"):
        build_faiss(args.model, incremental=args.incremental)

if __name__ == "__main__":
    main()
