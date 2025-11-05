# -*- coding: utf-8 -*-
"""
将 data/fulltext/*.word 文件批量转换为 jsonl（每段一行），用于 RAG 构建。
"""
import os, json
from pathlib import Path

def word_to_jsonl(src_dir="data/fulltext", out_dir="data/fulltext"):
    src = Path(src_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    
    for f in src.glob("*.word"):
        try:
            # 读取纯文本文件
            with open(f, "r", encoding="utf-8") as file:
                content = file.read()
        except Exception as e:
            print(f"[skip] {f.name} 无法读取：{e}")
            continue

        # 按段落分割，忽略空行
        paras = [p.strip() for p in content.split('\n') if p.strip()]
        print(f"[convert] {f.name}: {len(paras)} 段")

        out_path = out / f"{f.stem}.jsonl"
        with open(out_path, "w", encoding="utf-8") as fout:
            for i, t in enumerate(paras):
                data = {
                    "id": f"{f.stem}-{i:03d}",
                    "start": None,
                    "end": None,
                    "text": t,
                    "source_file": f.name
                }
                fout.write(json.dumps(data, ensure_ascii=False) + "\n")

        print(f"[save] -> {out_path}")

if __name__ == "__main__":
    word_to_jsonl()
