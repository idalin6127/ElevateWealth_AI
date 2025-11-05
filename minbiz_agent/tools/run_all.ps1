# 在项目根运行： .\tools\run_all.ps1
$env:PYTHONPATH = (Get-Location).Path

# 1) 段落化（可跳过，如果你直接从 fulltext_clean 开始）
python -m src.ingest.paragraphize --in data/fulltext --out data/paragraphs --max-para-chars 800 --pause-threshold 1.3 --merge-short 12

# 2) 清洗 + 去重
pip install simhash langdetect -q
python -m src.ingest.clean_fulltext --in data/paragraphs --out data/fulltext_clean --min_chars 8 --hamming_thresh 2 --bucket_bits 14

# 3) 脱敏 + 分块
python -m src.ingest.pipeline --transcripts data/fulltext_clean

# 4) 索引（BM25）
pip install rank-bm25 -q
python -m src.index.build_index --mode bm25

# 5) 验证检索
python -m src.app.cli --q "首周交付SOP怎么做？"

Write-Host "All done."
