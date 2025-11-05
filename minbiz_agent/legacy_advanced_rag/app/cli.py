# src/app/cli.py
import argparse, yaml
from pathlib import Path
from src.index.retriever import BM25Retriever, FaissRetriever, HybridRetriever, INDEX_DIR

def load_config():
    fp=Path("config.yaml")
    return yaml.safe_load(open(fp,"r",encoding="utf-8")) if fp.exists() else {"app":{"retrieval_mode":"bm25"}}

def make_retriever(mode:str):
    mode=(mode or "bm25").lower()
    if mode=="bm25": return BM25Retriever(INDEX_DIR)
    if mode=="faiss": return FaissRetriever(INDEX_DIR)
    if mode=="hybrid":
        bm25=BM25Retriever(INDEX_DIR); faiss=FaissRetriever(INDEX_DIR)
        return HybridRetriever(bm25, faiss, k_pool=50)
    raise ValueError("unknown mode")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--q",required=True); ap.add_argument("--k",type=int,default=10)
    args=ap.parse_args()
    cfg=load_config(); r=make_retriever(cfg.get("app",{}).get("retrieval_mode","bm25"))
    hits=r.search(args.q,k=args.k)
    for i,h in enumerate(hits,1):
        m=h.get("meta",{})
        print(f"{i:02d}. [{h.get('source')}] id={h['id']} score={h['score']:.4f} file={m.get('source_file')} t={m.get('start')}-{m.get('end')}")
        if "text" in h: print("    ", h["text"][:160].replace("\n"," "))
if __name__=="__main__": main()
