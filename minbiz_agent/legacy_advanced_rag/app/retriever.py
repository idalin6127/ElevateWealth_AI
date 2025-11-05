# src/app/retriever.py
# 极简可运行检索器：按文件分块后做关键词匹配计分

from pathlib import Path
from typing import List
import re

class Hit:
    def __init__(self, text, score, source_file, chunk_id, section_title=None, start=0.0, end=0.0):
        self.text = text
        self.score = score
        self.source_file = source_file
        self.chunk_id = chunk_id
        self.section_title = section_title or Path(source_file).stem
        self.start = start
        self.end = end

class HybridSearcher:
    def __init__(self, index_dir: str, exts=(".md", ".txt"), chunk_size=500, chunk_overlap=50):
        self.index_dir = Path(index_dir)
        self.docs = []  # [(source_file, chunk_text)]
        if not self.index_dir.exists():
            print(f"[DummySearcher] index_dir not found: {self.index_dir.resolve()}")
            return
        files = [p for p in self.index_dir.rglob("*") if p.suffix.lower() in exts]
        for f in files:
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                txt = f.read_text(errors="ignore")
            chunks = []
            i = 0
            while i < len(txt):
                chunks.append(txt[i:i+chunk_size])
                i += max(1, chunk_size - chunk_overlap)
            for j, ch in enumerate(chunks):
                self.docs.append((str(f), ch, j))
        print(f"[DummySearcher] loaded chunks: {len(self.docs)} from {self.index_dir.resolve()}")

    def search(self, query: str, top_k: int = 8) -> List[Hit]:
        """
        简易中文友好检索：
        - 先做粗分词（字母/数字/中文）
        - 对每个中文串再生成 2~6 字 n-gram 作为关键词
        - 命中规则：只要 chunk 文本包含任一关键词即可计分（出现次数之和）
        """
        if not self.docs or not query.strip():
            return []

        # 把中文/英文/数字都提取出来
        raw_tokens = re.findall(r"[\w\u4e00-\u9fa5]+", query)
        keywords = set()

        for tok in raw_tokens:
            tok = tok.lower().strip()
            if not tok:
                continue
            # 加入原 token
            keywords.add(tok)
            # 若是中文串，生成 2~6 字 n-gram
            if re.search(r"[\u4e00-\u9fa5]", tok):
                s = tok
                n_min, n_max = 2, min(8, len(s))
                for n in range(n_min, n_max + 1):
                    for i in range(0, len(s) - n + 1):
                        keywords.add(s[i:i+n])

        # 过滤太短的片段，降低误匹配
        keywords = {k for k in keywords if len(k) >= 2}

        hits: List[Hit] = []
        for src, chunk, cid in self.docs:
            t = (chunk or "").lower()
            score = 0.0
            for kw in keywords:
                if kw in t:
                    # 出现次数加权
                    score += t.count(kw)
            if score >= 2:
                hits.append(Hit(text=chunk, score=float(score), source_file=src, chunk_id=cid))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

