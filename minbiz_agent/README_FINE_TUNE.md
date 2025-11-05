# Fine-tuning & Safety

## 1) PII & IP
- Run `python -m src.ingest.pipeline` to produce **redacted** chunks.
- Only fine-tune on **redacted** text to respect IP & privacy.

## 2) Synthetic SFT
```bash
python -m src.train.synthetic_gen --n 1000
```

## 3) QLoRA (adapter stub)
Use `src/train/qlora_finetune.py` as starting point on your own GPU/Colab/AWS.

## 4) Evaluation
- Ask pricing/定位/测评/交付 SOP; check citations; ensure no long verbatim quotes.
- Red-team: try to elicit raw course content; expect refusal.


## New in v2
- Synthetic samples now include:
  - `"flags": ["synthetic","pii_redacted"]`
  - `"origin_source": {"file": "...", "chunk_id": "..."}` for internal tracing only (do not display to end users).
- Rule‑based paraphraser avoids verbatim leakage; inputs are summarized before generation.
- You can control citation verbosity via `app.show_citation_detail` in `config.yaml`.
