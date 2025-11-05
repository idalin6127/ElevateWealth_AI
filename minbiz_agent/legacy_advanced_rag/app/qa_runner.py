# src/app/qa_runner.py
from src.app.pipeline import build_evidence_pack, make_draft, refine_with_background, synthesize_answer, evidence_score

if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--q", required=True)
    ap.add_argument("--index_dir", default="data/index")
    ap.add_argument("--encoder", default="intfloat/multilingual-e5-base")
    args = ap.parse_args()

    ep, ctx_text, hits = build_evidence_pack(args.q, index_dir=args.index_dir, encoder=args.encoder)
    if evidence_score(hits) < 0.25:
        ctx_text = "【证据不足】内部覆盖较弱，以下先给一般性建议。\n\n" + ctx_text
    draft = make_draft(args.q, ctx_text)
    refined = refine_with_background(draft)
    final = synthesize_answer(args.q, refined.model_dump_json())
    print(final)
