# 运行：
# # 先看下权限和换行
# ls -l tools/clean_all.sh
# file tools/clean_all.sh   # 若显示 CRLF，用下一步转码

# # 若是 Windows 换行，转成 Unix 换行
# sed -i 's/\r$//' tools/clean_all.sh   # 或：dos2unix tools/clean_all.sh

# # 直接用 bash 运行（绕过 noexec）
# bash tools/clean_all.sh

# 之后你想逐步收紧，就把脚本顶部参数改为：
# MIN_CHARS=6 或 8
# HAMMING=2
# 去掉 EXTRA="--no_persistent_near_dup"（去掉前先删 _simhash_buckets.pkl）


#!/usr/bin/env bash
set -e

IN_DIR="data/paragraphs"
OUT_DIR="data/fulltext_clean"

# 清空旧输出 & 近重复状态
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.jsonl "$OUT_DIR"/_simhash_buckets.pkl

# 宽松参数起步（与你单文件成功的一致）
MIN_CHARS=3
MAX_CHARS=10000
HAMMING=1
BUCKET_BITS=16
EXTRA="--no_persistent_near_dup"

for f in "$IN_DIR"/*.jsonl; do
  d=/tmp/one; rm -rf "$d" && mkdir -p "$d"
  cp "$f" "$d"/
  python -m src.ingest.clean_fulltext \
    --in "$d" --out "$OUT_DIR" \
    --min_chars $MIN_CHARS --max_chars $MAX_CHARS \
    --hamming_thresh $HAMMING --bucket_bits $BUCKET_BITS \
    $EXTRA
done

# 汇总统计
for f in "$OUT_DIR"/*.jsonl; do echo -n "$(basename "$f"): "; wc -l < "$f"; done | sort | tail -n 20
