# tools/paragraphs_to_chunks.py
# 非官方，仅应急使用，优先使用ingest/batch_chunk.py
# 读取 data/paragraphs/*.jsonl （每行 {"cid","src","text"}）
# 合并相邻段落生成 data/chunks/<base>.chunks.jsonl （每行 {"chunk_id","src","text"}）
# 规则：按字符窗口滑动拼块，控制长度与重叠；保持 chunk_id 稳定可追踪。

import os, json, glob, re
from pathlib import Path
import argparse

PARA_DIR = Path("data/paragraphs")
CHUNK_DIR = Path("data/chunks")

def normalize(t: str) -> str:
    t = t.replace("\r\n","\n").replace("\r","\n")
    t = re.sub(r"[ \t]+"," ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def sliding_chunk(paras, min_chars=400, max_chars=1200, overlap=120):
    """
    paras: list[str] 已按顺序的段落文本
    产出：list[str] 每条为一个 chunk 文本
    """
    buf = ""
    out = []
    for p in paras:
        if not p: continue
        if buf:
            buf = (buf + " " + p).strip()
        else:
            buf = p
        # 如果超过 max，上一次就产出，并将末尾 overlap 作为下一块开头
        if len(buf) >= max_chars:
            out.append(buf[:max_chars])
            # 构造下一块的起点（重叠 overlap）
            tail = buf[max(0, len(buf)-overlap):]
            buf = tail
        else:
            # 未超 max 但足够长则产出
            if len(buf) >= min_chars:
                out.append(buf)
                buf = ""
    if buf and len(buf) >= max(100, min_chars//2):
        out.append(buf[:max_chars])
    return out

def load_paragraphs(jsonl_path: Path):
    paras = []
    with open(jsonl_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            text = obj.get("text") or ""
            text = normalize(text)
            if text:
                paras.append(text)
    return paras

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--para_dir", default=str(PARA_DIR))
    ap.add_argument("--out_dir",  default=str(CHUNK_DIR))
    ap.add_argument("--min_chars", type=int, default=400)
    ap.add_argument("--max_chars", type=int, default=1200)
    ap.add_argument("--overlap",   type=int, default=120)
    args = ap.parse_args()

    para_dir = Path(args.para_dir)
    out_dir  = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(str(para_dir / "*.jsonl")))
    if not files:
        print(f"[ERR] 未在 {para_dir} 找到 *.jsonl；请先生成 data/paragraphs/*.jsonl")
        return

    total_chunks = 0
    for fp in files:
        fp = Path(fp)
        base = fp.stem  # e.g., mydoc  -> 输出 mydoc.chunks.jsonl
        paras = load_paragraphs(fp)
        chunks = sliding_chunk(paras, args.min_chars, args.max_chars, args.overlap)
        out_path = out_dir / f"{base}.chunks.jsonl"
        with open(out_path, "w", encoding="utf-8") as w:
            for i, ch in enumerate(chunks, 1):
                chunk_id = f"{base}-ck{i:04d}"
                w.write(json.dumps({"chunk_id": chunk_id, "src": base + ".jsonl", "text": ch}, ensure_ascii=False) + "\n")
        total_chunks += len(chunks)
        print(f"[OK] {fp.name} → {out_path}  chunks={len(chunks)}")
    print(f"[DONE] 输出目录：{out_dir}  总计 chunks={total_chunks}")

if __name__ == "__main__":
    main()
