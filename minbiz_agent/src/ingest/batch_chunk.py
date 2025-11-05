# src/ingest/batch_chunk.py
# -*- coding: utf-8 -*-
import os, json, argparse, glob
from pathlib import Path
from typing import List, Dict

from .pipeline import PipelineConfig, process_document  # 复用你现有的切块逻辑

def read_clean_jsonl(fp: str) -> List[Dict]:
    """读取清洗后的 jsonl，返回每行 dict。"""
    rows = []
    with open(fp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows

def merge_text(rows: List[Dict]) -> str:
    """把清洗后的多行合并为一段文本；尽量使用 'text' 字段。"""
    parts = []
    for r in rows:
        t = r.get("text") or r.get("clean") or r.get("content") or ""
        if t:
            parts.append(t.strip())
    return "\n".join([p for p in parts if p])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir",  required=True, help="清洗后目录，例如 data/fulltext_clean")
    ap.add_argument("--out_dir", required=True, help="切块输出目录，例如 data/chunks")
    ap.add_argument("--max_chars", type=int, default=800)
    ap.add_argument("--overlap_chars", type=int, default=120)
    ap.add_argument("--opencc", default=None, help="如需再做繁简转换可传 t2s/s2t，否则留空")
    args = ap.parse_args()

    in_dir  = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(str(in_dir / "*.jsonl")))
    if not files:
        print(f"[batch_chunk] 未发现文件：{in_dir}/*.jsonl")
        return

    cfg = PipelineConfig(
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
        opencc=args.opencc if (args.opencc and args.opencc.lower()!="none") else None
    )

    total_chunks = 0
    for fp in files:
        base_id = Path(fp).stem.replace(".clean", "")  # 兼容 xxx.clean.jsonl/xxx.jsonl
        rows = read_clean_jsonl(fp)
        raw_text = merge_text(rows)
        if not raw_text.strip():
            print(f"[batch_chunk] 跳过（空文本）：{fp}")
            continue

        chunks = process_document(base_id=base_id, raw_text=raw_text, cfg=cfg)
        out_fp = out_dir / f"{base_id}.chunks.jsonl"
        with open(out_fp, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        total_chunks += len(chunks)
        print(f"[batch_chunk] {fp} -> {out_fp}  ({len(chunks)} chunks)")

    print(f"[batch_chunk] 完成，共生成 {total_chunks} 个 chunks 到 {out_dir}")

if __name__ == "__main__":
    main()
