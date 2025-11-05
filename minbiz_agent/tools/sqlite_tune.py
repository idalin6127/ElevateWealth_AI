# tools/sqlite_tune.py
import os, sqlite3

DB = os.getenv("MINBIZ_DB", "data/minbiz.db")  # 和你项目里一致
os.makedirs(os.path.dirname(DB), exist_ok=True)

con = sqlite3.connect(DB)
cur = con.cursor()

# —— 调优参数（一次性设置即可）——
cur.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=30000000000;  -- ~28GB 映射，有多少内存就用多少（不足会自动降级）
""")
con.commit()

# 打印验证
for p in ("journal_mode","synchronous","temp_store","mmap_size"):
    v = cur.execute(f"PRAGMA {p};").fetchone()[0]
    print(f"{p} = {v}")

con.close()
print("SQLite PRAGMA tuning done.")
