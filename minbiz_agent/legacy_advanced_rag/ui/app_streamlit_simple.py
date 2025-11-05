# -*- coding: utf-8 -*-
import io
import os
import json
import requests
import streamlit as st

st.set_page_config(page_title="MinBiz Voice Agent", page_icon="🗣️", layout="wide")

# -------------------- Sidebar 配置 --------------------
st.sidebar.title("MinBiz Agent (Streamlit)")
backend_url = st.sidebar.text_input(
    "后端地址（FastAPI）",
    value=os.environ.get("MINBIZ_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/"),
    help="你的 uvicorn 监听地址，例如 http://127.0.0.1:8000 或 http://<IP>:8000",
)
api_key = st.sidebar.text_input("X-API-Key", value=os.environ.get("MINBIZ_API_KEY", "devkey"))
style = st.sidebar.selectbox("回答风格", ["pro", "story", "bullets"], index=0)
lang = st.sidebar.selectbox("语言", ["auto", "zh", "en"], index=0)
bilingual = st.sidebar.checkbox("中英双语", value=False)
debug_mode = st.sidebar.checkbox("返回 RAG 调试信息（debug=true）", value=False)

st.sidebar.markdown("---")
st.sidebar.caption("提示：此版本通过服务端请求调用，不涉及浏览器 CORS/WebRTC。")

# -------------------- 实用函数 --------------------
def post_text(q: str, do_tts: bool):
    url = f"{backend_url}/ask-text-v2"
    files = {
        "q": (None, q),
        "style": (None, style),
        "lang": (None, lang),
        "bilingual": (None, json.dumps(bilingual).lower()),
        "do_tts": (None, json.dumps(do_tts).lower()),
        "debug": (None, json.dumps(debug_mode).lower()),
    }
    headers = {"X-API-Key": api_key}
    resp = requests.post(url, files=files, headers=headers, timeout=180)

    ct = resp.headers.get("Content-Type", "")
    return resp, ct

def post_voice(file_bytes: bytes, filename: str, do_tts: bool):
    url = f"{backend_url}/ask-voice-v2"
    files = {
        "audio": (filename, file_bytes, "application/octet-stream"),
        "style": (None, style),
        "lang": (None, lang),
        "bilingual": (None, json.dumps(bilingual).lower()),
        "do_tts": (None, json.dumps(do_tts).lower()),
        "debug": (None, json.dumps(debug_mode).lower()),
    }
    headers = {"X-API-Key": api_key}
    resp = requests.post(url, files=files, headers=headers, timeout=180)
    ct = resp.headers.get("Content-Type", "")
    return resp, ct

# -------------------- UI 主体 --------------------
st.title("🗣️ MinBiz Voice Agent（简易版 UI）")

tab1, tab2 = st.tabs(["📝 文本问答", "🎧 上传音频问答"])

with tab1:
    st.subheader("文本 → 回答 / 语音")
    q = st.text_area("输入你的问题：", height=140, placeholder="例如：一分钟讲明白创业定位")
    col_a, col_b = st.columns(2)
    with col_a:
        do_tts_text = st.checkbox("合成语音（TTS）", value=False)
    with col_b:
        btn = st.button("发送", use_container_width=True)

    if btn and q.strip():
        with st.spinner("调用后端中…"):
            resp, ct = post_text(q.strip(), do_tts_text)

        if "audio" in ct or ct.endswith("/mpeg") or ct.endswith("/mp3"):
            # 返回的是音频文件
            st.success("收到音频回答")
            st.audio(resp.content, format="audio/mp3")
            st.download_button("下载音频", data=resp.content, file_name="answer.mp3", mime="audio/mpeg")
        else:
            # 返回 JSON
            try:
                data = resp.json()
            except Exception:
                st.error(f"后端返回异常：{resp.status_code}\n{resp.text[:500]}")
            else:
                if resp.status_code >= 400:
                    st.error(data)
                else:
                    st.success("收到文本回答")
                    st.write(data.get("answer", ""))
                    if debug_mode and "rag_debug" in data:
                        with st.expander("RAG 调试信息（rag_debug）", expanded=False):
                            st.json(data["rag_debug"])

with tab2:
    st.subheader("上传音频 → 识别 + 回答 / 语音")
    up = st.file_uploader("上传音频文件（mp3/wav/m4a 等）", type=["mp3", "wav", "m4a", "ogg"])
    do_tts_voice = st.checkbox("合成语音（TTS）", value=True, key="do_tts_voice")
    send_voice = st.button("上传并发送", use_container_width=True, key="send_voice")

    if send_voice:
        if not up:
            st.warning("请先选择一个音频文件")
        else:
            with st.spinner("上传并调用后端中…"):
                resp, ct = post_voice(up.read(), up.name, do_tts_voice)

            if "audio" in ct or ct.endswith("/mpeg") or ct.endswith("/mp3"):
                st.success("收到语音回答")
                st.audio(resp.content, format="audio/mp3")
                st.download_button("下载音频", data=resp.content, file_name="answer.mp3", mime="audio/mpeg")
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
                        st.write(data.get("answer", ""))
                        if debug_mode and "rag_debug" in data:
                            with st.expander("RAG 调试信息（rag_debug）", expanded=False):
                                st.json(data["rag_debug"])
