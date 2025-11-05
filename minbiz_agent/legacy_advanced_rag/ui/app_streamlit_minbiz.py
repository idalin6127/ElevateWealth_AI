# -*- coding: utf-8 -*-
"""
MinBiz Voice Agent - Streamlit UI (含浏览器录音)
- /ask-text-v2:
  - do_tts=false -> JSON: {"answer","rag_debug"?}
  - do_tts=true  -> audio/mpeg
- /ask-voice-v2:
  - do_tts=false -> JSON: {"question","answer","rag_debug"?}
  - do_tts=true  -> audio/mpeg
"""

import os, io, json, requests, streamlit as st

# -------- 依赖的录音组件（audio-recorder-streamlit） --------
try:
    from audio_recorder_streamlit import audio_recorder  # 录音，返回 wav 字节
    REC_AVAILABLE = True
except Exception:
    REC_AVAILABLE = False

DEFAULT_API_BASE = os.getenv("MINBIZ_BACKEND_URL", os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000")).rstrip("/")
DEFAULT_API_KEY  = os.getenv("MINBIZ_API_KEY", "devkey")

STYLE_OPTIONS = ["pro", "story", "concise", "formal", "casual"]
LANG_OPTIONS  = {"Auto": "auto", "中文 (zh)": "zh", "English (en)": "en"}

EDGE_VOICE_BY_LANG = {
    "zh": os.getenv("EDGE_TTS_VOICE_ZH", "zh-CN-XiaoxiaoNeural"),
    "en": os.getenv("EDGE_TTS_VOICE_EN", "en-US-AriaNeural"),
}

st.set_page_config(page_title="MinBiz Voice Agent", page_icon="🎙️", layout="wide")

# ---------------------- Sidebar ----------------------
st.sidebar.header("🔧 Settings")
api_base = st.sidebar.text_input("API Base", value=DEFAULT_API_BASE)
api_key  = st.sidebar.text_input("X-API-Key", value=DEFAULT_API_KEY)
style    = st.sidebar.selectbox("Voice style / 语气", STYLE_OPTIONS, index=0)
ui_lang  = st.sidebar.selectbox("UI Language / 界面语言", list(LANG_OPTIONS.keys()), index=0)
lang     = LANG_OPTIONS[ui_lang]
bilingual = st.sidebar.checkbox("Answer bilingual / 双语回答", value=False)
debug_mode = st.sidebar.checkbox("返回 RAG 调试信息（debug=true）", value=False)

# ---------------------- HTTP helpers ----------------------
def _post_multipart(url: str, fields: dict, files: dict | None = None, timeout=180):
    headers = {"X-API-Key": api_key} if api_key else {}
    return requests.post(url, headers=headers, files=fields | (files or {}), timeout=timeout)

def _send_text(q: str, do_tts: bool, tts_voice: str = ""):
    url = f"{api_base}/ask-text-v2"
    fields = {
        "q": (None, q),
        "style": (None, style),
        "lang": (None, lang),
        "bilingual": (None, json.dumps(bilingual).lower()),
        "do_tts": (None, json.dumps(do_tts).lower()),
        "debug": (None, json.dumps(debug_mode).lower()),
    }
    if tts_voice.strip():
        fields["tts_voice"] = (None, tts_voice.strip())
    r = _post_multipart(url, fields=fields)
    return r, r.headers.get("Content-Type", "")

def _send_voice(file_name: str, file_bytes: bytes, do_tts: bool, tts_voice: str = ""):
    url = f"{api_base}/ask-voice-v2"
    fields = {
        "style": (None, style),
        "lang": (None, lang),
        "bilingual": (None, json.dumps(bilingual).lower()),
        "do_tts": (None, json.dumps(do_tts).lower()),
        "debug": (None, json.dumps(debug_mode).lower()),
    }
    if tts_voice.strip():
        fields["tts_voice"] = (None, tts_voice.strip())
    files = {"audio": (file_name, file_bytes, "audio/wav")}
    r = _post_multipart(url, fields=fields, files=files)
    return r, r.headers.get("Content-Type", "")

def _render_rag_debug(rag_debug):
    if not rag_debug:
        st.info("无 RAG 调试数据（rag_debug 为空）")
        return
    with st.expander("📚 RAG 调试（rag_debug）", expanded=False):
        st.json(rag_debug)

def _show_audio(resp_content: bytes, filename="answer.mp3"):
    st.success("收到音频回答")
    st.audio(resp_content, format="audio/mp3")
    st.download_button("下载音频", data=resp_content, file_name=filename, mime="audio/mpeg")

# ---------------------- UI ----------------------
st.title("🎙️ MinBiz Voice Agent")

tab1, tab2, tab3 = st.tabs(["💬 文本问答", "🎧 上传音频问答", "🎙️ 浏览器录音"])

# ---- 文本 ----
with tab1:
    st.subheader("💬 文本 → 回答 / 语音")
    q = st.text_area("你的问题", height=140, placeholder="例如：一分钟讲明白创业定位")
    col1, col2 = st.columns(2)
    with col1:
        do_tts_text = st.checkbox("返回语音（TTS）", value=False)
    with col2:
        tts_voice_override = st.text_input("TTS voice 覆盖（可留空）", value="")

    if st.button("🚀 发送（文本）", use_container_width=True):
        if not q.strip():
            st.warning("请输入问题")
        else:
            with st.spinner("调用后端中…"):
                resp, ctype = _send_text(q.strip(), do_tts_text, tts_voice_override)
            if "audio" in ctype or ctype.endswith("/mpeg") or ctype.endswith("/mp3"):
                _show_audio(resp.content)
            else:
                try:
                    data = resp.json()
                except Exception:
                    st.error(f"后端返回异常：{resp.status_code}\n{resp.text[:500]}")
                else:
                    if resp.status_code >= 400:
                        st.error(data)
                    else:
                        st.success("收到文本回答")
                        st.write(data.get("answer") or data.get("answer_text") or "")
                        if debug_mode:
                            _render_rag_debug(data.get("rag_debug"))

# ---- 上传音频 ----
with tab2:
    st.subheader("🎧 上传音频 → 识别 + 回答 / 语音")
    up = st.file_uploader("上传音频（mp3/wav/m4a/ogg/webm）", type=["mp3","wav","m4a","ogg","webm"])
    colv1, colv2 = st.columns(2)
    with colv1:
        do_tts_voice = st.checkbox("返回语音（TTS）", value=True, key="do_tts_voice_upl")
    with colv2:
        suggested = EDGE_VOICE_BY_LANG.get(lang, EDGE_VOICE_BY_LANG["zh"])
        tts_voice_override2 = st.text_input("TTS voice 覆盖（可留空）", value=suggested, key="tts_upl")

    if st.button("🎤 上传并发送", use_container_width=True):
        if not up:
            st.warning("请先选择音频文件")
        else:
            with st.spinner("上传并调用后端中…"):
                resp, ctype = _send_voice(up.name, up.read(), do_tts_voice, tts_voice_override2)
            if "audio" in ctype or ctype.endswith("/mpeg") or ctype.endswith("/mp3"):
                _show_audio(resp.content)
            else:
                try:
                    data = resp.json()
                except Exception:
                    st.error(f"后端返回异常：{resp.status_code}\n{resp.text[:500]}")
                else:
                    if resp.status_code >= 400:
                        st.error(data)
                    else:
                        st.success("收到识别 + 文本回答")
                        st.markdown(f"**识别文本（question）**： {data.get('question','')}")
                        st.write(data.get("answer") or data.get("answer_text") or "")
                        if debug_mode:
                            _render_rag_debug(data.get("rag_debug"))

# ---- 浏览器录音 ----
with tab3:
    st.subheader("🎙️ 录音 → 识别 + 回答 / 语音")
    if not REC_AVAILABLE:
        st.error("未安装 audio-recorder-streamlit，请先运行：pip install audio-recorder-streamlit")
    else:
        st.caption("点击下方按钮开始/停止录音；停止后会在本页播放并可发送到后端。")
        # 返回的是 WAV 字节；再次点击会停止并返回
        audio_wav = audio_recorder(text="🎙️ 点击开始/停止录音", icon_size="2x")
        if audio_wav:
            st.audio(io.BytesIO(audio_wav), format="audio/wav")
            colr1, colr2 = st.columns(2)
            with colr1:
                do_tts_rec = st.checkbox("返回语音（TTS）", value=True, key="do_tts_rec")
            with colr2:
                suggested_r = EDGE_VOICE_BY_LANG.get(lang, EDGE_VOICE_BY_LANG["zh"])
                tts_voice_override3 = st.text_input("TTS voice 覆盖（可留空）", value=suggested_r, key="tts_rec")

            if st.button("🚀 发送录音到后端", use_container_width=True):
                with st.spinner("调用后端中…"):
                    resp, ctype = _send_voice("mic.wav", audio_wav, do_tts_rec, tts_voice_override3)
                if "audio" in ctype or ctype.endswith("/mpeg") or ctype.endswith("/mp3"):
                    _show_audio(resp.content)
                else:
                    try:
                        data = resp.json()
                    except Exception:
                        st.error(f"后端返回异常：{resp.status_code}\n{resp.text[:500]}")
                    else:
                        if resp.status_code >= 400:
                            st.error(data)
                        else:
                            st.success("收到识别 + 文本回答")
                            st.markdown(f"**识别文本（question）**： {data.get('question','')}")
                            st.write(data.get("answer") or data.get("answer_text") or "")
                            if debug_mode:
                                _render_rag_debug(data.get("rag_debug"))


# ---- 🧭 创业诊断（调用 /ask-business-v1） ----
import os, requests, streamlit as st

st.markdown("---")
st.subheader("🧭 创业诊断（内置RAG+记忆）")
session = st.text_input("会话ID（可用你的昵称或手机号）", value="demo")
q2 = st.text_area("你的创业问题 / 场景", height=120, placeholder="例如：如何为‘留学生财务教练’做定位与3层产品？")
if st.button("生成诊断方案", use_container_width=True):
    api = os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000")
    try:
        resp = requests.post(f"{api}/ask-business-v1",
                             json={"session": session, "query": q2}, timeout=60)
        j = resp.json()
        if j.get("ok"):
            st.success("✅ 诊断完成")
            st.write(j["data"]["text"])
            with st.expander("查看RAG证据"):
                st.json(j["data"]["evidence"])
        else:
            st.error("❌ "+str(j.get("error")))
    except Exception as e:
        st.error(f"请求失败：{e}")
