# -*- coding: utf-8 -*-
import os, json, glob, argparse

def merge_jsonl(pattern: str, out_path: str):
    files = sorted(glob.glob(pattern))
    n = 0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as w:
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        w.write(line)
                        n += 1
    print(f"[merge] {n} rows -> {out_path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", required=True, help="data/chunks/*.jsonl")
    ap.add_argument("--out", required=True, help="data/chunks/all.jsonl")
    args = ap.parse_args()
    merge_jsonl(args.pattern, args.out)
