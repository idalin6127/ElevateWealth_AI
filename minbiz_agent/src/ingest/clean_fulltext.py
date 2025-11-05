# src/ingest/clean_fulltext.py
import os, re, json, glob, argparse, unicodedata, uuid, pickle
from pathlib import Path
from langdetect import detect, DetectorFactory
from simhash import Simhash
DetectorFactory.seed = 0

_ws = re.compile(r"[ \t\u00A0]+")
_dup_punct = re.compile(r"([。！？!?…])\1{1,}")
_nonprint = "".join(chr(i) for i in range(0x00,0x20) if chr(i) not in ("\n", "\r", "\t"))
_nonprint_re = re.compile(f"[{re.escape(_nonprint)}]")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?])\s+|[\r\n]+")

def normalize_text(s:str)->str:
    if not s: return ""
    s = s.replace("\ufeff","")
    s = unicodedata.normalize("NFKC", s)
    s = _nonprint_re.sub(" ", s)
    s = s.replace("\t"," ")
    s = _ws.sub(" ", s)
    s = _dup_punct.sub(r"\1", s)
    s = re.sub(r"\s*\n\s*","\n", s)
    return s.strip()

def is_gibberish(s:str)->bool:
    if not s: return True
    letters = re.findall(r"[A-Za-z\u4e00-\u9fff]", s)
    return (len(letters)/max(1,len(s))) < 0.2 and len(s) < 50

def lang_ok(s:str, allow=("zh-cn","zh-tw","zh","en"))->bool:
    try: return detect(s) in allow
    except: return True

def simhash_of(s:str)->int:
    toks = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", s.lower())
    return Simhash(toks).value

def yield_rows_from_path(fp:Path):
    if fp.suffix.lower()==".jsonl":
        with open(fp,"r",encoding="utf-8") as f:
            for line in f:
                try:
                    d=json.loads(line)
                    yield {
                        "id": d.get("id") or str(uuid.uuid4()),
                        "start": d.get("start"),
                        "end": d.get("end"),
                        "text": (d.get("text") or d.get("chunk") or ""),
                        "source_file": d.get("source_file") or fp.stem,
                    }
                except: continue
    else:
        raw = normalize_text(fp.read_text(encoding="utf-8", errors="ignore"))
        sents = [s.strip() for s in _SENT_SPLIT.split(raw) if s and s.strip()]
        for s in sents:
            yield {"id":str(uuid.uuid4()),"start":None,"end":None,"text":s,"source_file":fp.stem}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="in_dir",default="data/paragraphs")
    ap.add_argument("--out",dest="out_dir",default="data/fulltext_clean")
    ap.add_argument("--min_chars",type=int,default=8)
    ap.add_argument("--max_chars",type=int,default=4000)
    ap.add_argument("--enforce_lang",action="store_true")
    ap.add_argument("--hamming_thresh",type=int,default=2)
    ap.add_argument("--bucket_bits",type=int,default=14)
    ap.add_argument("--no_persistent_near_dup",action="store_true")
    args=ap.parse_args()

    in_dir=Path(args.in_dir); out_dir=Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    files=[Path(p) for p in sorted(glob.glob(str(in_dir/"*.*"))) if Path(p).suffix.lower() in (".jsonl",".txt")]
    if not files: print("[clean] 空输入：",in_dir); return

    state_fp = out_dir / "_simhash_buckets.pkl"
    state = {} if args.no_persistent_near_dup else (pickle.load(open(state_fp,"rb")) if state_fp.exists() else {})
    bucket_mask = (1<<args.bucket_bits)-1

    total_in=total_out=0
    for i,fp in enumerate(files,1):
        rows=[]
        for d in yield_rows_from_path(fp):
            t = normalize_text(d["text"])
            if not t: continue
            if len(t) < args.min_chars or len(t) > args.max_chars: continue
            if is_gibberish(t): continue
            if args.enforce_lang and (not lang_ok(t)): continue
            d["text"]=t; rows.append(d)
        # exact 去重
        seen=set(); uniq=[]
        for d in rows:
            key=d["text"]
            if key in seen: continue
            seen.add(key); uniq.append(d)
        # near-dup（跨文件）
        out=[]
        for d in uniq:
            h=simhash_of(d["text"]); b=h & bucket_mask
            s=state.setdefault(b,set())
            hit=False
            for x in s:
                if bin(x ^ h).count("1") <= args.hamming_thresh:
                    hit=True; break
            if hit: continue
            s.add(h); out.append(d)
        # 写出
        with open(out_dir/f"{fp.stem}.jsonl","w",encoding="utf-8") as f:
            for d in out:
                f.write(json.dumps(d,ensure_ascii=False)+"\n")
        total_in += len(rows); total_out += len(out)
        print(f"[clean] {i}/{len(files)} {fp.name}: {len(rows)} -> {len(out)}")
    if not args.no_persistent_near_dup:
        pickle.dump(state, open(state_fp,"wb"))
    print(f"[clean] DONE {total_in} -> {total_out} -> {out_dir}")

if __name__=="__main__": main()
