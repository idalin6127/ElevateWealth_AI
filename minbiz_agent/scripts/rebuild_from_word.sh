#!/usr/bin/env bash
set -euo pipefail

echo "=== 1. 转换 Word -> JSONL ==="
python -m src.ingest.convert_word_to_jsonl

echo "=== 2. 清洗 fulltext -> fulltext_clean ==="
python -m src.ingest.batch_clean --in_dir data/fulltext --out_dir data/fulltext_clean

echo "=== 3. 切块 ==="
python -m src.ingest.batch_chunk --in_dir data/fulltext_clean --out_dir data/chunks --max_chars 800 --overlap_chars 120

echo "=== 4. 重建索引 ==="
python -m src.index.build_index --mode hybrid --model intfloat/multilingual-e5-base

echo "✅ 全部完成！索引已基于新的 Word 讲稿版本。"
