# -*- coding: utf-8 -*-
import os, sqlite3, re
from typing import Any, Dict, List, Tuple
from contextlib import closing, suppress


# ---- OpenAI client ----
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_client = OpenAI(api_key=OPENAI_API_KEY)  # 注意：全局单例，供下方 _gen_answer_llm 使用

# =========================
# 基础：RAG 检索（容错封装）
# =========================
def _table_exists(conn, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None


def _split_terms(q: str) -> list[str]:
    # 取中文、英文数字，去掉标点，按连续块切开
    terms = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", q)
    # 过滤过短项（比如“的”“了”），中文保留长度>=2的片段；英数长度>=2
    out = []
    for t in terms:
        if re.search(r"[\u4e00-\u9fff]", t):
            if len(t) >= 2:
                out.append(t)
        else:
            if len(t) >= 2:
                out.append(t.lower())
    # 去重，保序
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq

def rag_search(db_path: str, q: str, limit: int = 6):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # 1) 先试 FTS MATCH（成功就直接用）
        rows = []
        try:
            cur.execute(
                "SELECT text, source, section_title, chunk_id, 1.0 AS score "
                "FROM paragraphs WHERE paragraphs MATCH ? LIMIT ?;",
                (q, limit)
            )
            rows = cur.fetchall()
        except Exception as e:
            print("[RAG] FTS MATCH error ->", e)

        # 2) 如果 MATCH 为空，做中文友好的 LIKE 回退
        if not rows:
            terms = _split_terms(q)
            # 如果没有有效词，就退回整个 q，但一般不会发生
            if not terms:
                terms = [q]

            # 拼接 WHERE: text LIKE ? OR text LIKE ? ...
            where = " OR ".join(["text LIKE ?"] * len(terms))
            params = [f"%{t}%" for t in terms]

            cur.execute(
                f"SELECT text, source, section_title, chunk_id "
                f"FROM paragraphs WHERE {where} LIMIT 200;",
                params
            )
            cand = cur.fetchall()

            # 计算一个简单得分：命中词个数（越多越靠前）
            scored = []
            for r in cand:
                txt = (r["text"] or "")
                s = 0
                for t in terms:
                    if t in txt:
                        s += 1
                if s > 0:
                    scored.append((s, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            rows = [r for _, r in scored[:limit]]

            # 把 rows 变成有 score 的结构
            tmp = []
            for s, r in scored[:limit]:
                tmp.append({
                    "text": r["text"],
                    "source": r["source"],
                    "section_title": r["section_title"],
                    "chunk_id": r["chunk_id"],
                    "score": float(s),   # 命中词个数作为分数
                })
            if tmp:
                # 统一返回 dict 列表
                return tmp

        # 3) 统一规范化返回
        hits = []
        for r in rows:
            # rows 可能来自 MATCH（Row，含 score=1.0）或上面的 tmp（已是 dict）
            if isinstance(r, dict):
                hits.append({
                    "text": r.get("text", ""),
                    "score": float(r.get("score", 0.0)),
                    "meta": {
                        "source": r.get("source"),
                        "section_title": r.get("section_title"),
                        "chunk_id": r.get("chunk_id"),
                    },
                })
            else:
                hits.append({
                    "text": r["text"],
                    "score": float(r["score"] if "score" in r.keys() else 1.0),
                    "meta": {
                        "source": r["source"],
                        "section_title": r["section_title"],
                        "chunk_id": r["chunk_id"],
                    },
                })
        return hits
    finally:
        conn.close()

# ---------- RAG 拼接 ----------
def _build_context(db_path: str, query: str, top_k: int = 6):
    """
    检索 -> 生成 rag_ctx 和 evidence
    """
    hits = rag_search(db_path, query, limit=top_k)  # 统一用 limit
    # 直接把 hits 里的字段映射到 evidence
    ev = []
    for h in (hits or []):
        meta = h.get("meta") or {}
        ev.append({
            "score": float(h.get("score", 0.0)),
            "source": meta.get("source"),
            "preview": (h.get("text") or "")[:200],
            "chunk_id": meta.get("chunk_id"),
            "title": meta.get("section_title"),
        })
    # 上下文拼成一段（也可用段落列表拼接）
    rag_ctx = "\n".join((h.get("text") or "") for h in (hits or []))
    return rag_ctx, ev




def _normalize_hits(hits: Any) -> List[Dict[str, Any]]:
    """把检索结果统一成 [{'text','score','meta':{...}}]"""
    if not hits:
        return []
    out: List[Dict[str, Any]] = []
    for h in hits:
        if isinstance(h, dict):
            text  = h.get("text", "")
            score = float(h.get("score", 0.0) or 0.0)
            meta  = h.get("meta", {})
        else:
            # 兜底：未知结构
            text, score, meta = str(h), 0.0, {}
        out.append({"text": text, "score": score, "meta": meta})
    return out


# =========================
# LLM 生成
# =========================
def _gen_answer_llm(question: str, lang: str, rag_ctx: str) -> str:
    """
    使用你喜欢的英文 prompt（加入中英标题逻辑），并用上方 _client。
    """
    # 标题常量（中英）
    if lang == "en":
        T1, T2, T3 = "Summary", "Three Actions", "Risks & Next steps"
    else:
        T1, T2, T3 = "总结", "三步行动", "风险与下一步"

    tag = "English" if lang == "en" else "Chinese"

    prompt = (
        "You are MinBiz, a startup consultant. Always ground your answer in the PROVIDED CONTEXT first. "
        "If something is not in the context, add it as short general tips.\n"
        f"Write in {tag}. Style: friendly, vivid, example-driven, short sentences, bullet points.\n\n"
        "User question:\n"
        f"{question}\n\n"
        f"{rag_ctx if rag_ctx else '(no context)'}\n\n"
        "Please output in the following sections:\n"
        f"1) {T1}\n"
        f"2) {T2} (with mini examples)\n"
        f"3) {T3}\n"
    )

    # 系统提示：中英自动
    if lang == "en":
        sys = "You are a startup coach. Always answer in clear, lively English."
    elif lang == "zh":
        sys = "你是一名创业教练。请始终用简洁活泼的中文回答。"
    else:
        sys = "You are a startup coach. Detect the user's language (Chinese or English) and answer in the same language."

    try:
        completion = _client.chat.completions.create(
            model=os.getenv("MINBIZ_OPENAI_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        print("[LLM] error ->", e)
        return "Sorry, I had trouble generating the answer. Please try again."

# =========================
# 画像 / 记忆（可选）
# =========================
def load_facts(session: str) -> Dict[str, str]:
    # 你的实现；没有也没关系
    return {}

def add_turn(session: str, role: str, content: str) -> None:
    # 你的实现；没有也没关系
    pass

# =========================
# 对外主函数
# =========================
def answer(session: str, query: str, db_path: str, debug: bool = False, lang: str = "auto") -> Dict[str, Any]:
    """
    返回：
      {"text": "...", "evidence": [...]}  // 仅在 debug=True 时包含 evidence
    """
    text: str = ""  # 防止异常时 UnboundLocalError

    # 1) 读取画像（不强依赖）
    with suppress(Exception):
        _ = load_facts(session)

    # 2) RAG
    rag_ctx, ev = _build_context(db_path, query, top_k=6)

    # 3) LLM
    # 简单判断语言：检测中文字符
    if lang == "auto":
        lang = "zh" if re.search(r"[\u4e00-\u9fff]", query) else "en"
    text = _gen_answer_llm(query, lang, rag_ctx)

    # 4) 记录轮次（忽略错误）
    with suppress(Exception):
        add_turn(session, "user", query)
        add_turn(session, "assistant", text)

    out: Dict[str, Any] = {"text": text}
    if debug:
        out["evidence"] = ev
    return out
