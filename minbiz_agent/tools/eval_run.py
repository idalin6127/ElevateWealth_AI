# tools/eval_run.py
import argparse, shutil, pathlib, subprocess, sys, yaml

def cp_glob(src_glob: str, dst_dir: str) -> int:
    dst = pathlib.Path(dst_dir); dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in pathlib.Path().glob(src_glob):
        if p.is_file():
            shutil.copy2(p, dst / p.name); n += 1
    return n

def set_config_mode(mode: str):
    cfg_p = pathlib.Path("config.yaml")
    cfg = {}
    if cfg_p.exists():
        cfg = yaml.safe_load(cfg_p.read_text(encoding="utf-8")) or {}
    cfg.setdefault("app", {})["retrieval_mode"] = mode  # bm25 | faiss | hybrid
    cfg.setdefault("paths", {}).setdefault("index_dir", "data/index")
    cfg.setdefault("paths", {}).setdefault("chunks_dir", "data/chunks")
    cfg.setdefault("paths", {}).setdefault("transcripts_dir", "data/fulltext_clean")
    cfg_p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

def run_case(mode: str, case: str):
    # 1) 切换 A/B 产物到默认目录
    pathlib.Path("data/index").mkdir(parents=True, exist_ok=True)
    pathlib.Path("data/chunks").mkdir(parents=True, exist_ok=True)
    for p in pathlib.Path("data/index").glob("*"): p.unlink()
    for p in pathlib.Path("data/chunks").glob("*.chunks.jsonl"): p.unlink()
    n_idx = cp_glob(f"data/index_{case}/*", "data/index")
    n_chk = cp_glob(f"data/chunks_{case}/*.chunks.jsonl", "data/chunks")

    # 2) 写入检索模式到 config.yaml
    set_config_mode(mode)

    # 3) 跑查询，收集日志
    log = pathlib.Path(f"eval/logs/result_{mode}_{case}.txt")
    log.parent.mkdir(parents=True, exist_ok=True)
    with open("eval/queries.txt", "r", encoding="utf-8") as qf, open(log, "w", encoding="utf-8") as lf:
        lf.write(f"[eval] case={case} mode={mode}  copied: index={n_idx} files, chunks={n_chk} files\n")
        for line in qf:
            q = line.strip()
            if not q: continue
            lf.write(f">>> Q: {q}\n")
            # 注意：不再传 --mode，让 CLI 走 config.yaml
            out = subprocess.run(
                [sys.executable, "-m", "src.app.cli", "--q", q, "--k", "10"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            lf.write((out.stdout or "").strip() + "\n\n")
    print("Saved ->", log)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="hybrid", choices=["bm25","faiss","hybrid"])
    ap.add_argument("--case", default="A", choices=["A","B"])
    args = ap.parse_args()
    run_case(args.mode, args.case)
