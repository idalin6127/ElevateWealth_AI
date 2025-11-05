from faster_whisper import WhisperModel
import sys, os, glob, time

wav = sorted(glob.glob(r"data/audio/*.wav"))[0]  # 改成具体文件也可以
print("test file:", os.path.basename(wav))
m = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)

t_last = 0.0
acc = 0.0
segments, info = m.transcribe(
    wav,
    language="zh",
    vad_filter=False,
    beam_size=1,
    word_timestamps=False
)
for s in segments:
    acc = s.end
    if acc - t_last >= 10:
        print(f"progress: {acc:7.2f}s")
        sys.stdout.flush()
        t_last = acc
print("OK up to:", acc, "seconds")
