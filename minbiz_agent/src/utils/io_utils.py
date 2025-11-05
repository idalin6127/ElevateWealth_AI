import os, json

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def write_jsonl(path: str, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def read_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

def list_media_files(folder: str):
    exts = (".mp4", ".mov", ".mkv", ".m4a", ".mp3", ".wav")
    files = []
    for root, _, fns in os.walk(folder):
        for fn in fns:
            if fn.lower().endswith(exts):
                files.append(os.path.join(root, fn))
    return files

def list_files_with_suffix(folder: str, suffix: str):
    return [os.path.join(folder, fn) for fn in os.listdir(folder) if fn.endswith(suffix)]
