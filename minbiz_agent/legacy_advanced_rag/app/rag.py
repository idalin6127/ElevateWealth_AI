# src/app/rag.py
# -*- coding: utf-8 -*-
"""
RAG 工具函数：命中去重、摘要/短引、安全上下文拼接、引用结构化。
严禁在此文件 import 检索器或 server，避免循环依赖。
"""

from typing import List, Dict, Tuple
import hashlib, re

def _hash(s: str) -> str:
    import hashlib as _h
    return _h.sha1(s.encode("utf-8")).hexdigest()

def _safe_snippet(text: str, max_chars: int) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) > max_chars:
        t = t[:max_chars].rstrip() + "…"
    return t

def _paraphrase_bullets(snippet: str, max_len: int = 180) -> str:
    sents = [s for s in re.split(r'[。！!？?；;]', snippet) if s.strip()]
    bullets = []
    for s in sents[:3]:
        s = s.strip()
        s = re.sub(r'\b(比如說|就是|OK|好嗎|其實|那麼)\b', '', s)
        if s:
            bullets.append("· " + s)
    out = " ".join(bullets)
    return out[:max_len] + ("…" if len(out) > max_len else "")

def build_context_for_query_secure(
    hits,
    display_mode: str = "summary",         # summary | snippet | none
    max_chars_per_snippet: int = 90,
    max_total_quote_chars: int = 300,
    per_ctx_blocks: int = 6
) -> Tuple[str, List[Dict]]:
    """
    输入：检索器 search() 返回的 hits（对象需含 h.text/h.chunk_id/...）
    输出：(context_text, refs)
    - 默认“summary”摘要，合规安全；“snippet”仅短引，限额。
    """
    total_quote = 0
    seen = set()
    ctx_lines = []
    refs: List[Dict] = []

    def _get(obj, name, default=None):
        return getattr(obj, name, default) if hasattr(obj, name) else obj.get(name, default)

    for h in list(hits)[:per_ctx_blocks]:
        raw = _get(h, "text", "") or _get(h, "chunk", "") or ""
        if not raw.strip():
            continue
        hkey = _hash(raw[:120])
        if hkey in seen:
            continue
        seen.add(hkey)

        snippet = _safe_snippet(raw, max_chars_per_snippet)
        chunk_id = _get(h, "chunk_id", None)
        source_file = _get(h, "source_file", None) or _get(h, "source", None)
        section_title = _get(h, "section_title", None)
        start = _get(h, "start", None)
        end = _get(h, "end", None)

        label = f"[{chunk_id} | {section_title} | {start}s–{end}s]"

        if display_mode == "none":
            ctx_lines.append(label)
        elif display_mode == "summary":
            safe_text = _paraphrase_bullets(snippet)
            ctx_lines.append(f"{label}\n{safe_text} （摘要）")
        else:  # "snippet"
            if total_quote + len(snippet) > max_total_quote_chars:
                ctx_lines.append(label + "（引文已达上限）")
            else:
                ctx_lines.append(f"{label}\n{snippet}")
                total_quote += len(snippet)

        refs.append({
            "chunk_id": chunk_id,
            "file": source_file,
            "title": section_title,
            "start_s": start,
            "end_s": end
        })

    context_text = "\n\n".join(ctx_lines)
    return context_text, refs
