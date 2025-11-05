# -*- coding: utf-8 -*-
import sqlite3, os, glob, json,re
from pathlib import Path
from typing import List, Dict, Any

CANDIDATE_KEYS = ["text", "content", "paragraph", "chunk", "body", "abstract"]



def _extract_text_from_json(obj):
    if isinstance(obj, dict):
        for k in CANDIDATE_KEYS:
            if k in obj and isinstance(obj[k], str):
                return obj[k]
        # 兜底：拼接所有字符串字段
        parts = []
        for v in obj.values():
            if isinstance(v, str):
                parts.append(v)
        return "\n".join(parts)
    return ""

def build_index(data_dir: str):
    p = Path(data_dir)
    db = p / "rag_fts5.db"
    p.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db)); c = conn.cursor()
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(path, content)")
    try:
        c.execute("DELETE FROM docs")
    except Exception:
        pass

    # 1) 先吃纯文本
    txt_pattern = str(p / "paragraphs" / "*.txt")
    for txt in glob.glob(txt_pattern):
        with open(txt, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        c.execute("INSERT INTO docs(path, content) VALUES(?,?)", (txt, content))

    # 2) 再吃 JSONL：逐行解析，抽取文本
    jsonl_pattern = str(p / "paragraphs" / "*.jsonl")
    for jf in glob.glob(jsonl_pattern):
        with open(jf, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                text = _extract_text_from_json(obj)
                if not text:
                    continue
                # 每行当作一个“虚拟文档”，path 上附加行号，便于定位
                virtual_path = f"{jf}#L{i+1}"
                c.execute("INSERT INTO docs(path, content) VALUES(?,?)", (virtual_path, text))

    conn.commit(); conn.close()
    return str(db)

def _normalize_query(q: str) -> str:
    """
    把用户自然语言问题转成 FTS5 友好查询：
    - 去掉会破坏 MATCH 语法的符号（? " ' ( ) | : - 等）
    - 仅保留中文/英文/数字，按词切分
    - 用前缀匹配：token* token* ...
    """
    # 全角转半角 + 小写
    q = q.strip().lower()
    # 只保留“字母/数字/汉字”，其它变空格
    q = re.sub(r"[^\w\u4e00-\u9fff]+", " ", q)
    tokens = [t for t in q.split() if t]
    if not tokens:
        return ""
    # FTS5 前缀匹配（注意：过短的 token 可不加 *，按需调整阈值）
    parts = []
    for t in tokens:
        if len(t) >= 2:
            parts.append(f'{t}*')
        else:
            parts.append(t)
    return " ".join(parts)


def search(db_path: str, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
    """
    返回统一结构：[{ 'text': str, 'score': float, 'meta': {...} }, ...]
    你可以把表名/字段名改为你现有的：比如 paragraphs(content TEXT, path TEXT, ...)
    """
    norm = _normalize_query(query)
    if not norm:
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        # ✅ 参数绑定，避免引号/问号破坏语法；rank 使用 bm25 或 fts5 的 rank 函数按你的库来
        sql = """
        SELECT
            content as text,
            path    as source,
            bm25(paragraphs) as score
        FROM paragraphs
        WHERE paragraphs MATCH ?
        ORDER BY score
        LIMIT ?
        """
        cur.execute(sql, (norm, top_k))
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                "text": r["text"] or "",
                "score": float(r["score"]) if r["score"] is not None else 0.0,
                "meta": {"source": r["source"]},
            })
        return out
    finally:
        conn.close()