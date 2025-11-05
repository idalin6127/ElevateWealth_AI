# src/ui/app_streamlit_webrtc.py
# -*- coding: utf-8 -*-
import os, io, json, time, wave, base64, requests
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from streamlit_webrtc import webrtc_streamer, WebRtcMode, AudioProcessorBase

load_dotenv()
st.set_page_config(page_title="MinBiz Voice Agent (WebRTC)", page_icon="🎙️", layout="centered")

# ====== 后端配置 ======
API_BASE = os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000")
API_KEY  = os.getenv("MINBIZ_API_KEY", "")
HEADERS  = {"X-API-Key": API_KEY} if API_KEY else {}
ICE_JSON = os.getenv("WEBRTC_ICE_JSON", "").strip()

RTC_CONFIG = json.loads(ICE_JSON) if ICE_JSON else {
    "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
}

with st.expander("Connection diagnostics", expanded=False):
    st.json({"API_BASE": API_BASE, "API_KEY_present": bool(API_KEY), "RTC_CONFIG": RTC_CONFIG})

st.title("🎙️ MinBiz Voice Agent (WebRTC)")

# ====== 文本问答（可选） ======
st.subheader("💬 Ask by text")
col1, col2, col3 = st.columns(3)
with col1:
    style = st.selectbox("Style", ["story", "concise", "coach"], index=0)
with col2:
    lang  = st.selectbox("Language", ["auto", "en", "zh"], index=0)
with col3:
    bilingual = st.toggle("Bilingual (中英双语)", value=False)
text_q = st.text_area("Your question", value="", height=80, placeholder="Type here and click Ask")
if st.button("Ask"):
    try:
        r = requests.post(
            f"{API_BASE}/ask-text-v2",
            headers=HEADERS,
            data={"q": text_q, "style": style, "lang": lang, "bilingual": str(bilingual).lower()},
            timeout=180
        )
        r.raise_for_status()
        out = r.json()
        st.success("Answer")
        st.write(out.get("answer") or out)

        # 如果后端也返回了TTS分段，顺便播一下
        segs = out.get("audio_segments_b64") or []
        if segs:
            fmt = "audio/mp3" if out.get("audio_format") == "mp3" else "audio/wav"
            for i, b64 in enumerate(segs, 1):
                st.audio(io.BytesIO(base64.b64decode(b64)), format=fmt)
    except Exception as e:
        st.error(f"Text ask failed: {e}")

st.divider()

# ====== 语音问答（WebRTC 录音） ======
st.subheader("🎙️ Browser Mic (WebRTC)")
st.caption("点击 Start 建立连接，说话后点击 Stop & Submit 提交。若无法连接，多半需要配置 TURN 服务器。")

if "webrtc_pcm" not in st.session_state:
    st.session_state["webrtc_pcm"] = []

class AudioCollector(AudioProcessorBase):
    """把每一帧音频转成 int16 单声道 PCM 缓冲到 session_state"""
    def __init__(self) -> None:
        # 初始化缓冲
        if "webrtc_pcm" not in st.session_state:
            st.session_state["webrtc_pcm"] = []

    def recv(self, frame):
        pcm = frame.to_ndarray()  # shape: (channels, samples)
        if pcm.ndim == 2:
            pcm = pcm[0]
        pcm = pcm.astype(np.int16)
        st.session_state["webrtc_pcm"].append(pcm.tobytes())
        return frame  # 必须回传

ctx = webrtc_streamer(
    key="minbiz-voice",
    mode=WebRtcMode.SENDONLY,
    audio_receiver_size=1024,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration=RTC_CONFIG,
    audio_processor_factory=AudioCollector,
)

# 参数
c1, c2, c3 = st.columns(3)
with c1:
    v_style = st.selectbox("Voice style", ["story", "concise", "coach"], index=0)
with c2:
    v_lang  = st.selectbox("Voice lang", ["auto", "en", "zh"], index=0)
with c3:
    v_bilingual = st.toggle("Voice bilingual", value=False)

def pcm_chunks_to_wav(chunks: list[bytes], sample_rate=16000) -> bytes:
    pcm = b"".join(chunks)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)         # int16
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return bio.getvalue()

# 提交按钮
if st.button("Stop & Submit", type="primary"):
    try:
        chunks = st.session_state.get("webrtc_pcm", [])
        if not chunks:
            st.warning("还没有采集到音频。请先 Start 连接成功后再说话，然后再点 Submit。")
        else:
            wav_bytes = pcm_chunks_to_wav(chunks, sample_rate=16000)
            files = {"audio": ("voice.wav", wav_bytes, "audio/wav")}
            data  = {"style": v_style, "lang": v_lang, "bilingual": str(v_bilingual).lower()}
            r = requests.post(f"{API_BASE}/ask-voice-v2", headers=HEADERS, files=files, data=data, timeout=180)
            r.raise_for_status()
            out = r.json()

            st.success("ASR Transcript")
            st.write(out.get("question", ""))

            st.success("Answer")
            st.write(out.get("answer", ""))

            segs = out.get("audio_segments_b64") or []
            if segs:
                fmt = "audio/mp3" if out.get("audio_format") == "mp3" else "audio/wav"
                for i, b64 in enumerate(segs, 1):
                    st.audio(io.BytesIO(base64.b64decode(b64)), format=fmt)

            # 清空缓冲，避免下次把上一次的内容混进去
            st.session_state["webrtc_pcm"] = []
    except Exception as e:
        st.error(f"Voice submit failed: {e}")
