# src/ingest/paragraphize.py
import os, re, json, glob, argparse, unicodedata, uuid
from pathlib import Path

_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;：:])\s+|[\r\n]+")
_WS = re.compile(r"[ \t\u00A0]+")
_DUP_PUNCT = re.compile(r"([。！？!?…])\1{1,}")
_NONPRINT = "".join(chr(i) for i in range(0x00,0x20) if chr(i) not in ("\n", "\r", "\t"))
_NONPRINT_RE = re.compile(f"[{re.escape(_NONPRINT)}]")
FILLERS = ["嗯","呃","額","诶","欸","啊","哈","喔","哦","哎","這個","这个","就是","那個","那个","然後","然后","好吧","好嗎","好吗","OK","ok","對吧","对吧","你知道","我跟你說","我跟你说","其實","其实"]
FILLER_RE = re.compile(r"^(%s)[，,。.！!？?\s]*$" % "|".join(map(re.escape, FILLERS)))

def norm(s:str)->str:
    if not s: return ""
    s = s.replace("\ufeff","")
    s = unicodedata.normalize("NFKC", s)
    s = _NONPRINT_RE.sub(" ", s)
    s = s.replace("\t"," ")
    s = _WS.sub(" ", s)
    s = _DUP_PUNCT.sub(r"\1", s)
    s = re.sub(r"\s*\n\s*","\n",s)
    return s.strip()

def is_pure_filler(s:str)->bool:
    return bool(FILLER_RE.match(s.strip()))

def load_jsonl(fp:Path):
    rows=[]
    with open(fp,"r",encoding="utf-8") as f:
        for line in f:
            try:
                d=json.loads(line); t=norm(d.get("text",""))
                if not t or is_pure_filler(t): continue
                rows.append({"start":float(d.get("start") or 0.0),"end":float(d.get("end") or 0.0),"text":t})
            except: continue
    return rows

def load_txt(fp:Path):
    raw = norm(fp.read_text(encoding="utf-8", errors="ignore"))
    sents = [s.strip() for s in _SENT_SPLIT.split(raw) if s and s.strip()]
    rows=[]; t=0.0
    for s in sents:
        rows.append({"start":t,"end":t+2.0,"text":s}); t+=2.0
    return rows

def to_paragraphs(rows, max_para_chars=800, pause_threshold=1.3, merge_short=12):
    paras=[]; cur={"start":None,"end":None,"text":""}; last_end=None
    def flush():
        if cur["text"].strip():
            paras.append({"id":str(uuid.uuid4()),"start":cur["start"],"end":cur["end"],"text":cur["text"].strip()})
    for r in rows:
        s=r["text"]; 
        if not s: continue
        should_break = last_end is not None and (r["start"] - last_end) >= pause_threshold
        strong_end = bool(re.search(r"[。！？!?]$", cur["text"].strip()))
        will_exceed = len(cur["text"])+(1 if cur["text"] else 0)+len(s) > max_para_chars
        if cur["text"] and (should_break or will_exceed or (strong_end and len(s) > merge_short)):
            flush(); cur={"start":None,"end":None,"text":""}
        if not cur["text"]:
            cur["start"]=r["start"]; cur["text"]=s
        else:
            cur["text"] += ("\n" if len(s)<merge_short else " ") + s
        cur["end"]=r["end"]; last_end=r["end"]
    flush(); return paras

def process_file(src:Path,out_dir:Path,args):
    rows = load_jsonl(src) if src.suffix.lower()==".jsonl" else load_txt(src)
    if not rows: return 0
    # 合并短句（先借上下文）
    merged=[]; buf=None
    for r in rows:
        if buf is None: buf=r; continue
        if len(buf["text"])<args.merge_short and (r["start"]-buf["end"])<args.pause_threshold:
            r={"start":buf["start"],"end":r["end"],"text":(buf["text"]+" "+r["text"]).strip()}
            buf=r
        else:
            merged.append(buf); buf=r
    if buf: merged.append(buf)
    paras = to_paragraphs(merged,args.max_para_chars,args.pause_threshold,args.merge_short)
    out_dir.mkdir(parents=True, exist_ok=True)
    base=src.stem; j=out_dir/f"{base}.jsonl"; t=out_dir/f"{base}.txt"
    with open(j,"w",encoding="utf-8") as f:
        for p in paras: f.write(json.dumps(p,ensure_ascii=False)+"\n")
    with open(t,"w",encoding="utf-8") as f:
        for p in paras: f.write(p["text"]+"\n\n")
    return len(paras)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="in_dir",default="data/fulltext")
    ap.add_argument("--out",dest="out_dir",default="data/paragraphs")
    ap.add_argument("--max-para-chars",type=int,default=800)
    ap.add_argument("--pause-threshold",type=float,default=1.3)
    ap.add_argument("--merge-short",type=int,default=12)
    args=ap.parse_args()
    in_dir=Path(args.in_dir); out_dir=Path(args.out_dir)
    files=[Path(p) for p in sorted(glob.glob(str(in_dir/"*.*"))) if Path(p).suffix.lower() in (".jsonl",".txt")]
    if not files: print("[paragraphize] 空输入：",in_dir); return
    total=0
    for i,fp in enumerate(files,1):
        n=process_file(fp,out_dir,args)
        print(f"[paragraphize] {i}/{len(files)} {fp.name} -> {n} 段"); total+=n
    print(f"[paragraphize] DONE -> {out_dir} 共 {total} 段")
if __name__=="__main__": main()
