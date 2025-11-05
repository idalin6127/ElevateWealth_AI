# src/utils/text_utils.py
import re

_SENT_SPLIT = re.compile(r"(?<=[。！？!?])\s+|[\r\n]+")

def normalize_text(s: str) -> str:
    """基础清洗：去 BOM、统一空白、去重复空格"""
    if not s:
        return ""
    s = s.replace("\ufeff", "")       # BOM
    s = s.replace("\t", " ")
    s = re.sub(r"[ \xa0]+", " ", s)   # 连续空格
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n\s+", "\n", s)
    s = s.strip()
    return s

def greedy_sentence_chunk(
    text: str, max_chars: int = 900, overlap: int = 120
):
    """
    句子级贪心切块：尽量贴近 max_chars；块与块之间保留 overlap 字符重叠
    """
    if not text:
        return []

    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    chunks, cur = [], ""

    for s in sents:
        if not cur:
            cur = s
            continue
        if len(cur) + 1 + len(s) <= max_chars:
            cur = f"{cur}\n{s}"
        else:
            chunks.append(cur)
            # 做 overlap
            if overlap > 0 and len(cur) > overlap:
                cur_tail = cur[-overlap:]
                cur = f"{cur_tail}\n{s}"
            else:
                cur = s

    if cur:
        chunks.append(cur)

    # 极端长句兜底再切
    out = []
    for c in chunks:
        if len(c) <= max_chars:
            out.append(c)
        else:
            for i in range(0, len(c), max_chars):
                out.append(c[i:i+max_chars])
    return out
