# -*- coding: utf-8 -*-
"""Session memory (SQLite) for user facts & conversation turns."""
import sqlite3, json, time, os
from pathlib import Path
import hashlib, json, time, sqlite3, os
DB_PATH = os.getenv("MINBIZ_DB", "data/minbiz.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA mmap_size=30000000000;")
    return con

def _ensure_cache_table(con):
    con.execute("""
    CREATE TABLE IF NOT EXISTS cache (
      k TEXT PRIMARY KEY,
      v TEXT NOT NULL,
      ts INTEGER NOT NULL
    )""")

def cache_get(session: str, query: str, ttl_sec: int = 3600):
    k = hashlib.sha1(f"{session}|{query}".encode("utf-8")).hexdigest()
    con = _conn(); _ensure_cache_table(con)
    row = con.execute("SELECT v, ts FROM cache WHERE k=?", (k,)).fetchone()
    con.close()
    if not row: return None
    v, ts = row
    if time.time() - ts > ttl_sec: return None
    try: return json.loads(v)   # 约定为 {"text":..., "evidence":[...]}
    except: return None

def cache_set(session: str, query: str, payload: dict):
    k = hashlib.sha1(f"{session}|{query}".encode("utf-8")).hexdigest()
    con = _conn(); _ensure_cache_table(con)
    con.execute("INSERT OR REPLACE INTO cache(k,v,ts) VALUES(?,?,?)",
                (k, json.dumps(payload, ensure_ascii=False), int(time.time())))
    con.commit(); con.close()

def cache_invalidate_session(session: str):
    # 当你写入画像/事实时可调用，避免旧缓存影响
    prefix = hashlib.sha1(f"{session}|".encode("utf-8")).hexdigest()[:8]  # 简单做法：全表删更直接
    con = _conn(); _ensure_cache_table(con)
    con.execute("DELETE FROM cache")   # 简化：全清；如需细粒度可建二级索引存 session
    con.commit(); con.close()

DB_PATH = os.environ.get(
    "MINBIZ_DB",
    str(Path(__file__).resolve().parents[2] / "data" / "minbiz.db")
)

def _ensure():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS facts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session TEXT, key TEXT, value TEXT, ts REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS turns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session TEXT, role TEXT, content TEXT, ts REAL
    )""")
    conn.commit(); conn.close()

def save_fact(session: str, key: str, value: str):
    _ensure()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO facts(session,key,value,ts) VALUES(?,?,?,?)",
              (session, key, value, time.time()))
    conn.commit(); conn.close()
    cache_invalidate_session(session)

def load_facts(session: str):
    _ensure()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    rows = c.execute(
        "SELECT key,value FROM facts WHERE session=? ORDER BY ts DESC",
        (session,)
    ).fetchall()
    conn.close()
    out = {}
    for k, v in rows:
        out.setdefault(k, v)
    return out

def add_turn(session: str, role: str, content: str):
    _ensure()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO turns(session,role,content,ts) VALUES(?,?,?,?)",
              (session, role, content, time.time()))
    conn.commit(); conn.close()

def last_k_turns(session: str, k: int = 6):
    _ensure()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    rows = c.execute(
        "SELECT role,content FROM turns WHERE session=? ORDER BY id DESC LIMIT ?",
        (session, k)
    ).fetchall()
    conn.close()
    rows.reverse()
    return rows
