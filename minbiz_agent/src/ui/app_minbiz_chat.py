# -*- coding: utf-8 -*-
# src/ui/app_minbiz_chat.py — Minimal Chat UI (English default) + RAG + STT + TTS
import os
import uuid
import requests
import streamlit as st
from contextlib import suppress
import time
from requests.exceptions import ReadTimeout, ConnectionError
import pathlib, sys


API_TIMEOUT = 60  # 降低到 60s，更快失败更早重试

# 确保能导入 src.shared
ROOT = pathlib.Path(__file__).resolve().parents[3]  # 定位到 ElevateWealthAI 根（视你的层级调整）
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from shared.router import goto
from shared.context import get_financial_summary

def post_json_with_retry(url, *, json=None, data=None, files=None, headers=None, timeout=API_TIMEOUT, tries=2):
    last = None
    for i in range(tries):
        try:
            r = requests.post(url, json=json, data=data, files=files, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except (ReadTimeout, ConnectionError) as e:
            last = e
            time.sleep(1.2 * (i+1))  # 退避
        except Exception as e:
            last = e
            break
    raise last


# ---------- Page ----------
def render_minbiz_ui():
    st.title("Startup Companion")
    st.caption("Ask like you're talking to a consultant. It remembers context and uses your RAG knowledge base.")
    summary = get_financial_summary()            # ← 替代直接 st.session_state 读取

    API_BASE = os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000")
    API_KEY  = os.getenv("MINBIZ_API_KEY", "devkey")
    SHOW_SETTINGS = os.getenv("SHOW_SETTINGS", "0") == "1"  # set 1 during dev only
    headers = {"x-api-key": API_KEY}



    # ---------- Dev-only settings ----------
    if SHOW_SETTINGS:
        with st.expander("⚙️ Developer Settings", expanded=False):
            API_BASE = st.text_input("API Base", API_BASE)
            API_KEY  = st.text_input("X-API-Key", API_KEY)
            headers = {"x-api-key": API_KEY}
            st.info("Hide this by unsetting SHOW_SETTINGS or setting it to 0.")

    # ---------- Session ----------
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())[:8]
    if "messages" not in st.session_state:
        st.session_state.messages = []  # [{'role': 'user'|'assistant', 'content': str, 'evidence': list, 'audio': bytes?}]
    # Initialize flags BEFORE widgets to avoid Streamlit key conflicts
    if "show_ev" not in st.session_state:
        st.session_state.show_ev = False
    if "tts_enabled" not in st.session_state:
        st.session_state.tts_enabled = False

    # ---------- History ----------
    _show_ev = st.session_state.show_ev
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if _show_ev and m["role"] == "assistant" and m.get("evidence"):
                with st.expander("Show RAG evidence"):
                    st.json(m["evidence"])
            if m.get("audio"):
                st.audio(m["audio"], format="audio/mp3")

    # ---------- Input Area (toolbar + input + handling) ----------
    # Toolbar glued to input: Show evidence / TTS / Voice input
    _recorder_ok = False
    with suppress(Exception):
        from audio_recorder_streamlit import audio_recorder  # pip install audio-recorder-streamlit
        _recorder_ok = True

    bar = st.container()
    with bar:
        st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.26, 0.26, 0.48])
        c1.checkbox("🧩 Show RAG evidence", value=st.session_state.show_ev, key="show_ev")
        c2.checkbox("🔊 Speak answer (TTS)", value=st.session_state.tts_enabled, key="tts_enabled")

        audio_bytes = None
        if _recorder_ok:
            with c3:
                audio_bytes = audio_recorder(text="🎙️ Voice input", icon_size="1.2x")

    # If voice recorded, call STT to get a draft
    default_prompt = (
        st.session_state.pop("__draft_from_voice__", "")
        if "__draft_from_voice__" in st.session_state else ""
    )
    if audio_bytes:
        try:
            url_stt = API_BASE.rstrip("/") + "/stt-openai"
            files = {"file": ("voice.wav", audio_bytes, "audio/wav")}
            rr = post_json_with_retry(url_stt, files=files, headers=headers, timeout=180)
            rr.raise_for_status()
            stt_text = rr.json().get("text", "")
            if stt_text:
                st.session_state["__draft_from_voice__"] = stt_text
                default_prompt = stt_text
                st.toast("Voice transcribed")
        except Exception as e:
            st.warning(f"STT failed: {e}")

    # Chat-style input (placeholder compatible with older Streamlit)
    try:
        q = st.chat_input(key="chat_input", placeholder="Ask a startup question… (Chinese or English)")
    except TypeError:
        q = st.chat_input("Ask a startup question… (Chinese or English)", key="chat_input")

    # If we have STT draft, let user edit & send
    if q is None and default_prompt:
        q = st.text_input("Recognized speech (edit then press Enter)", value=default_prompt)

    # ---- 统一处理：文本/语音都走 RAG（/ask-business-v1），可选再 TTS ----
    if q:
        # 1) 先展示用户消息
        st.session_state.messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)

        # 2) 调用 /ask-business-v1
        try:
            payload = {
                "session": st.session_state.session_id,
                "query": q,
                "debug": bool(st.session_state.get("show_ev", False)),  # ⬅ 关键
            }
            url_rag = API_BASE.rstrip("/") + "/ask-business-v1"
            r = requests.post(url_rag, json=payload, headers=headers, timeout=180)
            j = r.json()
            ans_text = j["data"].get("text", "")
            evs     = j["data"].get("evidence", [])
        except Exception as e:
            ans_text = f"❌ Request failed: {e}"
            evs = []

        # 3)（可选）TTS：把文字转语音
        audio_data = None
        if st.session_state.get("tts_enabled", False) and ans_text:
            try:
                url_tts = API_BASE.rstrip("/") + "/tts-say"
                jr = requests.post(url_tts, json={"text": ans_text}, headers=headers, timeout=180)
                if jr.headers.get("content-type", "").startswith("audio/"):
                    audio_data = jr.content
            except Exception:
                # 不阻塞主流程，语音失败就忽略
                pass

        # 4) 保存与展示助手消息
        msg = {"role": "assistant", "content": ans_text, "evidence": evs}
        if audio_data:
            msg["audio"] = audio_data
        st.session_state.messages.append(msg)

        with st.chat_message("assistant"):
            st.markdown(ans_text)
            if st.session_state.get("show_ev") and evs:
                with st.expander("RAG evidence", expanded=False):
                    st.json(evs)
            if audio_data:
                st.audio(audio_data, format="audio/mp3")

    # ---------- Footer actions ----------
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        if st.button("🧹 Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    with c2:
        if st.button("🆕 New session", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())[:8]
            st.session_state.messages = []
            st.rerun()
    # with c3:
    #     st.caption(f"Session ID: `{st.session_state.session_id}`")
    with c4:
        # st.divider()
        # if st.button("Back to FIRE Checkup", type="secondary"):
        if st.button("Back to FIRE Checkup"):
            goto("app.py")


if __name__ == "__main__":
    st.set_page_config(page_title="Disclaimer: It is for education only and is NOT investment advice. Startup Companion can make mistakes. Check important info. ", layout="wide")
    render_minbiz_ui()