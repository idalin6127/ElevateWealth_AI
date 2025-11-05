# src/index/retriever.py
# -*- coding: utf-8 -*-
import os, json, pickle, sys
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

from src.index.tokenizers import tokenize_jieba_bigram

@dataclass
class Hit:
    id: str
    text: str
    score: float
    chunk_id: str
    source_file: str
    section_title: str
    start: float
    end: float

def rrf_fuse(bm25_hits: List[Hit], vec_hits: List[Hit], k: int = 60) -> List[Tuple[Hit, float]]:
    scores = {}
    bucket = {}
    for rank, h in enumerate(bm25_hits):
        s = 1.0 / (k + rank + 1)
        scores[h.id] = scores.get(h.id, 0.0) + s
        bucket[h.id] = h
    for rank, h in enumerate(vec_hits):
        s = 1.0 / (k + rank + 1)
        scores[h.id] = scores.get(h.id, 0.0) + s
        bucket[h.id] = h
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(bucket[_id], sc) for _id, sc in fused]

def _safe_import_transformers():
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        return AutoTokenizer, AutoModelForSequenceClassification, torch
    except Exception:
        return None, None, None

class CrossEncoderReranker:
    def __init__(self, name: str = "mixedbread-ai/mxbai-rerank-xsmall-v1", device: str = None):
        AutoTokenizer, AutoModel, torch = _safe_import_transformers()
        if AutoTokenizer is None:
            raise RuntimeError("transformers/torch 未安装，无法启用交叉重排")
        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = AutoModel.from_pretrained(name)
        self.model.eval()
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    def score(self, query: str, passages: List[str]) -> List[float]:
        with self.torch.no_grad():
            pairs = [(query, p) for p in passages]
            inputs = self.tok.batch_encode_plus(
                pairs, padding=True, truncation=True, max_length=512, return_tensors='pt'
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            logits = self.model(**inputs).logits.squeeze(-1)
            return logits.detach().cpu().tolist()

def rerank(query: str, hits: List[Hit], top_k: int = 50, final_k: int = 10) -> List[Hit]:
    if not hits:
        return []
    cand = hits[:top_k]
    try:
        rr = CrossEncoderReranker()
        scores = rr.score(query, [h.text for h in cand])
        ordering = sorted(zip(cand, scores), key=lambda x: x[1], reverse=True)
        return [h for h, _ in ordering[:final_k]]
    except Exception as e:
        print(f"[retriever] rerank disabled: {type(e).__name__}: {e}", file=sys.stderr)
        return cand[:final_k]

class HybridSearcher:
    def __init__(self, index_dir: str, encoder_name: str = "intfloat/multilingual-e5-base"):
        self.index_dir = index_dir
        # BM25 包（我们保存的是 tokens/texts，需要重建 BM25Okapi）
        with open(os.path.join(index_dir, "bm25.pkl"), "rb") as f:
            pack = pickle.load(f)
        self.doc_ids = pack["doc_ids"]
        self.texts   = pack["texts"]
        self.tokens  = pack["tokens"]
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi(self.tokens)
        with open(os.path.join(index_dir, "meta.json"), "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        # 向量索引（可选）
        self.vec_ok = False
        try:
            import faiss
            self.faiss = faiss
            self.faiss_index = faiss.read_index(os.path.join(index_dir, "faiss.index"))
            with open(os.path.join(index_dir, "faiss_meta.json"), "r", encoding="utf-8") as f:
                self.faiss_meta = json.load(f)
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(encoder_name)
            self.vec_ok = True
        except Exception as e:
            print(f"[retriever] vector search disabled: {type(e).__name__}: {e}", file=sys.stderr)
            self.faiss_index = None
            self.faiss_meta = None
            self.model = None

    def _bm25_search(self, query: str, topk: int = 50) -> List[Hit]:
        q_tokens = tokenize_jieba_bigram(query)
        scores = self.bm25.get_scores(q_tokens)
        idx = np.argsort(scores)[::-1][:topk]
        hits = []
        for i in idx:
            m = self.meta[i]
            hits.append(Hit(
                id=str(i),
                text=self.texts[i],
                score=float(scores[i]),
                chunk_id=m.get("id") or m.get("chunk_id") or self.doc_ids[i],
                source_file=m.get("source_file") or "",
                section_title=m.get("section_title") or "",
                start=m.get("start") or 0.0,
                end=m.get("end") or 0.0
            ))
        return hits

    def _faiss_search(self, query: str, topk: int = 50) -> List[Hit]:
        if not self.vec_ok:
            return []
        q = [f"query: {query}"]
        q_emb = self.model.encode(q, normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        D, I = self.faiss_index.search(q_emb, topk)
        hits = []
        for score, idx in zip(D[0], I[0]):
            m = self.faiss_meta["meta_map"][ self.faiss_meta["doc_ids"][idx] ]
            text = self.texts[idx]
            hits.append(Hit(
                id=str(int(idx)),
                text=text,
                score=float(score),
                chunk_id=self.faiss_meta["doc_ids"][idx],
                source_file=m.get("source_file") or "",
                section_title=m.get("section_title") or "",
                start=m.get("start") or 0.0,
                end=m.get("end") or 0.0
            ))
        return hits

    def search(self, query: str, bm25_k: int = 50, faiss_k: int = 50,
               rrf_k: int = 60, use_rerank: bool = True, final_k: int = 10) -> List[Hit]:
        bm25_hits = self._bm25_search(query, topk=bm25_k)
        vec_hits  = self._faiss_search(query, topk=faiss_k) if self.vec_ok else []
        fused_hits = [h for (h, _) in rrf_fuse(bm25_hits, vec_hits, k=rrf_k)] if vec_hits else bm25_hits
        if use_rerank and fused_hits:
            return rerank(query, fused_hits, top_k=min(50, len(fused_hits)), final_k=final_k)
        return fused_hits[:final_k]

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--index_dir", required=True)
    ap.add_argument("--q", required=True)
    ap.add_argument("--encoder", default="intfloat/multilingual-e5-base")
    ap.add_argument("--no_rerank", action="store_true")
    args = ap.parse_args()

    hs = HybridSearcher(args.index_dir, encoder_name=args.encoder)
    hits = hs.search(args.q, use_rerank=not args.no_rerank, final_k=5)
    for i, h in enumerate(hits, 1):
        snippet = (h.text or "").replace("\n", " ")
        if len(snippet) > 90: snippet = snippet[:90] + "…"
        print(f"{i}. [{h.chunk_id}] {h.section_title} ({h.start:.1f}-{h.end:.1f}s) score={h.score:.4f}")
        print(snippet)
        print("-"*80)
