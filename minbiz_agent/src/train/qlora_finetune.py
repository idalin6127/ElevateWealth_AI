import argparse, os
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_jsonl", default="data/sft/train_synthetic.jsonl")
    ap.add_argument("--base_model", default="meta-llama/Llama-3-8b-Instruct")
    ap.add_argument("--output_dir", default="out/minbiz-qlora")
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=1)
    args = ap.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    with open(os.path.join(args.output_dir, "NEXT_STEPS.txt"), "w", encoding="utf-8") as f:
        f.write("Install transformers, peft, bitsandbytes; load base model; prepare Dataset from JSONL; run QLoRA training.\n")
    print("Scaffold ready:", args.output_dir)

if __name__ == "__main__":
    main()
