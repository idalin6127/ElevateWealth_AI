"""
Fulltext transcription archiver
- Reads media in data/raw_videos/
- Extracts wav (16k mono) and transcribes with faster-whisper
- Writes:
    data/fulltext/{video_stem}.jsonl  (segment-level with timestamps)
    data/fulltext/{video_stem}.txt     (concatenated plain text)

NOTE: Fulltext is for your private archive ONLY.
Do NOT index or share; pipeline.py still builds PII-redacted chunks for retrieval.
"""
import os, argparse, pathlib, subprocess, uuid
from faster_whisper import WhisperModel
from src.utils.io_utils import ensure_dir, list_media_files, write_jsonl

def extract_audio(video_path: str, out_dir: str) -> str:
    ensure_dir(out_dir)
    base = pathlib.Path(video_path).stem
    out_wav = os.path.join(out_dir, f"{base}.wav")
    cmd = ["ffmpeg", "-y", "-i", video_path, "-ac", "1", "-ar", "16000", out_wav]
    subprocess.run(cmd, check=True)
    return out_wav

def transcribe_file(wav_path: str, model_name: str="medium", device: str="cpu", language: str=None):
    model = WhisperModel(model_name, device=device, compute_type="int8")
    segments, info = model.transcribe(wav_path, language=language, vad_filter=True)
    for seg in segments:
        yield {
            "id": str(uuid.uuid4()),
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip()
        }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_videos", default="data/raw_videos")
    ap.add_argument("--audio_out", default="data/audio")
    ap.add_argument("--fulltext_out", default="data/fulltext")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--language", default=None)
    args = ap.parse_args()

    ensure_dir(args.fulltext_out)
    files = list_media_files(args.raw_videos)
    if not files:
        print("No media in", args.raw_videos); return

    for vid in files:
        print(">> Transcribing (fulltext)", vid)
        wav = extract_audio(vid, args.audio_out)
        rows = list(transcribe_file(wav, model_name=args.model, device=args.device, language=args.language))

        base = pathlib.Path(vid).stem
        jsonl_path = os.path.join(args.fulltext_out, base + ".jsonl")
        txt_path = os.path.join(args.fulltext_out, base + ".txt")
        write_jsonl(jsonl_path, rows)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(r["text"] for r in rows))
        print("Saved:", jsonl_path, "and", txt_path)

    print("Fulltext transcription complete. Keep PRIVATE.")

if __name__ == "__main__":
    main()
