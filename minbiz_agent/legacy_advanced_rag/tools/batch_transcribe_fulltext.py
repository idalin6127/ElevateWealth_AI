# -*- coding: utf-8 -*-
"""
批量转录 →（可选）段落化 → 清洗去重 → 写入 fulltext_clean →（可选）触发 pipeline/索引
- 可中断、可续跑：已完成的文件自动跳过
- 进度打印：每 ~10 秒输出一次 progress
- 先用 small + CPU 跑通；少量关键音频再切 medium 重跑覆盖

运行示例（Windows PowerShell）：
  .\.venv_min\Scripts\Activate.ps1
  $env:CUDA_VISIBLE_DEVICES = "-1"            # 强制 CPU，避免找 CUDA
  python tools\batch_transcribe_fulltext.py

你也可以用环境变量临时覆盖模型/索引模式等：
  $env:MINBIZ_WHISPER_MODEL = "medium"
  $env:MINBIZ_INDEX_MODE   = "hybrid"
"""

import os, glob, json, uuid, sys, time, re, unicodedata, subprocess, pickle, argparse
from pathlib import Path
from typing import List, Dict, Optional

# =============== 可调参数（集中在这里） ===============
# Whisper 模型与推理配置
MODEL = os.environ.get("MINBIZ_WHISPER_MODEL", "small")   # "base" | "small" | "medium" ...
CPU_THREADS = int(os.environ.get("MINBIZ_CPU_THREADS", "4"))
VAD_FILTER = False
BEAM_SIZE = 1
WORD_TIMESTAMPS = False

# 是否在每个文件转完后做后续处理
PARAGRAPHIZE_AFTER_TRANSCRIBE = True   # 若想“先成段再清洗”，设为 True（会调用 paragraphize 的内置实现）
RUN_PIPELINE_AFTER_EACH      = True     # 转完/清洗后立刻跑 pipeline（只处理 fulltext_clean）
RUN_BUILD_INDEX_EVERY_N      = 5        # 每处理完 N 个文件刷新一次索引；0 = 不刷新
BUILD_INDEX_MODE = os.environ.get("MINBIZ_INDEX_MODE", "bm25")  # "bm25" | "faiss" | "hybrid"

# 目录
AUDIO_DIR = Path("data/audio")
FT_DIR    = Path("data/fulltext")         # 原始逐句转录（txt/jsonl）
PARA_DIR  = Path("data/paragraphs")       # 段落化输出（可选）
FTC_DIR   = Path("data/fulltext_clean")   # 清洗后的“干净文本”（供 pipeline 使用）
FTC_DIR.mkdir(parents=True, exist_ok=True)

# 清洗/去重参数（保守，不“清太狠”）
MIN_CHARS = 8
MAX_CHARS = 4000
ENFORCE_LANG = False                      # 先不强制语言过滤，避免误杀
HAMMING_THRESH = 2                        # 近重复阈值（越小越保守）
BUCKET_BITS = 14                          # 分桶位数（越大越少误撞桶）
PERSISTENT_NEAR_DUP = True                # 是否跨文件持久化近重复状态
SIMHASH_STATE = FTC_DIR / "_simhash_buckets.pkl"

# 段落化参数（仅当 PARAGRAPHIZE_AFTER_TRANSCRIBE=True 时使用）
MAX_PARA_CHARS   = 800
PAUSE_THRESHOLD  = 1.3
MERGE_SHORT_SENT = 12

# =====================================================

# 规范化/句法工具（与 paragraphize/clean 的逻辑一致）
_WS = re.compile(r"[ \t\u00A0]+")
_DUP_PUNCT = re.compile(r"([。！？!?…])\1{1,}")
_NONPRINT = "".join(chr(i) for i in range(0x00,0x20) if chr(i) not in ("\n", "\r", "\t"))
_NONPRINT_RE = re.compile(f"[{re.escape(_NONPRINT)}]")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;：:])\s+|[\r\n]+")

def normalize_text(s: str) -> str:
    if not s: return ""
    s = s.replace("\ufeff", "")
    s = unicodedata.normalize("NFKC", s)
    s = _NONPRINT_RE.sub(" ", s)
    s = s.replace("\t", " ")
    s = _WS.sub(" ", s)
    s = _DUP_PUNCT.sub(r"\1", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()

def is_gibberish(s: str) -> bool:
    if not s: return True
    letters = re.findall(r"[A-Za-z\u4e00-\u9fff]", s)
    return (len(letters) / max(1, len(s))) < 0.2 and len(s) < 50

# ---- 段落化（内置轻量实现，避免必须先跑独立模块） ----
def paragraphize_from_jsonl(jsonl_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = jsonl_path.stem
    rows = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                t = normalize_text(d.get("text",""))
                if not t: continue
                rows.append({"start": float(d.get("start") or 0.0), "end": float(d.get("end") or 0.0), "text": t})
            except: 
                continue
    if not rows:
        return out_dir / f"{base}.jsonl"

    # 合并短句（借上下文）
    merged = []
    buf = None
    for r in rows:
        if buf is None:
            buf = r; continue
        if len(buf["text"]) < MERGE_SHORT_SENT and (r["start"] - buf["end"]) < PAUSE_THRESHOLD:
            r = {"start": buf["start"], "end": r["end"], "text": (buf["text"] + " " + r["text"]).strip()}
            buf = r
        else:
            merged.append(buf); buf = r
    if buf: merged.append(buf)

    # 组段
    paras = []
    cur = {"start": None, "end": None, "text": ""}
    last_end = None
    def flush():
        if cur["text"].strip():
            paras.append({"id": str(uuid.uuid4()), "start": cur["start"], "end": cur["end"], "text": cur["text"].strip()})
    for r in merged:
        s = r["text"]
        if not s: continue
        should_break = last_end is not None and (r["start"] - last_end) >= PAUSE_THRESHOLD
        strong_end = bool(re.search(r"[。！？!?]$", cur["text"].strip()))
        will_exceed = len(cur["text"]) + (1 if cur["text"] else 0) + len(s) > MAX_PARA_CHARS
        if cur["text"] and (should_break or will_exceed or (strong_end and len(s) > MERGE_SHORT_SENT)):
            flush(); cur = {"start": None, "end": None, "text": ""}
        if not cur["text"]:
            cur["start"] = r["start"]; cur["text"] = s
        else:
            cur["text"] += ("\n" if len(s) < MERGE_SHORT_SENT else " ") + s
        cur["end"] = r["end"]; last_end = r["end"]
    flush()

    # 写出
    out_jsonl = out_dir / f"{base}.jsonl"
    out_txt   = out_dir / f"{base}.txt"
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for p in paras: f.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(out_txt, "w", encoding="utf-8") as f:
        for p in paras: f.write(p["text"] + "\n\n")
    print(f"   [paragraphize] {base}: {len(paras)} 段 -> {out_jsonl.name}")
    return out_jsonl

# ---- 清洗/去重（含跨文件近重复持久化） ----
from simhash import Simhash
try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
    def lang_ok(s: str, allow=("zh-cn","zh-tw","zh","en")) -> bool:
        try: return detect(s) in allow
        except: return True
except Exception:
    # 没装 langdetect 时，直接视为通过
    def lang_ok(s: str, allow=None) -> bool:
        return True

def simhash_of(s: str) -> int:
    toks = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", s.lower())
    return Simhash(toks).value

def load_simhash_state() -> dict:
    if SIMHASH_STATE.exists():
        try:
            with open(SIMHASH_STATE, "rb") as f:
                return pickle.load(f)
        except Exception:
            return {}
    return {}

def save_simhash_state(state: dict):
    with open(SIMHASH_STATE, "wb") as f:
        pickle.dump(state, f)

def clean_and_write_to_fulltext_clean(ft_txt_path: Optional[Path], ft_jsonl_path: Optional[Path], source_base: str) -> bool:
    """
    读取刚产出的 fulltext（优先 jsonl；退化用 txt 切句），清洗 + 去重（跨文件近重复），
    写到 data/fulltext_clean/<name>.jsonl
    """
    out_fp = FTC_DIR / f"{source_base}.jsonl"

    # 读取为标准行
    rows: List[Dict] = []
    if ft_jsonl_path and ft_jsonl_path.exists():
        with open(ft_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    t = d.get("text") or d.get("chunk") or ""
                    rows.append({
                        "id": d.get("id") or str(uuid.uuid4()),
                        "start": d.get("start"),
                        "end": d.get("end"),
                        "text": t,
                        "source_file": source_base,
                    })
                except Exception:
                    continue
    elif ft_txt_path and ft_txt_path.exists():
        raw = ft_txt_path.read_text(encoding="utf-8", errors="ignore")
        raw = normalize_text(raw)
        sents = [s.strip() for s in _SENT_SPLIT.split(raw) if s and s.strip()]
        for s in sents:
            rows.append({"id": str(uuid.uuid4()), "start": None, "end": None, "text": s, "source_file": source_base})
    else:
        print("   WARN: fulltext 不存在，跳过清洗：" , source_base)
        return False

    # 清洗 + 质量过滤
    cleaned = []
    for d in rows:
        t = normalize_text(d["text"])
        if not t: continue
        if len(t) < MIN_CHARS or len(t) > MAX_CHARS: continue
        if is_gibberish(t): continue
        if ENFORCE_LANG and (not lang_ok(t)): continue
        d["text"] = t
        cleaned.append(d)

    # exact 去重（同文件）
    seen = set(); uniq = []
    for d in cleaned:
        key = d["text"]
        if key in seen: continue
        seen.add(key); uniq.append(d)

    # near-dup 去重（跨文件，全局持久化）
    state = load_simhash_state() if PERSISTENT_NEAR_DUP else {}
    bucket_mask = (1 << BUCKET_BITS) - 1
    out = []
    for d in uniq:
        h = simhash_of(d["text"])
        b = h & bucket_mask
        s = state.setdefault(b, set())
        hit = False
        for x in s:
            if bin(x ^ h).count("1") <= HAMMING_THRESH:
                hit = True; break
        if hit: 
            continue
        s.add(h)
        out.append(d)

    # 写出
    with open(out_fp, "w", encoding="utf-8") as f:
        for d in out:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    if PERSISTENT_NEAR_DUP:
        save_simhash_state(state)

    print(f"   [clean] {source_base}: {len(rows)} -> {len(out)}   -> {out_fp.name}")
    return out_fp.exists()

# ---- 主流程：逐个 WAV 转录 →（可选段落化）→ 清洗 → 触发后续 ----
def transcribe_all():
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("请先安装 faster-whisper： pip install faster-whisper ctranslate2")
        raise

    print(f"[Transcribe] Using Whisper model: {MODEL}  cpu_threads={CPU_THREADS}")
    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS)

    wavs = sorted(glob.glob(str(AUDIO_DIR / "*.wav")))
    print("Found", len(wavs), "wav files")

    done = 0
    for w in wavs:
        base = Path(w).stem
        ft_txt  = FT_DIR / f"{base}.txt"
        ft_json = FT_DIR / f"{base}.jsonl"
        ftc_json = FTC_DIR / f"{base}.jsonl"

        # 断点：如果 fulltext_clean 已存在，就认为该文件已完成整链（除非手动删除重跑）
        if ftc_json.exists():
            print("skip (fulltext_clean exists):", base)
            continue

        FT_DIR.mkdir(parents=True, exist_ok=True)
        print(f">> transcribing: {base}")
        try:
            segments, info = model.transcribe(
                w,
                language="zh",
                vad_filter=VAD_FILTER,
                beam_size=BEAM_SIZE,
                word_timestamps=WORD_TIMESTAMPS
            )
            last = 0.0
            with open(ft_txt, "w", encoding="utf-8") as ft, open(ft_json, "w", encoding="utf-8") as fj:
                for s in segments:
                    t = s.text.strip()
                    ft.write(t + "\n")
                    fj.write(json.dumps(
                        {"id": str(uuid.uuid4()), "start": s.start, "end": s.end, "text": t, "source_file": base},
                        ensure_ascii=False
                    ) + "\n")
                    if s.end - last >= 10:
                        print(f"   progress: {s.end:7.2f}s"); sys.stdout.flush()
                        last = s.end
            print("   transcribe done:", base)

            # —— 可选：段落化（改善口述为文章段） ——
            para_jsonl = None
            if PARAGRAPHIZE_AFTER_TRANSCRIBE:
                PARA_DIR.mkdir(parents=True, exist_ok=True)
                para_jsonl = paragraphize_from_jsonl(ft_json, PARA_DIR)

            # —— 清洗 + 去重 → 写入 fulltext_clean ——
            src_jsonl = para_jsonl if para_jsonl else ft_json
            ok = clean_and_write_to_fulltext_clean(ft_txt, src_jsonl, base)
            if not ok:
                print("   WARN: clean step produced no output; skipping pipeline/index for", base)

            # —— （可选）立刻跑 pipeline（只盯 fulltext_clean）——
            if RUN_PIPELINE_AFTER_EACH and ok:
                try:
                    subprocess.run([sys.executable, "-m", "src.ingest.pipeline", "--transcripts", str(FTC_DIR)], check=False)
                    print("   pipeline updated.")
                except Exception as e:
                    print("   WARN: pipeline failed:", e, file=sys.stderr)

            done += 1
            # —— （可选）节流刷索引 —— 
            if RUN_BUILD_INDEX_EVERY_N and (done % RUN_BUILD_INDEX_EVERY_N == 0):
                try:
                    subprocess.run([sys.executable, "-m", "src.index.build_index", "--mode", BUILD_INDEX_MODE], check=False)
                    print(f"   index refreshed ({BUILD_INDEX_MODE}).")
                except Exception as e:
                    print("   WARN: index build failed:", e, file=sys.stderr)

        except KeyboardInterrupt:
            print("\n[Ctrl-C] interrupted by user.")
            break
        except Exception as e:
            print("   ERROR:", base, "->", e, file=sys.stderr)
            # 不中断，继续下一个

    # 兜底：收尾再跑一遍 pipeline 和索引
    if RUN_PIPELINE_AFTER_EACH:
        try:
            subprocess.run([sys.executable, "-m", "src.ingest.pipeline", "--transcripts", str(FTC_DIR)], check=False)
        except Exception as e:
            print("WARN: final pipeline failed:", e, file=sys.stderr)
    if RUN_BUILD_INDEX_EVERY_N:
        try:
            subprocess.run([sys.executable, "-m", "src.index.build_index", "--mode", BUILD_INDEX_MODE], check=False)
            print("All done. Index refreshed.")
        except Exception as e:
            print("WARN: final index build failed:", e, file=sys.stderr)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--threads", type=int, default=CPU_THREADS)
    ap.add_argument("--no-paragraphize", action="store_true")
    ap.add_argument("--no-pipeline", action="store_true")
    ap.add_argument("--refresh-index-n", type=int, default=RUN_BUILD_INDEX_EVERY_N)
    ap.add_argument("--index-mode", default=BUILD_INDEX_MODE)
    args = ap.parse_args()

    global MODEL, CPU_THREADS, PARAGRAPHIZE_AFTER_TRANSCRIBE
    global RUN_PIPELINE_AFTER_EACH, RUN_BUILD_INDEX_EVERY_N, BUILD_INDEX_MODE

    MODEL = args.model
    CPU_THREADS = args.threads
    PARAGRAPHIZE_AFTER_TRANSCRIBE = not args.no_paragraphize
    RUN_PIPELINE_AFTER_EACH = not args.no_pipeline
    RUN_BUILD_INDEX_EVERY_N = args.refresh_index_n
    BUILD_INDEX_MODE = args.index_mode

    transcribe_all()

if __name__ == "__main__":
    main()
