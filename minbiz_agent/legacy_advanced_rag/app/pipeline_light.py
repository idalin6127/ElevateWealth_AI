# src/app/pipeline_light.py
# -*- coding: utf-8 -*-
import os, json, gzip, pickle, re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

from openai import OpenAI
_oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# === ADD START: Multi-query expansion ===
def _expand_queries_with_llm(q: str, n: int = 3, model: str | None = None) -> list[str]:
    """
    用 OpenAI 生成互补问句，增加召回覆盖面。
    返回: [原问题, 改写1, 改写2, ...]
    """
    from openai import OpenAI
    import json, os
    m = model or os.getenv("MINBIZ_OAI_QUERY_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = (
        "请为下面的问题生成3个不同角度的改写问句，覆盖同义和上下位表达。"
        "只输出JSON数组（字符串数组），不要解释。\n问题：" + q
    )
    try:
        resp = client.chat.completions.create(
            model=m,
            messages=[
                {"role": "system", "content": "你是检索提示词改写器，只输出JSON数组。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        txt = resp.choices[0].message.content.strip()
        arr = json.loads(txt) if txt.startswith("[") else []
    except Exception:
        arr = []
    out = [q] + [x for x in arr if isinstance(x, str)]
    # 去重
    seen, dedup = set(), []
    for s in out:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup[: (n + 1)]
# === ADD END ===


# === ADD START: Lite Cross-Encoder Reranker ===
class _LiteReranker:
    """
    轻量交叉重排器（CrossEncoder）。默认模型：BAAI/bge-reranker-base
    在A100上延迟可接受；若环境缺依赖，可通过环境变量 MINBIZ_RERANK=0 关闭。
    """
    def __init__(self, name: str | None = None, device: str | None = None):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.name = name or os.getenv("MINBIZ_RERANK_MODEL", "BAAI/bge-reranker-base")
        self.tok = AutoTokenizer.from_pretrained(self.name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.name)
        self.model.eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.torch = torch

    def score(self, query: str, passages: list[str]) -> list[float]:
        with self.torch.no_grad():
            pairs = [(query, p if isinstance(p, str) else "") for p in passages]
            inputs = self.tok.batch_encode_plus(
                pairs, padding=True, truncation=True, max_length=512, return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            logits = self.model(**inputs).logits.squeeze(-1)
            return logits.detach().cpu().tolist()
# === ADD END ===



# ============ Types ============
@dataclass
class Hit:
    chunk_id: str
    text: str
    score: float
    doc_title: str | None = None
    source_file: str | None = None

    def model_dump(self):  # 兼容 pydantic-like
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "score": float(self.score),
            "doc_title": self.doc_title,
            "source_file": self.source_file,
        }

@dataclass
class EvidencePack:
    hits: List[Hit]

# 兼容 voice_agent 的类型签名
@dataclass
class Refined:
    draft: str
    background: str
    def model_dump_json(self):  # voice_agent 会调用
        return json.dumps({"draft": self.draft, "background": self.background}, ensure_ascii=False)

# ============ Hybrid Searcher ============
# in src/app/pipeline_light.py
import gzip, pickle
from src.index.tokenizers import tokenize_jieba_bigram  # 与索引一致

class HybridSearcher:
    def __init__(self, index_dir: str, encoder_name: str, normalize: bool = True):
        self.index_dir = index_dir
        self.encoder_name = encoder_name
        self.normalize = normalize

        # Encoder
        self.model = SentenceTransformer(encoder_name)

        # FAISS
        self.faiss = faiss.read_index(os.path.join(index_dir, "faiss.index"))
        ids_npy = os.path.join(index_dir, "ids.npy")
        if os.path.exists(ids_npy):
            self.ids = np.load(ids_npy, allow_pickle=True).tolist()
        else:
            # 兼容老格式
            meta_path = os.path.join(index_dir, "faiss_meta.json")
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.ids = meta["doc_ids"]

        # BM25：优先加载运行时工件（已构建好的 BM25Okapi）
        self.texts = None
        self.bm25 = None
        runtime_paths = [os.path.join(index_dir, "bm25.pkl.gz"),
                         os.path.join(index_dir, "bm25.runtime.pkl.gz")]
        loaded_runtime = False
        for rp in runtime_paths:
            if os.path.exists(rp):
                with gzip.open(rp, "rb") as f:
                    pack = pickle.load(f)
                self.bm25 = pack["bm25"]
                self.texts = pack["texts"]
                self.bm25_ids = pack["ids"]
                loaded_runtime = True
                break

        if not loaded_runtime:
            # 回退：从旧版 bm25.pkl（只含 tokens）重建
            legacy = os.path.join(index_dir, "bm25.pkl")
            if not os.path.exists(legacy):
                raise FileNotFoundError("No BM25 index file found.")
            with open(legacy, "rb") as f:
                obj = pickle.load(f)
            from rank_bm25 import BM25Okapi
            self.texts = obj["texts"]
            self.bm25_ids = obj["doc_ids"]
            tokens = obj["tokens"]
            self.bm25 = BM25Okapi(tokens)
            self.reranker = None
            if os.getenv("MINBIZ_RERANK", "1") == "1":
                try:
                    self.reranker = _LiteReranker()
                except Exception as e:
                    # 不让服务挂：依赖缺失时仅打印告警
                    print(f"[hybrid] reranker disabled: {type(e).__name__}: {e}")          

    def embed_query(self, q: str) -> np.ndarray:
        # e5 查询端必须加 "query: "
        v = self.model.encode([f"query: {q}"], normalize_embeddings=self.normalize)
        return np.asarray(v, dtype="float32")

def search(self, q: str, top_k: int = 6, alpha: float = 0.6) -> List[Hit]:
    """
    新策略：
    1) 生成多查询（原问句 + 3个改写）
    2) 对每个子查询做：向量topN + BM25topN，分数线性融合
    3) 合并去重（chunk_id维度）
    4) （若可用）交叉重排
    5) 取前 top_k
    """
    # 1) 多查询扩展
    queries = _expand_queries_with_llm(q, n=3)

    # 2) 每个子查询都做更“宽”的初筛
    per_list_topn = int(os.getenv("MINBIZ_PER_LIST_TOPN", "30"))
    bucket_scores: Dict[str, float] = {}
    bucket_texts: Dict[str, str] = {}

    def _accumulate(cid: str, score: float, text: str):
        bucket_scores[cid] = bucket_scores.get(cid, 0.0) + score
        if text and not bucket_texts.get(cid):
            bucket_texts[cid] = text

    for subq in queries:
        # 向量召回
        qv = self.embed_query(subq)
        D, I = self.faiss.search(qv, per_list_topn)
        for i, idx in enumerate(I[0]):
            cid = self.ids[idx]
            vscore = float(D[0, i])
            text = self.texts[idx] if self.texts else ""
            _accumulate(cid, alpha * vscore, text)

        # BM25 召回
        toks = tokenize_jieba_bigram(subq)
        bm_scores = self.bm25.get_scores(toks)
        bm_idx = np.argsort(-bm_scores)[:per_list_topn]
        for i in bm_idx:
            cid = self.bm25_ids[i]
            bscore = float(bm_scores[i])
            text = self.texts[i]
            _accumulate(cid, (1 - alpha) * bscore, text)

    # 3) 合并去重并转为列表
    merged = [ (cid, sc) for cid, sc in bucket_scores.items() ]
    merged.sort(key=lambda x: -x[1])

    # 4) （可选）交叉重排
    hits_all: List[Hit] = [
        Hit(chunk_id=cid, text=bucket_texts.get(cid, ""), score=sc,
            doc_title=None, source_file=cid.split("-")[0])
        for cid, sc in merged
    ]

    if self.reranker and hits_all:
        passages = [h.text or "" for h in hits_all]
        scores = self.reranker.score(q, passages)
        # 归一/融合：0.5*原分 + 0.5*重排分
        for h, s in zip(hits_all, scores):
            h.score = 0.5 * float(h.score) + 0.5 * float(s)
        hits_all.sort(key=lambda x: -x.score)

    # 5) 截断
    return hits_all[:top_k]


# === NEW: CrossEncoder Reranker（轻量内置）===
class _LiteReranker:
    def __init__(self, name: str = None, device: str | None = None):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.name = name or os.getenv("MINBIZ_RERANK_MODEL", "BAAI/bge-reranker-base")
        self.tok = AutoTokenizer.from_pretrained(self.name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.name)
        self.model.eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.torch = torch

    def score(self, query: str, passages: list[str]) -> list[float]:
        with self.torch.no_grad():
            pairs = [(query, p) for p in passages]
            inputs = self.tok.batch_encode_plus(
                pairs, padding=True, truncation=True, max_length=512, return_tensors='pt'
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            logits = self.model(**inputs).logits.squeeze(-1)
            return logits.detach().cpu().tolist()

# ============ Pipeline functions ============
def build_evidence_pack(
    q: str,
    index_dir: str,
    encoder: str,
    # 以下是可调的上下文控制参数（默认与你 voice_agent.py 本地实现一致/相近）
    display_mode: str = "inline",
    max_chars_per_snippet: int = 180,
    max_total_quote_chars: int = 960,
    per_ctx_blocks: int = 8,
) -> Tuple[EvidencePack, str, List[Hit]]:
    """
    统一返回 (ep, context_text, hits)
    - ep.hits: 命中对象列表
    - context_text: 供 LLM 使用的上下文（已做安全裁剪/拼接）
    """
    # 1) 检索（HybridSearcher 内部已含多查询+融合+可选交叉重排）
    hs = HybridSearcher(index_dir=index_dir, encoder_name=encoder, normalize=True)
    hits = hs.search(q, top_k=int(os.getenv("MINBIZ_SEARCH_TOPK", os.getenv("RAG_TOPK", "12"))), alpha=0.55)

    # 2) 上下文拼接（两种方案：A. 直接用 [chunk_id] + 摘要行；B. 用已有的 secure builder）
    try:
        # 如果你的项目已经有这个函数，优先用它（更稳）
        from src.app.rag import build_context_for_query_secure
        ctx_text, _refs = build_context_for_query_secure(
            hits,
            display_mode=display_mode,
            max_chars_per_snippet=max_chars_per_snippet,
            max_total_quote_chars=max_total_quote_chars,
            per_ctx_blocks=per_ctx_blocks,
        )
    except Exception:
        # 兜底：简单拼接（每段前缀带 chunk_id，便于引用）
        ctx_lines = []
        for h in hits:
            snippet = (h.text or "").replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:280] + "…"
            ctx_lines.append(f"[{h.chunk_id}] {snippet}")
        ctx_text = "\n".join(ctx_lines)

    # 3) 包装返回
    ep = type("EP", (), {})()
    ep.hits = hits
    return ep, ctx_text, hits



def evidence_score(hits: List[Hit]) -> float:
    if not hits: return 0.0
    # 简化：归一化 top1~topk 的平均
    vals = np.array([h.score for h in hits], dtype="float32")
    # 取 min-max 到 [0,1]
    if vals.max() == vals.min():
        return 0.5
    norm = (vals - vals.min()) / (vals.max() - vals.min())
    return float(norm.mean())

def _style_prompt(style: str, lang: str) -> str:
    s = (style or "concise").lower()
    if lang.lower().startswith("zh"):
        if s == "story":
            return "用生动的故事化口吻回答，适当用类比/小场景，句子短，落到可执行建议。"
        elif s == "formal":
            return "用正式专业的中文表述，条理清晰。"
        elif s == "casual":
            return "用轻松口语的中文说明，简洁直白。"
        else:
            return "简洁、可执行、结构清晰。"
    else:
        if s == "story":
            return "Answer in a vivid, story-like tone with brief analogies and imagery; keep sentences short and end with actionable advice."
        elif s == "formal":
            return "Use a formal, professional tone with clear structure."
        elif s == "casual":
            return "Use a casual, conversational tone; be concise."
        else:
            return "Be concise, practical, and well-structured."

def make_draft(q: str, ctx_text: str, model: str, allowed_ids: set[str]) -> str:
    sys = ("You are a business assistant. Use ONLY the given evidence (by chunk_id). "
           "Cite chunk_ids like [doc-0001], avoid fabricating citations.")
    prompt = f"""Evidence:
{ctx_text}

Question:
{q}

Instructions:
- Only use the facts from the evidence above.
- Cite supporting chunk_ids like [doc-0001, doc-0003] where relevant.
- If evidence is insufficient, say so briefly before general advice.
"""
    resp = _oai.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def check_support_ids_exist(draft: str, valid_ids: set[str]):
    ids = set()
    for tok in draft.split("["):
        if "]" in tok:
            seg = tok.split("]")[0]
            for x in seg.split(","):
                x = x.strip()
                if x:
                    ids.add(x)
    # 如果出现不在 valid 里的 id，抛错以触发纠正
    for i in ids:
        if i not in valid_ids:
            raise ValueError(f"invalid citation id: {i}")

def _sanitize_draft(draft: str, valid_ids: set[str]) -> str:
    # 去掉无效引用
    def _filter(m):
        seg = m.group(1)
        ids = [x.strip() for x in seg.split(",")]
        ids = [x for x in ids if x in valid_ids]
        return f"[{', '.join(ids)}]" if ids else ""
    return re.sub(r"\[([^\]]+)\]", _filter, draft)

def _regenerate_draft_with_constraints(make_draft_fn, q, ctx_text, valid_ids, tries=1, model="gpt-4o-mini"):
    text = make_draft_fn(q, ctx_text, model, valid_ids)
    text = _sanitize_draft(text, valid_ids)
    return text

def refine_with_background(draft: str, model: str) -> Refined:
    # 简化：把 draft 当成最终要点，再补一点背景润色
    bg = "（背景要点已纳入，不新增外部信息）"
    return Refined(draft=draft, background=bg)

def synthesize_answer(q: str, refined_json: str, model: str, style: str = "concise", lang: str = "auto") -> str:
    """
    强约束：
    - 仅在句尾用 [chunk_id] 引用，且 chunk_id 必须存在于 evidence_map
    - 若证据不足，先明确提示，再给一般建议
    - style 支持：concise / story / story_six  （story_six 即六幕剧）
    """
    obj = json.loads(refined_json)
    draft = obj.get("draft","") or obj.get("content","") or ""
    claims = obj.get("claims", [])
    # 建 evidence_map
    evidence_map = {}
    for c in claims:
        cid_list = c.get("support") or c.get("supports") or []
        # 过滤空与重复
        evidence_map[str(c.get("id","c"))] = [s for s in cid_list if isinstance(s, str) and s.strip()]

    # 拼接合法的 chunk_id 白名单
    legal_ids = sorted(set([cid for lst in evidence_map.values() for cid in lst]))
    legal_list = "\n".join(legal_ids) if legal_ids else ""

    # 风格模板
    STYLE_GUIDE_CONCISE_ZH = (
        "用中文回答：先结论，后步骤，最后给下一步行动。"
        "所有事实句在句尾用 [chunk_id]，且 chunk_id 必须来自 LEGAL_IDS。"
    )
    STYLE_GUIDE_STORY_ZH = (
        "用中文回答：用1-2句故事/比喻开头，分点讲方法，列风险与下一步。"
        "所有事实句在句尾用 [chunk_id]（故事/比喻不需要），且 chunk_id 必须来自 LEGAL_IDS。"
    )
    STYLE_GUIDE_SIX_ZH = (
        "你是一位世界顶级商业咨询师兼讲师，用中文、六幕剧结构输出："
        "第一幕觉醒、第二幕变现、第三幕起步、第四幕成长、第五幕成交、第六幕放大。"
        "每幕要有故事/比喻+实操步骤；"
        "所有来自知识库的具体事实与术语，在句尾用 [chunk_id] 引用（故事/比喻不必引用）；"
        "若证据不足，先明确提示“【证据不足】”，再给一般建议。"
    )
    sguide = {
        "concise": STYLE_GUIDE_CONCISE_ZH,
        "story": STYLE_GUIDE_STORY_ZH,
        "story_six": STYLE_GUIDE_SIX_ZH
    }.get(style, STYLE_GUIDE_CONCISE_ZH)

    sys = (
        "你是严谨的编辑，负责把草稿重写为用户可直接执行的答案。"
        "禁止编造引用；引用必须使用 LEGAL_IDS 列表中的真实 chunk_id。"
        "如果草稿没有足够证据支撑，请在开头标注“【证据不足】”。"
    )
    user = (
        f"问题：{q}\n"
        f"风格：{style}\n"
        f"LANG: zh\n"
        f"STYLE_GUIDE:\n{sguide}\n\n"
        f"LEGAL_IDS（逐行一个）：\n{legal_list}\n\n"
        f"草稿：\n{draft}\n\n"
        "请输出最终答案。务必遵循：\n"
        "1) 事实句用 [chunk_id]，且必须来自 LEGAL_IDS；\n"
        "2) 不要出现 [c1]/[c2] 之类占位；\n"
        "3) 如果没有任何 LEGAL_IDS，可在开头标注“【证据不足】”，随后给一般性建议；\n"
    )

    resp = _oai.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":sys},{"role":"user","content":user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()

