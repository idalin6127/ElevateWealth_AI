
# src/ingest/pipeline.py
# -*- coding: utf-8 -*-
import os, re, json, hashlib
from dataclasses import dataclass
from typing import List, Dict, Iterable, Optional

# 可选：繁简转换
try:
    from opencc import OpenCC
    _HAS_OPENCC = True
except Exception:
    _HAS_OPENCC = False

# 可选：关键词抽取
try:
    import jieba, jieba.analyse
    _HAS_JIEBA = True
except Exception:
    _HAS_JIEBA = False

# —— 句末分割 + 标点扩展
SENT_PTN = re.compile(r'(?<=[。！？!?；;…])\s*')

def split_to_sentences(text: str) -> List[str]:
    text = text.replace("\u3000", " ").replace("\t", " ").strip()
    text = re.sub(r"[ ]{2,}", " ", text)
    sents = [s.strip() for s in SENT_PTN.split(text) if s.strip()]
    out = []
    for s in sents:
        # 极端长句再按逗号切
        if len(s) > 600:
            out.extend([ss.strip() for ss in re.split(r'[，,、]', s) if ss.strip()])
        else:
            out.append(s)
    return out

def chunk_by_sentences(text: str, max_chars: int, overlap_chars: int) -> List[str]:
    sents = split_to_sentences(text)
    chunks, buf = [], ""
    for s in sents:
        if not buf:
            buf = s
            continue
        if len(buf) + 1 + len(s) <= max_chars:
            buf += " " + s
        else:
            chunks.append(buf)
            overlap = buf[-overlap_chars:] if overlap_chars > 0 else ""
            buf = (overlap + " " + s).strip()
    if buf:
        chunks.append(buf)
    return chunks

def load_typo_map(path: str) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def apply_typos(s: str, typo_map: Dict[str, str]) -> str:
    for k, v in typo_map.items():
        s = s.replace(k, v)
    return s

def maybe_convert_chinese(s: str, mode: Optional[str]) -> str:
    if not mode or not _HAS_OPENCC:
        return s
    cc = OpenCC(mode)  # "t2s"/"s2t"
    return cc.convert(s)

def simple_title(s: str) -> str:
    first = s.split('。')[0].strip() if '。' in s else s[:28]
    return first[:28]

def simple_summary(s: str) -> List[str]:
    sents = split_to_sentences(s)
    if not sents:
        return [s[:40]]
    if len(sents) == 1:
        return [sents[0][:60]]
    return [sents[0][:60], sents[1][:60]]

def extract_keywords(s: str, topk: int = 6) -> List[str]:
    if not _HAS_JIEBA:
        s = re.sub(r'\s+', '', s)
        # 简单去重
        uniq = []
        for ch in s:
            if ch not in uniq:
                uniq.append(ch)
        return uniq[:topk]
    kws = jieba.analyse.extract_tags(s, topK=topk)
    return [k for k in kws if len(k.strip()) >= 1]

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

@dataclass
class PipelineConfig:
    max_chars: int = 800
    overlap_chars: int = 120
    opencc: Optional[str] = "t2s"   # "t2s"/"s2t"/None
    typo_fix: bool = True
    typo_map_path: str = "src/filters/typo_map.json"
    add_summary: bool = True
    add_keywords: bool = True
    language: str = "zh-Hans"
    version: str = "v2-clean"

def process_document(
    base_id: str,
    raw_text: str,
    start_s: float = None,
    end_s: float = None,
    cfg: PipelineConfig = PipelineConfig()
) -> List[Dict]:
    """长文本 -> 多个 chunk（带重叠与元数据）"""
    typo_map = load_typo_map(cfg.typo_map_path) if cfg.typo_fix else {}
    clean = raw_text
    if cfg.typo_fix:
        clean = apply_typos(clean, typo_map)
    if cfg.opencc:
        clean = maybe_convert_chinese(clean, cfg.opencc)

    pieces = chunk_by_sentences(clean, cfg.max_chars, cfg.overlap_chars)
    out = []
    for i, piece in enumerate(pieces):
        title = simple_title(piece) if cfg.add_summary else ""
        summ = simple_summary(piece) if cfg.add_summary else []
        kws  = extract_keywords(piece) if cfg.add_keywords else []
        out.append({
            "chunk_id": f"{base_id}-{i:04d}",
            "source_file": base_id,
            "text_raw": raw_text if i == 0 else None,
            "text": piece,
            "start": start_s,
            "end": end_s,
            "overlap_prev": cfg.overlap_chars if i > 0 else 0,
            "language": cfg.language,
            "section_title": title,
            "summary": summ,
            "keywords": kws,
            "char_count": len(piece),
            "hash": sha1(piece),
            "pii_redacted": True,
            "version": cfg.version
        })
    return out

def write_jsonl(path: str, rows: Iterable[Dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# CLI
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_txt", required=True)
    ap.add_argument("--base_id", required=True)
    ap.add_argument("--out_jsonl", required=True)
    ap.add_argument("--opencc", default="t2s")
    ap.add_argument("--max_chars", type=int, default=800)
    ap.add_argument("--overlap_chars", type=int, default=120)
    args = ap.parse_args()

    with open(args.in_txt, "r", encoding="utf-8") as f:
        raw = f.read()

    cfg = PipelineConfig(
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
        opencc=(args.opencc if args.opencc.lower() != "none" else None)
    )
    rows = process_document(args.base_id, raw, start_s=None, end_s=None, cfg=cfg)
    write_jsonl(args.out_jsonl, rows)
    print(f"Wrote {len(rows)} chunks -> {args.out_jsonl}")
