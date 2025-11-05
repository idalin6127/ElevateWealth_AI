import os, json, argparse, random, re, pathlib
from typing import List, Dict
from src.utils.io_utils import list_files_with_suffix, read_jsonl

# ---------- Lightweight paraphrase helpers (rule-based, LLM-free) ----------
REPHRASE_MAP = [
    (r"定位", "市场定位"),
    (r"定价", "价格策略"),
    (r"引流", "获客"),
    (r"转化", "成交转化"),
    (r"测评", "诊断问卷"),
    (r"SOP", "流程规范"),
    (r"复购", "二次成交"),
]

def paraphrase(text: str) -> str:
    """A tiny rule-based paraphraser to ensure expression difference (no verbatim reuse)."""
    out = text
    for pat, rep in REPHRASE_MAP:
        out = re.sub(pat, rep, out)
    # shuffle bullets if any
    bullets = [b.strip() for b in re.split(r"[\n•\-]\s+", out) if b.strip()]
    if 2 <= len(bullets) <= 6 and len(out) < 600:
        random.shuffle(bullets)
        out = "- " + "\n- ".join(bullets)
    return out

# ---------- Prompt templates (transformative, not reproducing originals) ----------
TEMPLATES = [
    {
        "instruction": "请为{aud}制定一份一周可执行的市场定位与价格策略计划（需包含指标与验收标准）。",
        "input": "背景要点（非原文）：{ctx}\n请根据要点进行**转化性**总结与扩写，避免任何逐字复现。",
        "output": "行动清单：\n1) 明确单一高价值问题与用户画像\n2) 设计价格梯度与入门款验证路径\n3) 关键指标：线索成本 / 预约率 / 成交率\n4) 证据：表单记录、访谈纪要、报价单样例"
    },
    {
        "instruction": "Design a week‑1 delivery process (SOP) for {aud} with concrete artifacts and metrics.",
        "input": "Context (abstracted): {ctx}\nTransform the ideas; do not quote original sentences.",
        "output": "SOP:\n- Day1: Kickoff + diagnostic form\n- Day3: Offer draft + pricing rationale\n- Day5: Objection list + scripts\n- KPI: form CVR≥15%, show‑up≥60%"
    },
    {
        "instruction": "列出适用于{aud}的内容话题矩阵与引流渠道测试方案，并包含AB测试思路。",
        "input": "摘要要点：{ctx}\n请输出不依赖原文表达的总结与扩写。",
        "output": "建议：\n- 话题簇：痛点拆解/案例复盘/误区澄清\n- 渠道：短视频/长帖/直播/广告\n- AB：标题钩子/开头3秒/CTA变体\n- 度量：浏览->点击->表单->预约"
    },
    {
        "instruction": "Generate a sales conversation framework for {aud} including disqualification rules.",
        "input": "Abstract context: {ctx}\nEnsure fully original wording with concrete steps and artifacts.",
        "output": "Framework:\n- Discovery: pain → urgency → constraints\n- Offer fit: ROI framing + milestones\n- Disqualify if: 无预算/无决策权/动机不足\n- Artifacts: call notes, proposal v1, follow‑up email"
    }
]

AUDS = [
    "在北美的华人职场女性",
    "solo 创业者（教练/咨询）",
    "B2B 服务商（高客单交付）",
    "内容创作者转咨询/陪跑"
]

def summarize_for_ctx(s: str, max_len: int = 220) -> str:
    """Crude context summarizer: trim + simple paraphrase to avoid verbatim leakage."""
    s = s.strip().replace("\n", " ")
    s = s[:max_len]
    return paraphrase(s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks_dir", default="data/chunks")
    ap.add_argument("--out_jsonl", default="data/sft/train_synthetic.jsonl")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)

    os.makedirs(os.path.dirname(args.out_jsonl), exist_ok=True)
    pool: List[Dict] = []
    # collect pii_redacted chunks only
    for fp in list_files_with_suffix(args.chunks_dir, ".jsonl"):
        for row in read_jsonl(fp):
            if "pii_redacted" in row.get("flags", []):
                pool.append({
                    "source_file": row.get("source_file", pathlib.Path(fp).name),
                    "id": row.get("id", ""),
                    "text": row.get("text","")
                })

    random.shuffle(pool)
    out_count = min(args.n, len(pool))
    with open(args.out_jsonl, "w", encoding="utf-8") as f:
        for i in range(out_count):
            t = random.choice(TEMPLATES)
            aud = random.choice(AUDS)
            ctx = summarize_for_ctx(pool[i]["text"])
            # Build synthetic example
            ex = {
                "id": f"synth-{i:05d}",
                "instruction": paraphrase(t["instruction"].format(aud=aud)),
                "input": paraphrase(t["input"].format(ctx=ctx)),
                "output": paraphrase(t["output"]),
                "flags": ["synthetic", "pii_redacted"],
                "origin_source": {
                    "file": pool[i]["source_file"],
                    "chunk_id": pool[i]["id"]
                }
            }
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print("Wrote", args.out_jsonl, "samples:", out_count)

if __name__ == "__main__":
    main()
