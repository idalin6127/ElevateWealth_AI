# tools/rebuild_paragraphs.py
# 作用：用最新的 data/fulltext_clean/*.jsonl（优先）或 *.txt 重建 data/paragraphs/*.jsonl
# 场景：你已有 batch_transcribe_fulltext.py 产生的 JSONL；paragraphs 需跟随 fulltext_clean 更新
#
# 逻辑：
# 1) 优先读取 data/fulltext_clean/*.jsonl；若无 → 读取 data/fulltext/*.jsonl
# 2) 若上述都无 JSONL，则回退读取 *.txt（clean 优先）
# 3) JSONL 每行尝试字段：text / paragraph / content / body / lines（list）
# 4) 如行里已有 cid/id，尽量继承；否则生成: <base>-0001 这种稳定编号
# 5) 根据 minlen/maxlen 做“合并短段/切分长段”，保证检索友好
# 6) 输出到 data/paragraphs/<base>.jsonl，行结构：{"cid","src","text"}

import os, re, glob, json, argparse
from pathlib import Path
from typing import List, Dict, Any

SRC_CLEAN = Path("data/fulltext_clean")
SRC_RAW   = Path("data/fulltext")
OUT_DIR   = Path("data/paragraphs")

def normalize_text(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def read_jsonl_fields(obj: Dict[str, Any]) -> str:
    """
    从一条 JSON 记录里抽文本。按优先级尝试：
    text > paragraph > content > body > lines(list[str]) 合并
    """
    keys = ["text", "paragraph", "content", "body"]
    for k in keys:
        if isinstance(obj.get(k), str) and obj.get(k).strip():
            return normalize_text(obj[k])
    if isinstance(obj.get("lines"), list):
        joined = "\n".join([x for x in obj["lines"] if isinstance(x, str)])
        if joined.strip():
            return normalize_text(joined)
    # 部分转录器可能把文本放在 data.text
    data = obj.get("data")
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), str) and data.get(k).strip():
                return normalize_text(data[k])
    return ""

def split_paragraphs(txt: str, min_len: int, max_len: int) -> List[str]:
    """
    基础切分策略：
    - 先按“空行”切段；
    - < min_len 的短段累积合并；
    - > max_len 的长段硬切；
    - 清洗多余空白。
    """
    # 先按空行切
    paras = [p.strip() for p in re.split(r"\n{2,}", txt) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(p) < min_len:
            buf = (buf + " " + p).strip()
            if len(buf) >= min_len:
                out.append(buf[:max_len])
                buf = ""
        elif len(p) > max_len:
            chunk = p
            while len(chunk) > max_len:
                out.append(chunk[:max_len])
                chunk = chunk[max_len:]
            if chunk.strip():
                out.append(chunk.strip())
        else:
            out.append(p)
    if buf:
        out.append(buf)
    out = [re.sub(r"\s+", " ", x).strip() for x in out if x.strip()]
    return out

def iter_sources():
    """返回 (模式, 路径列表, 源目录路径)。模式: 'jsonl' 或 'txt'"""
    # 优先 JSONL（clean 优先）
    jsonl_clean = sorted(SRC_CLEAN.glob("*.jsonl"))
    if jsonl_clean:
        return "jsonl", jsonl_clean, SRC_CLEAN
    jsonl_raw = sorted(SRC_RAW.glob("*.jsonl"))
    if jsonl_raw:
        return "jsonl", jsonl_raw, SRC_RAW
    # 回退到 txt
    txt_clean = sorted(SRC_CLEAN.glob("*.txt"))
    if txt_clean:
        return "txt", txt_clean, SRC_CLEAN
    txt_raw = sorted(SRC_RAW.glob("*.txt"))
    if txt_raw:
        return "txt", txt_raw, SRC_RAW
    return None, [], None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="源目录（默认优先 fulltext_clean 再 fulltext）")
    ap.add_argument("--out", default=str(OUT_DIR), help="输出目录 data/paragraphs")
    ap.add_argument("--minlen", type=int, default=80, help="段落最短字符，短段会被合并")
    ap.add_argument("--maxlen", type=int, default=800, help="段落最长字符，超长会被切块")
    ap.add_argument("--assume_ready", action="store_true",
                    help="如果 JSONL 每行已是段落级，不再二次切分，仅做清洗与编号补全。")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    mode, files, auto_src = iter_sources()
    if args.src:
        base = Path(args.src)
        if not base.exists():
            raise SystemExit(f"源目录不存在：{base}")
        # 自动探测模式
        if list(base.glob("*.jsonl")):
            mode, files, auto_src = "jsonl", sorted(base.glob("*.jsonl")), base
        elif list(base.glob("*.txt")):
            mode, files, auto_src = "txt", sorted(base.glob("*.txt")), base
        else:
            raise SystemExit(f"源目录下没有 .jsonl 或 .txt：{base}")
    else:
        if mode is None:
            raise SystemExit("未找到可用源文件。请确保 data/fulltext_clean/ 或 data/fulltext/ 下存在 .jsonl 或 .txt")

    print(f"[INFO] 源模式: {mode}  源目录: {auto_src}  文件数: {len(files)}")
    total = 0

    for fp in files:
        base = fp.stem
        out_jsonl = out_dir / f"{base}.jsonl"
        written = 0

        if mode == "jsonl":
            with open(fp, "r", encoding="utf-8", errors="ignore") as r, \
                 open(out_jsonl, "w", encoding="utf-8") as w:
                idx = 0
                for line in r:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    # 先尽量复用已有 id/cid
                    cid = (obj.get("cid") or obj.get("id") or "").strip()
                    text = read_jsonl_fields(obj)
                    if not text:
                        continue
                    if args.assume_ready:
                        # 行本身就是段落：仅规范化、补编号
                        idx += 1
                        if not cid:
                            cid = f"{base}-{idx:04d}"
                        w.write(json.dumps({"cid": cid, "src": base + ".jsonl", "text": text}, ensure_ascii=False) + "\n")
                        written += 1
                    else:
                        # 行里可能是篇章/大块：再切分为段
                        parts = split_paragraphs(text, args.minlen, args.maxlen)
                        for p in parts:
                            idx += 1
                            cid_use = cid or f"{base}-{idx:04d}"
                            # 为避免同一 cid 多段，这里用序号
                            if cid:
                                cid_use = f"{cid}-{idx:04d}"
                            w.write(json.dumps({"cid": cid_use, "src": base + ".jsonl", "text": p}, ensure_ascii=False) + "\n")
                            written += 1

        else:  # txt
            with open(fp, "r", encoding="utf-8", errors="ignore") as r:
                raw = r.read()
            text = normalize_text(raw)
            parts = split_paragraphs(text, args.minlen, args.maxlen)
            with open(out_jsonl, "w", encoding="utf-8") as w:
                for i, p in enumerate(parts, 1):
                    cid = f"{base}-{i:04d}"
                    w.write(json.dumps({"cid": cid, "src": base + ".txt", "text": p}, ensure_ascii=False) + "\n")
                    written += 1

        total += written
        print(f"[OK] {fp.name} → {out_jsonl}  段落数: {written}")

    print(f"完成：共输出段落 {total} 条 → {out_dir}")

if __name__ == "__main__":
    main()
