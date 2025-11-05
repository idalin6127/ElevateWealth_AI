# src/app/pipeline.py
# -*- coding: utf-8 -*-
"""
多阶段编排：
A) RAG 取证据 -> EvidencePack
B) Draft（仅基于证据，结构化 JSON，claims 必须带 support=chunk_id 列表）
C) 校验 -> 重试（白名单）-> 兜底清洗
D) Refine（允许通识补充，标注 external/冲突以 internal 为准）
E) 合成自然语言答案（句尾 [chunk_id] 引用；禁止 [c1]/[c2] 占位）
"""

from __future__ import annotations
from typing import Set, Tuple, List, Dict, Optional
import json
import re

# —— 检索与安全上下文 ——
from src.index.retriever import HybridSearcher
from src.app.rag import build_context_for_query_secure

# —— 数据模型 ——
from src.app.schemas import (
    EvidencePack, EvidenceHit,
    Draft, Refined, Claim, BGAddition, Conflict
)

# —— 校验工具 ——
from src.app.validators import check_support_ids_exist

# —— LLM 调用封装 ——
from src.app.llm_client import chat_json, chat_text

import re as _re_lang

def _contains_cjk(s: str) -> bool:
    return bool(_re_lang.search(r"[\u4e00-\u9fff]", s or ""))

def _decide_lang(user_lang: str, question: str) -> str:
    """
    user_lang: 'auto' | 'zh' | 'en'
    """
    if user_lang in ("zh", "en"):
        return user_lang
    return "zh" if _contains_cjk(question) else "en"


# =========================
# A) 证据打包 (RAG -> EvidencePack)
# =========================
def build_evidence_pack(
    query: str,
    index_dir: str = "data/index",
    encoder: str = "intfloat/multilingual-e5-base",
    display_mode: str = "summary",
    per_ctx_blocks: int = 6
) -> Tuple[EvidencePack, str, list]:
    """
    返回: (EvidencePack, context_text_for_prompt, raw_hits)
    """
    hs = HybridSearcher(index_dir=index_dir, encoder_name=encoder)
    hits = hs.search(query, use_rerank=True, final_k=10)

    # 安全上下文（摘要/短引 + 引用限制）
    ctx_text, refs = build_context_for_query_secure(
        hits,
        display_mode=display_mode,
        max_chars_per_snippet=90,
        max_total_quote_chars=300,
        per_ctx_blocks=per_ctx_blocks
    )

    ep = EvidencePack(
        question=query,
        hits=[
            EvidenceHit(
                chunk_id=r["chunk_id"],
                title=r["title"] or "",
                start_s=r["start_s"],
                end_s=r["end_s"],
                snippet="",                 # 不直出长文本，只在 RAG 构建时做摘要
                source=str(r["file"]),
                type="internal",
            )
            for r in refs
        ],
    )
    return ep, ctx_text, hits


# =========================
# B) Draft（结构化草稿，仅基于证据）
# =========================
DRAFT_SYS = (
    "你是严谨的证据驱动助手。仅基于 [EVIDENCE] 生成 JSON 草稿。\n"
    "输出必须是一个对象，字段：\n"
    "  - claims: 列表，每个元素是 {id: 字符串, text: 字符串, support: 字符串列表}\n"
    "  - steps:  列表（字符串）\n"
    "  - gaps:   列表（字符串）\n"
    "  - tone:   'professional'\n"
    "要求：\n"
    "  - 每条 claim 的 support 必须是内部 chunk_id 列表（如 '1.潜意识::15'）。\n"
    "  - 不要出现其它字段名，如 'claim'/'content'/'evidence' 等。\n"
    "  - 严格返回 JSON（不要 markdown 代码块）。\n"
    "示例：\n"
    "{\n"
    "  \"claims\": [\n"
    "    {\"id\": \"c1\", \"text\": \"X 的比喻是猴子与大象。\", \"support\": [\"1.潜意识::4\", \"1.潜意识::15\"]}\n"
    "  ],\n"
    "  \"steps\": [\"先解释两者含义\", \"再对比差异\"],\n"
    "  \"gaps\": [],\n"
    "  \"tone\": \"professional\"\n"
    "}\n"
)

def _normalize_draft_obj(obj: dict, allowed_ids: Set[str] | None = None) -> dict:
    """
    把模型返回的草稿对象“归一化”为我们要求的字段:
    - claims[*].id / text / support
    - steps / gaps / tone
    允许输入里出现 'claim'/'content'/'desc'/'supports'/'evidence' 等别名，并做映射。
    为缺失 id 自动生成 c1/c2/...，并过滤非法 support（若提供了白名单）。
    """
    allowed = set(allowed_ids or [])
    out = {"claims": [], "steps": [], "gaps": [], "tone": "professional"}

    raw_claims = obj.get("claims") or obj.get("Claims") or []
    if isinstance(raw_claims, dict):  # 极端情况：模型给了对象
        raw_claims = [raw_claims]

    for i, c in enumerate(raw_claims, start=1):
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or f"c{i}"
        text = c.get("text") or c.get("claim") or c.get("content") or c.get("desc") or ""
        sup = (
            c.get("support")
            or c.get("supports")
            or c.get("evidence")
            or c.get("ref_ids")
            or []
        )
        # 归一化 support 成 list[str]
        if isinstance(sup, str):
            sup = [sup]
        sup = [str(s) for s in sup if isinstance(s, (str, int))]

        if allowed:
            sup = [s for s in sup if s in allowed]

        text = (text or "").strip()
        if not text or not sup:
            continue

        out["claims"].append({"id": cid, "text": text, "support": sup})

    # steps / gaps / tone
    out["steps"] = [str(s) for s in (obj.get("steps") or obj.get("plan") or obj.get("actions") or []) if isinstance(s, (str, int))]
    out["gaps"]  = [str(s) for s in (obj.get("gaps")  or obj.get("missing") or []) if isinstance(s, (str, int))]
    tone = obj.get("tone") or "professional"
    out["tone"] = "professional" if tone not in ("professional", "casual", "formal") else tone
    return out

def make_draft(
    question: str,
    evidence_context: str,
    model: str = "gpt-4o-mini",
    allowed_ids: Set[str] | None = None
) -> Draft:
    # 兜底（防止全局常量未加载的极端情况）
    SYS = globals().get("DRAFT_SYS") or (
        "你是严谨的证据驱动助手。仅基于 [EVIDENCE] 生成 JSON 草稿。"
        "输出必须包含 claims(list[{id,text,support[]}]), steps(list), gaps(list), tone='professional'。"
        "每条 claims 的 support 只能是内部 chunk_id；严格返回 JSON。"
    )

    id_hint = ""
    if allowed_ids:
        id_list = ", ".join(sorted(allowed_ids))
        id_hint = (
            "\n[CONSTRAINTS]\n"
            f"- support 只能从以下 chunk_id 列表中选择：{id_list}\n"
            "- 若证据不足，请在 gaps 中明确指出，不要编造 support。\n"
        )

    user = (
        f"[USER_QUESTION]\n{question}\n\n"
        f"[EVIDENCE]\n{evidence_context}\n"
        "要求：仅基于 [EVIDENCE] 生成 JSON；所有 claims 必须包含 support（内部 chunk_id 列表）。"
        + id_hint
    )

    raw = chat_json(
        messages=[{"role": "system", "content": SYS},
                  {"role": "user",   "content": user}],
        model=model,
        temperature=0.2,
    )
    norm = _normalize_draft_obj(raw, allowed_ids=allowed_ids)
    return Draft.model_validate(norm)


# =========================
# C) Step6：校验 → 重试（白名单）→ 兜底清洗
# =========================
RETRY_HINT = (
    "請嚴格從下列合法 chunk_id 中選擇 support，且每條 claims 必須至少包含 1 個 support：\n"
    "{id_list}\n"
    "不要創建任何新的 id，不要留空。"
)

def _regenerate_draft_with_constraints(
    make_draft_fn,
    question: str,
    evidence_context: str,
    valid_ids: Set[str],
    tries: int = 2,
    model: str = "gpt-4o-mini"
) -> Draft:
    """
    首次校验失败后，带合法 chunk_id 白名单重试 1-2 次。
    """
    last_err = None
    id_list = ", ".join(sorted(valid_ids))
    draft = None
    for _ in range(tries):
        constrained_ctx = evidence_context + "\n\n" + RETRY_HINT.format(id_list=id_list)
        draft = make_draft_fn(question, constrained_ctx, model=model, allowed_ids=valid_ids)
        try:
            check_support_ids_exist(draft, valid_ids)
            return draft
        except Exception as e:
            last_err = e
            continue
    if last_err:
        print(f"[pipeline] Draft 引用校验反复失败，将执行兜底清洗: {last_err}")
    return draft

def _sanitize_draft(draft: Draft, valid_ids: Set[str]) -> Draft:
    """
    兜底：剔除无效 support；若某 claim 被剔空则移除。
    """
    clean = []
    removed = 0
    for c in draft.claims:
        supports = [s for s in c.support if s in valid_ids]
        if supports:
            c.support = supports
            clean.append(c)
        else:
            removed += 1
    draft.claims = clean
    if removed:
        print(f"[pipeline] 兜底：移除了 {removed} 条没有有效引用的 claims")
    return draft


# =========================
# D) Refine（允许通识补充） + 归一化
# =========================
_ALLOWED_SOURCES = {"external:web", "external:api", "external:paper", "external:other"}

def _bucket_source(val: str) -> str:
    if not val:
        return "external:other"
    v = str(val).lower().strip()
    if v.startswith("external:"):
        suf = v.split(":", 1)[1]
    else:
        suf = v
    if any(k in suf for k in ["api", "sdk", "endpoint"]):
        return "external:api"
    if any(k in suf for k in ["paper", "arxiv", "doi", "journal", "apa", "acm", "ieee"]):
        return "external:paper"
    if any(k in suf for k in ["web", "site", "blog", "news", "psychology_today", "wikipedia"]):
        return "external:web"
    return "external:other"

def _normalize_refined_obj(obj: dict) -> dict:
    """将 bg_additions 的 source 归一化到白名单值；缺字段则补齐。"""
    obj = dict(obj or {})
    ba = []
    for item in obj.get("bg_additions", []) or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        source = _bucket_source(str(item.get("source", "")))
        citation = str(item.get("citation", "")).strip() or "unspecified"
        ba.append({"text": text, "source": source, "citation": citation})
    obj["bg_additions"] = ba
    obj["claims"] = obj.get("claims", []) or []
    obj["conflicts"] = obj.get("conflicts", []) or []
    return obj

REFINE_SYS = (
    "你是行业顾问。输入是 Draft(JSON)。允许使用你的通识知识补充“最佳实践/方法论”。\n"
    "把补充写入 bg_additions，结构：\n"
    "  - text: 补充内容（字符串）\n"
    "  - source: 仅能为 'external:web' | 'external:api' | 'external:paper' | 'external:other'\n"
    "  - citation: 来源名称或接口名（字符串）\n"
    "如与内部 claims 冲突，请在 conflicts 中列出并以内部为准。只输出 JSON。\n"
)

def refine_with_background(draft: Draft, model: str = "gpt-4o") -> Refined:
    raw = chat_json(
        messages=[{"role": "system", "content": REFINE_SYS},
                  {"role": "user",   "content": draft.model_dump_json()}],
        model=model,
        temperature=0.4,
    )
    norm = _normalize_refined_obj(raw)
    return Refined.model_validate(norm)


# =========================
# E) 合成自然语言答案（支持“专业/讲故事”风格；始终使用真实 chunk_id 引用）
# =========================
def make_evidence_map(refined: Refined) -> Dict[str, List[str]]:
    """ claim_id -> support 的映射，用于提示模型引用真实 chunk_id """
    return {c.id: list(c.support) for c in refined.claims}

# —— 单语：专业/讲故事（中文） ——
FINAL_SYS_PRO_ZH = (
    "你是专业顾问。请用**中文**回答。根据 Refined(JSON) 输出最终答案："
    "1) 先给总体结论（2-3句）；2) 分点给出步骤/建议；3) 风险与下一步；"
    "对具体事实在句尾用 [chunk_id] 标注（多个用逗号分隔）；"
    "禁止使用 [c1]/[c2] 等占位符，引用必须来自[EVIDENCE_MAP]中的真实 chunk_id；"
    "优先使用[EVIDENCE]信息，外部补充仅作背景。语言自然、可执行。"
)
FINAL_SYS_STORY_ZH = (
    "你是一位善于“深入浅出”的顾问教练。请用**中文**回答："
    "A) 用1-2句形象类比/很短的故事（≤120字）引入；"
    "B) 用小标题+要点把方法/步骤讲透；"
    "C) 事实句尾用 [chunk_id] 引用（类比/故事不必引用）；"
    "D) 给出风险与下一步；E) 背景补充单列。"
    "禁止[c1]/[c2]占位；引用必须来自[EVIDENCE_MAP]真实 chunk_id；优先[EVIDENCE]。"
)

# —— 单语：专业/讲故事（英文） ——
FINAL_SYS_PRO_EN = (
    "You are a professional consultant. Answer in **English**. Based on Refined(JSON), produce: "
    "1) A concise overall conclusion (2–3 sentences); 2) Actionable steps; 3) Risks & next steps. "
    "Append [chunk_id] citations at the end of factual sentences (multiple separated by commas). "
    "Do NOT use placeholders like [c1]/[c2]; citations must come from real chunk_ids in [EVIDENCE_MAP]. "
    "Prioritize [EVIDENCE]; external additions are background only. Be clear, practical, and precise."
)
FINAL_SYS_STORY_EN = (
    "You are a coach who explains complex ideas clearly. Answer in **English**: "
    "A) Start with a short analogy or mini-story (≤120 words); "
    "B) Then structured headings + bullets for the method/steps; "
    "C) Put [chunk_id] citations at the end of factual sentences (no citations needed for the analogy/story); "
    "D) Risks & next steps; E) Background additions section. "
    "No [c1]/[c2]; citations must be real chunk_ids from [EVIDENCE_MAP]. Prioritize [EVIDENCE]."
)

# —— 六幕剧（中文）——
FINAL_SYS_STORY6_ZH = (
    "你是一位有感染力的商业讲师，请用**中文**按“六幕剧”讲解：\n"
    "结构：\n"
    "第一幕：觉醒篇（生活化例子+比喻）\n"
    "第二幕：变现篇（真实案例+三步逻辑）\n"
    "第三幕：起步篇（0成本上手步骤）\n"
    "第四幕：成长篇（四级晋升路线）\n"
    "第五幕：成交篇（高情商对话模板+故事）\n"
    "第六幕：放大篇（从个人到品牌的放大路径）\n"
    "要求：\n"
    "- 语言口语化、有节奏；多用比喻/例子/故事；\n"
    "- 每一幕结尾附 1 条“行动指令”；\n"
    "- 事实句尾用 [chunk_id] 引用（故事/类比可不引）；\n"
    "- 严禁 [c1]/[c2] 占位，引用必须来自[EVIDENCE_MAP]的真实 chunk_id；\n"
    "- 优先[EVIDENCE]信息，外部补充仅作背景。"
)

# —— 六幕剧（英文）——
FINAL_SYS_STORY6_EN = (
    "You are a captivating business speaker. Please explain the topic in **English** using a 'Six-Act Story' format:\n"
    "Structure:\n"
    "Act 1: Awakening — use a relatable life example or vivid metaphor.\n"
    "Act 2: Monetization — share a real-world case and break it down into a clear three-step logic.\n"
    "Act 3: Getting Started — explain how to start from zero with no cost.\n"
    "Act 4: Growth — outline a four-level progression or mastery path.\n"
    "Act 5: Conversion — include an emotional-intelligence based dialogue template + a short story.\n"
    "Act 6: Amplification — describe how to scale from an individual to a full personal brand.\n"
    "Requirements:\n"
    "- Use spoken, rhythmic, and emotionally engaging language.\n"
    "- Use plenty of examples, stories, and metaphors.\n"
    "- End each act with one clear 'Action Command'.\n"
    "- For factual statements, end the sentence with [chunk_id] citation (stories/metaphors do not need it).\n"
    "- Strictly forbid placeholders like [c1]/[c2]; citations must come from real chunk_ids in [EVIDENCE_MAP].\n"
    "- Prioritize information from [EVIDENCE]; use outside content only for background or narrative color."
)


# —— 双语（中文+英文）统一风格说明 ——
FINAL_SYS_BILINGUAL = (
    "你是双语顾问。请按**中文在前、英文在后**输出两个版本（结构一致），"
    "每个版本都包含：总体结论、步骤/建议、风险与下一步、（可选）背景补充。"
    "事实句尾均用 [chunk_id] 引用（多个用逗号分隔），且**必须**来自[EVIDENCE_MAP]真实 chunk_id；"
    "禁止使用[c1]/[c2]占位。优先使用[EVIDENCE]信息，外部补充仅作背景。"
)


def synthesize_answer(
    question: str,
    refined,                      # Refined 对象（保持与你的 Pydantic 模型一致）
    model: str = "gpt-4o",
    style: str = "pro",           # "pro" | "story" | "story_six"
    lang: str = "auto",           # "auto" | "zh" | "en"
    bilingual: bool = False       # True 同时中英双语
) -> str:
    evid_map = json.dumps(make_evidence_map(refined), ensure_ascii=False)
    target_lang = _decide_lang(lang, question)

    if bilingual:
        # 双语统一提示词
        sys_prompt = FINAL_SYS_BILINGUAL
        temp = 0.55 if style in ("story", "story_six") else 0.35
    else:
        # 单语：根据语言与风格选择对应提示词
        if target_lang == "zh":
            if style == "story_six":
                sys_prompt = FINAL_SYS_STORY6_ZH
            else:
                sys_prompt = FINAL_SYS_STORY_ZH if style == "story" else FINAL_SYS_PRO_ZH
        elif target_lang == "en":
            if style == "story_six":
                sys_prompt = FINAL_SYS_STORY6_EN
            else:
                sys_prompt = FINAL_SYS_STORY_EN if style == "story" else FINAL_SYS_PRO_EN
        else:
            # 兜底：未知语言 → 英文专业版
            sys_prompt = FINAL_SYS_PRO_EN
        # 讲故事/六幕剧温度略高
        temp = 0.55 if style in ("story", "story_six") else 0.3

    user = (
        f"[QUESTION]\n{question}\n\n"
        f"[REFINED]\n{refined.model_dump_json()}\n\n"
        f"[EVIDENCE_MAP]\n{evid_map}\n"
        "[EVIDENCE]\n"
        "（以上 JSON 中 claims.support 是可引用的内部证据片段ID，即 chunk_id。"
        "请严格使用这些 chunk_id 做句尾引用；类比/故事无需引用。）"
    )

    return chat_text(
        messages=[{"role": "system", "content": sys_prompt},
                  {"role": "user",   "content": user}],
        model=model,
        temperature=temp,
    )


# =========================
# 实用：证据打分（路由策略用）
# =========================
def evidence_score(hits) -> float:
    if not hits:
        return 0.0
    k = min(8, len(hits))
    mean = sum([h.score for h in hits[:k]]) / k
    return 0.6 * (k / 8.0) + 0.4 * min(1.0, max(0.0, mean))


# =========================
# 只展示“用到的引用”
# =========================
_CHUNK_ID_RE = re.compile(r"\[(\d+\.[^\[\]:]+::\d+)\]")

def extract_used_chunk_ids(answer_text: str) -> List[str]:
    return sorted(set(_CHUNK_ID_RE.findall(answer_text or "")))


# =========================
# CLI 入口
# =========================
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument(
    "--style",
    choices=["pro", "story", "story_six"],
    default="pro",
    help="答案风格：专业(pro) / 讲故事(story) / 六幕剧(story_six)"
)
    ap.add_argument("--lang",  choices=["auto","zh","en"], default="auto", help="回答语言：auto/zh/en")
    ap.add_argument("--bilingual", action="store_true", help="同时输出中英双语版本")
    ap.add_argument("--q", required=True)
    ap.add_argument("--index_dir", default="data/index")
    ap.add_argument("--encoder", default="intfloat/multilingual-e5-base")
    ap.add_argument("--no_refine", action="store_true", help="跳过背景补充阶段（只做证据→草稿→合成）")
    args = ap.parse_args()

    # A) 证据
    ep, ctx_text, hits = build_evidence_pack(
        args.q, index_dir=args.index_dir, encoder=args.encoder
    )

    # 证据不足提示（可选）
    score = evidence_score(hits)
    if score < 0.25:
        ctx_text = "【证据不足】内部覆盖较弱，以下先给一般性建议。\n\n" + ctx_text

    # B) Draft（首次生成，带白名单提示更稳）
    valid_ids: Set[str] = {h.chunk_id for h in ep.hits}
    draft = make_draft(args.q, ctx_text, model="gpt-4o-mini", allowed_ids=valid_ids)

    # C) Step6 校验 → 重试 → 兜底
    try:
        check_support_ids_exist(draft, valid_ids)
    except Exception as e:
        print(f"[pipeline] Draft 引用校验失败，尝试白名单重生：{e}")
        draft = _regenerate_draft_with_constraints(
            make_draft, args.q, ctx_text, valid_ids, tries=2, model="gpt-4o-mini"
        )
        try:
            check_support_ids_exist(draft, valid_ids)
        except Exception as e2:
            print(f"[pipeline] 重生后仍未通过，执行兜底：{e2}")
            draft = _sanitize_draft(draft, valid_ids)
            # 兜底后保守再检一次；若为空可选择降级
            check_support_ids_exist(draft, valid_ids)

    # D) Refine（可选）
    if args.no_refine or not draft.claims:
        refined_obj = {
            "claims": [c.model_dump() for c in draft.claims],
            "bg_additions": [],
            "conflicts": []
        }
        refined = Refined.model_validate(refined_obj)
    else:
        refined = refine_with_background(draft, model="gpt-4o")

    # E) 合成
    final = synthesize_answer(
    args.q, refined,
    model="gpt-4o",
    style=args.style,
    lang=args.lang,
    bilingual=args.bilingual)

    used_ids = extract_used_chunk_ids(final)
    filtered_refs = [h for h in ep.hits if h.chunk_id in used_ids]

    print("\n=== Answer ===\n")
    print(final)
    print("\n=== Refs (internal, used) ===\n")
    print(json.dumps([h.model_dump() for h in filtered_refs], ensure_ascii=False, indent=2))
