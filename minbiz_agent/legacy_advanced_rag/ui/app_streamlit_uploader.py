import io, requests, os, base64
import streamlit as st

BACKEND = os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000")
API_KEY = os.getenv("MINBIZ_API_KEY", "devkey")

st.set_page_config(page_title="MinBiz Voice (Uploader)", page_icon="🎤", layout="centered")
st.title("🎤 Browser Mic (Uploader)")

st.write("点击下方录音按钮录音，或直接上传 .wav/.mp3。录完后会把音频发到后端 `/ask-voice-v2`。")

# 方式1：用一个轻量录音组件（不需要 webrtc）
try:
    from streamlit_mic_recorder import mic_recorder, speech_to_text
    audio = mic_recorder(start_prompt="Start", stop_prompt="Stop", key="rec", format="wav")
    uploaded = st.file_uploader("或上传音频文件", type=["wav", "mp3", "m4a"])
    data = audio["bytes"] if audio else (uploaded.read() if uploaded else None)
except Exception:
    st.info("未安装 `streamlit-mic-recorder`，请先 `pip install streamlit-mic-recorder`，临时改用纯上传。")
    uploaded = st.file_uploader("上传音频文件", type=["wav", "mp3", "m4a"])
    data = uploaded.read() if uploaded else None

style = st.selectbox("Voice style", options=["story","concise","coach"], index=0)
lang  = st.selectbox("Voice lang", options=["auto","zh","en"], index=0)
bilingual = st.checkbox("Voice bilingual", value=False)

if st.button("Send to backend") and data:
    with st.spinner("Calling backend..."):
        resp = requests.post(
            f"{BACKEND}/ask-voice-v2",
            headers={"X-API-Key": API_KEY},
            files={"audio": ("voice.wav", data, "audio/wav")},
            data={"style": style, "lang": lang, "bilingual": str(bilingual).lower()},
            timeout=120,
        )
    st.write("Status:", resp.status_code)
    st.json(resp.json())
    if resp.ok:
        js = resp.json()
        st.subheader("Answer")
        st.write(js.get("answer"))
        # 播放第一段音频
        segs = js.get("audio_segments_b64") or []
        if segs:
            st.audio(io.BytesIO(base64.b64decode(segs[0])), format="audio/mp3")
else:
    st.info("录音或上传一个音频，然后点 Send to backend")
