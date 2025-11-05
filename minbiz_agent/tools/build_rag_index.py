# -*- coding: utf-8 -*-
from pathlib import Path
from src.rag.sqlite_fts import build_index
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
print("Building RAG index on", DATA_DIR)
print(build_index(str(DATA_DIR)))