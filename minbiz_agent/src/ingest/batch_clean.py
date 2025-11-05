# -*- coding: utf-8 -*-
"""
Batch-clean jsonl files in a directory.
Usage:
  python -m src.ingest.batch_clean --in_dir data/fulltext --out_dir data/fulltext_clean
"""
import os, json, argparse, pathlib
from typing import Dict

# 这里假定 clean_fulltext.py 里提供了 clean_text(text: str) -> str
# 如果函数名不同，按你文件里的实际函数名改一下即可
from src.ingest.clean_fulltext import normalize_text as clean_text

def process_file(in_path: pathlib.Path, out_path: pathlib.Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                obj: Dict = json.loads(line)
            except Exception:
                continue
            txt = obj.get("text") or obj.get("content") or ""
            txt = clean_text(txt)  # 调你现有的清洗规则
            obj["text"] = txt
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir",  required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()

    in_dir  = pathlib.Path(args.in_dir)
    out_dir = pathlib.Path(args.out_dir)
    files = sorted(in_dir.rglob("*.jsonl"))
    print(f"[batch_clean] {len(files)} files from {in_dir} -> {out_dir}")
    total = 0
    for fp in files:
        rel = fp.relative_to(in_dir)
        out_fp = out_dir / rel
        cnt = process_file(fp, out_fp)
        print(f"  cleaned {rel}  ({cnt} lines)")
        total += cnt
    print(f"[batch_clean] done. total lines: {total}")

if __name__ == "__main__":
    main()
