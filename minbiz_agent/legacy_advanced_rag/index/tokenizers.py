# src/index/tokenizers.py
# -*- coding: utf-8 -*-
import re
try:
    import jieba
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False

CJK_PTN = re.compile(r'[\u4e00-\u9fff]')

def is_cjk(s: str) -> bool:
    return bool(CJK_PTN.search(s))

def tokenize_jieba_bigram(s: str):
    tokens = []
    if _HAS_JIEBA:
        for seg in jieba.cut(s, cut_all=False):
            seg = seg.strip()
            if not seg:
                continue
            tokens.append(seg)
            if is_cjk(seg) and len(seg) >= 2:
                tokens.extend([seg[i:i+2] for i in range(len(seg) - 1)])
    else:
        # 退化：按字切 + bigram
        s = re.sub(r"\s+", "", s)
        for ch in s:
            tokens.append(ch)
        tokens.extend([s[i:i+2] for i in range(len(s) - 1)])
    return tokens
