# -*- coding: utf-8 -*-
import os, json, glob
from pathlib import Path

SRC = Path("data/paragraphs")
DST = Path("data/paragraphs")
DST.mkdir(parents=True, exist_ok=True)

# 按常见字段提取文本；找不到就拼接所有字符串字段
CANDIDATE_KEYS = ["text", "content", "paragraph", "chunk", "body"]

def extract_text(obj):
    if isinstance(obj, dict):
        for k in CANDIDATE_KEYS:
            if k in obj and isinstance(obj[k], str):
                return obj[k]
        # 兜底：把所有字符串字段拼起来
        parts = []
        for v in obj.values():
            if isinstance(v, str):
                parts.append(v)
        return "\n".join(parts)
    return ""

for fp in glob.glob(str(SRC / "*.jsonl")):
    name = Path(fp).stem  # 不带后缀
    out = DST / f"{name}.txt"
    lines = []
    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            text = extract_text(obj)
            if text:
                lines.append(text)
    with open(out, "w", encoding="utf-8") as w:
        w.write("\n\n".join(lines))
    print("Wrote:", out)
print("Done.")
