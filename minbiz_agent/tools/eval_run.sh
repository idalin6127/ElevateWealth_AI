#!/usr/bin/env bash
set -e
MODE=${1:-hybrid}      # bm25 | faiss | hybrid
CASE=${2:-A}          # A | B

# 切换到对应的 A/B 产物到默认目录
rm -f data/index/* 2>/dev/null || true
rm -f data/chunks/*.chunks.jsonl 2>/dev/null || true
cp -f data/index_${CASE}/* data/index/ 2>/dev/null || true
cp -f data/chunks_${CASE}/*.chunks.jsonl data/chunks/

LOG="eval/logs/result_${MODE}_${CASE}.txt"
: > "$LOG"

while IFS= read -r q; do
  [ -z "$q" ] && continue
  echo ">>> Q: $q" | tee -a "$LOG"
  python -m src.app.cli --q "$q" --k 10 --mode $MODE 2>/dev/null | tee -a "$LOG"
  echo | tee -a "$LOG"
done < eval/queries.txt

echo "Saved -> $LOG"
