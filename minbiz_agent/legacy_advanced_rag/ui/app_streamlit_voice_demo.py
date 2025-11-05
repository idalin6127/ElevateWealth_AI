# # import os, io, base64, requests
# # import streamlit as st

# # # 尝试导入“浏览器麦克风录音”（可选）
# # try:
# #     from streamlit_mic_recorder import mic_recorder
# #     MIC_OK = True
# # except Exception:
# #     MIC_OK = False

# # st.set_page_config(page_title="MinBiz Voice Demo", page_icon="🎤", layout="centered")
# # st.title("🎤 MinBiz Voice Agent Demo")

# # # ============== 配置区 ==============
# # with st.sidebar:
# #     st.header("Backend")
# #     api_base = st.text_input("API Base", value=os.getenv("VOICE_AGENT_API", "http://127.0.0.1:8000"))
# #     api_key  = st.text_input("X-API-Key", value=os.getenv("MINBIZ_API_KEY", "devkey"))
# #     st.caption("后端必须已在 8000 端口运行。")

# #     st.header("Options")
# #     style = st.selectbox("Voice style", ["story", "concise", "bullet"])
# #     lang  = st.selectbox("Voice lang", ["auto", "zh", "en"])
# #     bilingual = st.checkbox("Bilingual?", value=False)

# #     st.divider()
# #     st.caption("提示：语音输出使用后端的 TTS 配置；无需在前端单独设置。")

# # def play_segments_b64(b64_list, fmt="mp3"):
# #     if not b64_list:
# #         st.info("后端未返回语音片段（可能已关闭 TTS 或发生降级）。")
# #         return
# #     for i, b64 in enumerate(b64_list, 1):
# #         audio_bytes = base64.b64decode(b64)
# #         st.audio(io.BytesIO(audio_bytes), format=f"audio/{fmt}")
# #         with st.expander(f"第 {i} 段音频（{fmt}，base64）", expanded=False):
# #             st.code(b64[:120] + " ...", language="text")

# # def render_refs(refs):
# #     if not refs:
# #         return
# #     st.subheader("📚 引用片段")
# #     for r in refs:
# #         st.markdown(f"- **{r.get('doc_title','')}** · {r.get('chunk_id','')} · score={r.get('score','')}")
# #         if r.get("text"):
# #             with st.expander("查看内容"):
# #                 st.write(r["text"])

# # # ============== 语音 Tab ==============
# # tab_voice, tab_text = st.tabs(["🎙️ 语音输入", "⌨️ 文本输入"])

# # with tab_voice:
# #     st.write("选择一种方式提交音频：浏览器录音（可用时）或上传 wav/mp3 文件。")
# #     wav_bytes = None

# #     if MIC_OK:
# #         rec = mic_recorder(start_prompt="开始录音", stop_prompt="停止录音", just_once=False, use_container_width=True)
# #         if rec and rec.get("bytes"):
# #             wav_bytes = rec["bytes"]  # wav PCM
# #             st.success("已采集到语音。")
# #     else:
# #         st.info("mic 录音组件不可用，使用下方文件上传。")

# #     up = st.file_uploader("或上传音频文件（wav/mp3）", type=["wav", "mp3"], accept_multiple_files=False)
# #     if up:
# #         wav_bytes = up.read()

# #     if st.button("提交语音到后端", use_container_width=True, disabled=(wav_bytes is None)):
# #         try:
# #             files = {"audio": ("voice.wav", wav_bytes, "audio/wav")}
# #             data  = {"style": style, "lang": lang, "bilingual": str(bilingual).lower()}
# #             r = requests.post(f"{api_base}/ask-voice-v2",
# #                               headers={"X-API-Key": api_key},
# #                               files=files, data=data, timeout=90)
# #             r.raise_for_status()
# #             j = r.json()

# #             st.subheader("🗣️ 识别文本（STT）")
# #             st.write(j.get("question", ""))

# #             st.subheader("🧠 答案")
# #             st.write(j.get("answer", ""))

# #             st.subheader("🔊 语音播放")
# #             play_segments_b64(j.get("audio_segments_b64", []), fmt=j.get("audio_format", "mp3"))

# #             render_refs(j.get("refs", []))
# #         except requests.HTTPError as e:
# #             st.error(f"HTTPError: {e.response.status_code} {e.response.text}")
# #         except Exception as e:
# #             st.exception(e)

# # # ============== 文本 Tab ==============
# # with tab_text:
# #     q = st.text_area("你的问题：", value="用一句话解释极简商业的核心", height=120)
# #     if st.button("提交文本到后端", use_container_width=True):
# #         try:
# #             data = {"q": q, "style": style, "lang": lang, "bilingual": str(bilingual).lower()}
# #             r = requests.post(f"{api_base}/ask-text-v2",
# #                               headers={"X-API-Key": api_key},
# #                               data=data, timeout=90)
# #             r.raise_for_status()
# #             j = r.json()

# #             # 两类返回：你现在的后端同时支持“只文本”和“带音频的文本”
# #             answer = j.get("answer") or j.get("answer_text") or ""
# #             st.subheader("🧠 答案")
# #             st.write(answer)

# #             # 尝试播放语音（如果后端开启TTS则会有）
# #             st.subheader("🔊 语音播放")
# #             segs = j.get("audio_segments_b64")  # /ask-text-v2 兼容字段
# #             if segs is None and "segments" in j:
# #                 segs = [s.get("audio_b64") for s in j["segments"]]
# #             fmt  = j.get("audio_format", "mp3")
# #             play_segments_b64(segs or [], fmt=fmt)

# #             render_refs(j.get("refs", []))
# #         except requests.HTTPError as e:
# #             st.error(f"HTTPError: {e.response.status_code} {e.response.text}")
# #         except Exception as e:
# #             st.exception(e)


# # src/ui/app_streamlit_voice_demo.py
# import os, io, base64, requests
# import streamlit as st

# # 可选录音功能（无则自动关闭）
# try:
#     from streamlit_mic_recorder import mic_recorder
#     MIC_OK = True
# except Exception:
#     MIC_OK = False

# st.set_page_config(page_title="MinBiz Voice Agent", page_icon="🎧", layout="centered")

# # ---------------- 初始化防丢状态 ----------------
# if "ui_lang" not in st.session_state:
#     st.session_state.ui_lang = os.getenv("UI_LANG", "zh")
# if "follow_ui" not in st.session_state:
#     st.session_state.follow_ui = True
# if "ans_lang" not in st.session_state:
#     st.session_state.ans_lang = "en" if st.session_state.ui_lang == "en" else "zh"

# default_voice_map = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AriaNeural"}
# if "preferred_voice" not in st.session_state:
#     st.session_state.preferred_voice = os.getenv(
#         "EDGE_TTS_VOICE", default_voice_map[st.session_state.ans_lang]
#     )

# # ---------------- 多语言字典 ----------------
# I18N = {
#     "zh": {
#         "title": "🎧 语音 / 文本 助手",
#         "backend_header": "后端配置",
#         "api_base": "API 地址",
#         "api_key": "X-API-Key",
#         "options": "选项",
#         "ui_lang": "界面语言",
#         "ans_lang": "回答语言",
#         "follow_ui_lang": "回答语言跟随界面语言",
#         "style": "表达风格",
#         "tab_voice": "🎙️ 语音输入",
#         "tab_text": "⌨️ 文本输入",
#         "rec_start": "开始录音",
#         "rec_stop": "停止录音",
#         "or_upload": "或上传音频文件（wav/mp3）",
#         "submit_audio": "提交语音到后端",
#         "submit_text": "提交文本到后端",
#         "placeholder_q": "用一句话解释极简商业的核心",
#         "stt": "🗣️ 识别文本",
#         "answer": "🧠 答案",
#         "audio": "🔊 语音播放",
#         "refs": "📚 引用片段",
#         "no_audio": "未返回音频（可能关闭了 TTS 或发生降级）",
#         "hint": "提示：语音输出的声音会自动根据语言选择发音。",
#         "bilingual": "双语回答（覆盖回答语言设置）",
#         "tts_voice": "首选 TTS 声音（可留空自动）",
#         "loading": "生成中...",
#         "ready": "完成",
#         "mic_unavailable": "录音不可用，请上传文件。",
#     },
#     "en": {
#         "title": "🎧 Voice / Text Assistant",
#         "backend_header": "Backend",
#         "api_base": "API Base",
#         "api_key": "X-API-Key",
#         "options": "Options",
#         "ui_lang": "UI Language",
#         "ans_lang": "Answer Language",
#         "follow_ui_lang": "Answer language follows UI",
#         "style": "Style",
#         "tab_voice": "🎙️ Voice",
#         "tab_text": "⌨️ Text",
#         "rec_start": "Start Recording",
#         "rec_stop": "Stop Recording",
#         "or_upload": "Or upload audio (wav/mp3)",
#         "submit_audio": "Send Audio",
#         "submit_text": "Send Text",
#         "placeholder_q": "Explain the core of Minimal Business in one sentence",
#         "stt": "🗣️ Transcript",
#         "answer": "🧠 Answer",
#         "audio": "🔊 Audio",
#         "refs": "📚 References",
#         "no_audio": "No audio returned (TTS disabled or degraded)",
#         "hint": "Note: The TTS voice auto-adjusts based on language.",
#         "bilingual": "Bilingual answer (override answer language)",
#         "tts_voice": "Preferred TTS voice (optional)",
#         "loading": "Generating...",
#         "ready": "Done",
#         "mic_unavailable": "Mic unavailable. Please upload an audio file.",
#     }
# }
# def t(key): return I18N[st.session_state.ui_lang].get(key, key)

# # ---------------- 样式 ----------------
# st.markdown("""
# <style>
# .stTabs [data-baseweb="tab"] { font-size: 1rem; padding: 10px 18px; }
# h1,h2,h3 { letter-spacing:.2px; }
# .stButton>button { border-radius: 10px; height:44px; }
# .card {background:#fff;border:1px solid rgba(0,0,0,.07);border-radius:14px;padding:14px 16px;box-shadow:0 3px 15px rgba(0,0,0,.05);}
# </style>
# """, unsafe_allow_html=True)

# # ---------------- 侧边栏 ----------------
# with st.sidebar:
#     st.header(t("backend_header"))
#     api_base = st.text_input(t("api_base"), value=os.getenv("VOICE_AGENT_API","http://127.0.0.1:8000"))
#     api_key  = st.text_input(t("api_key"), value=os.getenv("MINBIZ_API_KEY","devkey"))

#     st.header(t("options"))

#     st.selectbox(t("ui_lang"), ["zh","en"], key="ui_lang")
#     st.checkbox(t("follow_ui_lang"), key="follow_ui")

#     if st.session_state.follow_ui:
#         st.session_state.ans_lang = "en" if st.session_state.ui_lang == "en" else "zh"
#         disabled_ans = True
#     else:
#         disabled_ans = False

#     st.selectbox(t("ans_lang"), ["auto","zh","en"], key="ans_lang", disabled=disabled_ans)

#     style = st.selectbox(t("style"), ["story","concise","bullet"])
#     bilingual = st.checkbox(t("bilingual"), value=False)

#     if st.session_state.follow_ui:
#         st.session_state.preferred_voice = default_voice_map[st.session_state.ans_lang]

#     st.text_input(t("tts_voice"), key="preferred_voice")
#     st.caption(t("hint"))

# st.title(t("title"))

# # ---------------- 工具函数 ----------------
# def play_segments(b64_list, fmt="mp3"):
#     if not b64_list:
#         st.info(t("no_audio")); return
#     for i,b64 in enumerate(b64_list,1):
#         audio = base64.b64decode(b64)
#         st.audio(io.BytesIO(audio), format=f"audio/{fmt}")

# def render_refs(refs):
#     if not refs: return
#     st.subheader(t("refs"))
#     for r in refs:
#         with st.container():
#             st.markdown(f"<div class='card'><b>{r.get('doc_title','')}</b><br/>{r.get('text','')[:120]}...</div>", unsafe_allow_html=True)

# def send_voice(audio_bytes):
#     data = {
#         "style": style,
#         "lang": st.session_state.ans_lang,
#         "bilingual": str(bilingual).lower(),
#         "tts_voice": st.session_state.preferred_voice
#     }
#     files = {"audio": ("voice.wav", audio_bytes, "audio/wav")}
#     return requests.post(f"{api_base}/ask-voice-v2", headers={"X-API-Key": api_key}, files=files, data=data, timeout=120)

# def send_text(q):
#     data = {
#         "q": q,
#         "style": style,
#         "lang": st.session_state.ans_lang,
#         "bilingual": str(bilingual).lower(),
#         "tts_voice": st.session_state.preferred_voice
#     }
#     return requests.post(f"{api_base}/ask-text-v2", headers={"X-API-Key": api_key}, data=data, timeout=120)

# # ---------------- 主体 ----------------
# tab_voice, tab_text = st.tabs([t("tab_voice"), t("tab_text")])

# with tab_voice:
#     wav_bytes = None
#     if MIC_OK:
#         rec = mic_recorder(start_prompt=t("rec_start"), stop_prompt=t("rec_stop"), just_once=False)
#         if rec and rec.get("bytes"): wav_bytes = rec["bytes"]
#     else:
#         st.info(t("mic_unavailable"))

#     up = st.file_uploader(t("or_upload"), type=["wav","mp3"])
#     if up: wav_bytes = up.read()

#     if st.button(t("submit_audio"), use_container_width=True, disabled=(wav_bytes is None)):
#         with st.status(t("loading"), expanded=True) as s:
#             try:
#                 r = send_voice(wav_bytes); j = r.json(); s.update(label=t("ready"), state="complete")
#                 st.subheader(t("stt")); st.write(j.get("question",""))
#                 st.subheader(t("answer")); st.write(j.get("answer",""))
#                 st.subheader(t("audio")); play_segments(j.get("audio_segments_b64",[]), fmt=j.get("audio_format","mp3"))
#                 render_refs(j.get("refs", []))
#             except Exception as e:
#                 st.exception(e)

# with tab_text:
#     q = st.text_area("", value=t("placeholder_q"), height=120)
#     if st.button(t("submit_text"), use_container_width=True):
#         with st.status(t("loading"), expanded=True) as s:
#             try:
#                 r = send_text(q); j = r.json(); s.update(label=t("ready"), state="complete")
#                 st.subheader(t("answer")); st.write(j.get("answer",""))
#                 st.subheader(t("audio")); play_segments(j.get("audio_segments_b64",[]), fmt=j.get("audio_format","mp3"))
#                 render_refs(j.get("refs", []))
#             except Exception as e:
#                 st.exception(e)

# src/ui/app_streamlit_voice_demo.py
import os, io, base64, json, requests
import streamlit as st

# 可选：简易麦克风组件（没有也可用文件上传）
try:
    from streamlit_mic_recorder import mic_recorder
    MIC_OK = True
except Exception:
    MIC_OK = False

st.set_page_config(page_title="MinBiz Voice Assistant", page_icon="🎧", layout="centered")

# ---------------- 会话状态：防止 rerun 丢语言设置 ----------------
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = os.getenv("UI_LANG", "zh")
if "follow_ui" not in st.session_state:
    st.session_state.follow_ui = True
if "ans_lang" not in st.session_state:
    st.session_state.ans_lang = "en" if st.session_state.ui_lang == "en" else "zh"

default_voice_map = {"zh": "zh-CN-XiaoxiaoNeural", "en": "en-US-AriaNeural"}
if "preferred_voice" not in st.session_state:
    st.session_state.preferred_voice = os.getenv(
        "EDGE_TTS_VOICE", default_voice_map[st.session_state.ans_lang]
    )

# ---------------- 多语言文案 ----------------
I18N = {
    "zh": {
        "title": "🎧 语音 / 文本 助手",
        "backend_header": "后端配置",
        "api_base": "API 地址",
        "api_key": "X-API-Key",
        "options": "选项",
        "ui_lang": "界面语言",
        "ans_lang": "回答语言",
        "follow_ui_lang": "回答语言跟随界面语言",
        "style": "表达风格",
        "tab_voice": "🎙️ 语音输入",
        "tab_text": "⌨️ 文本输入",
        "rec_start": "开始录音",
        "rec_stop": "停止录音",
        "or_upload": "或上传音频文件（wav/mp3/m4a/ogg/webm）",
        "submit_audio": "提交语音到后端",
        "submit_text": "提交文本到后端",
        "placeholder_q": "用一句话解释极简商业的核心",
        "stt": "🗣️ 识别文本",
        "answer": "🧠 答案",
        "audio": "🔊 语音播放",
        "refs": "📚 引用片段",
        "no_audio": "未返回音频（可能关闭了 TTS 或发生降级）",
        "hint": "提示：开启“回答语言跟随界面语言”后，答案与发音会跟随 UI 语言。",
        "bilingual": "双语回答（开启将不强制改写为单一语言）",
        "tts_voice": "首选 TTS 声音（可留空自动）",
        "loading": "生成中...",
        "ready": "完成",
        "mic_unavailable": "录音不可用，请上传文件。",
        "return_tts": "返回语音分段",
    },
    "en": {
        "title": "🎧 Voice / Text Assistant",
        "backend_header": "Backend",
        "api_base": "API Base",
        "api_key": "X-API-Key",
        "options": "Options",
        "ui_lang": "UI Language",
        "ans_lang": "Answer Language",
        "follow_ui_lang": "Answer language follows UI",
        "style": "Style",
        "tab_voice": "🎙️ Voice",
        "tab_text": "⌨️ Text",
        "rec_start": "Start Recording",
        "rec_stop": "Stop Recording",
        "or_upload": "Or upload audio (wav/mp3/m4a/ogg/webm)",
        "submit_audio": "Send Audio",
        "submit_text": "Send Text",
        "placeholder_q": "Explain the core of Minimal Business in one sentence",
        "stt": "🗣️ Transcript",
        "answer": "🧠 Answer",
        "audio": "🔊 Audio",
        "refs": "📚 References",
        "no_audio": "No audio returned (TTS disabled or degraded)",
        "hint": "Note: With 'Answer language follows UI' ON, answers & voice follow the UI language.",
        "bilingual": "Bilingual answer (disables language-forcing)",
        "tts_voice": "Preferred TTS voice (optional)",
        "loading": "Generating...",
        "ready": "Done",
        "mic_unavailable": "Mic unavailable. Please upload an audio file.",
        "return_tts": "Return TTS segments",
    }
}
def t(key): return I18N[st.session_state.ui_lang].get(key, key)

# ---------------- 样式 ----------------
st.markdown("""
<style>
.stTabs [data-baseweb="tab"] { font-size: 1rem; padding: 10px 18px; }
h1,h2,h3 { letter-spacing:.2px; }
.stButton>button { border-radius: 10px; height:44px; }
.card {background:#fff;border:1px solid rgba(0,0,0,.07);border-radius:14px;padding:14px 16px;box-shadow:0 3px 15px rgba(0,0,0,.05);}
</style>
""", unsafe_allow_html=True)

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.header(t("backend_header"))
    api_base = st.text_input(t("api_base"), value=os.getenv("VOICE_AGENT_API","http://127.0.0.1:8000"))
    api_key  = st.text_input(t("api_key"), value=os.getenv("MINBIZ_API_KEY","devkey"))

    st.header(t("options"))

    st.selectbox(t("ui_lang"), ["zh","en"], key="ui_lang")
    st.checkbox(t("follow_ui_lang"), key="follow_ui")

    # 跟随 UI 时，自动对齐回答语言与 voice
    if st.session_state.follow_ui:
        st.session_state.ans_lang = "en" if st.session_state.ui_lang == "en" else "zh"
        st.session_state.preferred_voice = default_voice_map[st.session_state.ans_lang]
        ans_disabled = True
    else:
        ans_disabled = False

    st.selectbox(t("ans_lang"), ["auto","zh","en"], key="ans_lang", disabled=ans_disabled)
    style = st.selectbox(t("style"), ["story","concise","formal","casual"], index=0)
    bilingual = st.checkbox(t("bilingual"), value=False)

    st.text_input(t("tts_voice"), key="preferred_voice")
    st.caption(t("hint"))

st.title(t("title"))

# ---------------- 工具函数 ----------------
def _headers():
    return {"X-API-Key": api_key} if api_key else {}

def send_text(q: str, return_tts: bool, tts_voice: str | None):
    fields = {
        "q": q,
        "style": style,
        "lang": st.session_state.ans_lang,
        "bilingual": json.dumps(bilingual).lower(),
    }
    if tts_voice:
        fields["tts_voice"] = tts_voice
    # 是否返回 TTS 取决于后端 VOICE_TTS_DISABLE；这里直接请求，后端按 env 决定是否合成
    return requests.post(f"{api_base}/ask-text-v2", headers=_headers(), data=fields, timeout=180)

def send_voice(audio_bytes: bytes, tts_voice: str | None):
    fields = {
        "style": style,
        "lang": st.session_state.ans_lang,
        "bilingual": json.dumps(bilingual).lower(),
    }
    if tts_voice:
        fields["tts_voice"] = tts_voice
    files = {"audio": ("voice.wav", audio_bytes, "audio/wav")}
    return requests.post(f"{api_base}/ask-voice-v2", headers=_headers(), data=fields, files=files, timeout=180)

def play_segments(b64_list, fmt="mp3"):
    if not b64_list:
        st.info(t("no_audio")); return
    st.subheader(t("audio"))
    for idx, b64 in enumerate(b64_list, 1):
        try:
            audio = base64.b64decode(b64)
            st.audio(io.BytesIO(audio), format=f"audio/{fmt}")
        except Exception as e:
            st.warning(f"Segment {idx} decode error: {e}")

def render_refs(refs):
    if not refs: return
    st.subheader(t("refs"))
    for r in refs:
        st.markdown(
            f"<div class='card'><b>{r.get('doc_title','')}</b><br/>{(r.get('text','') or '')[:160]}...</div>",
            unsafe_allow_html=True
        )

# ---------------- 主体：Tab 结构 ----------------
tab_voice, tab_text = st.tabs([t("tab_voice"), t("tab_text")])

with tab_voice:
    wav_bytes = None
    # A) 浏览器录音（可选）
    if MIC_OK:
        rec = mic_recorder(start_prompt=t("rec_start"), stop_prompt=t("rec_stop"), just_once=False)
        if rec and rec.get("bytes"):
            wav_bytes = rec["bytes"]
    else:
        st.info(t("mic_unavailable"))

    # B) 文件上传（最稳）
    up = st.file_uploader(t("or_upload"), type=["wav","mp3","m4a","ogg","webm"])
    if up:
        wav_bytes = up.read()

    if st.button(t("submit_audio"), use_container_width=True, disabled=(wav_bytes is None)):
        with st.status(t("loading"), expanded=True) as s:
            try:
                r = send_voice(wav_bytes, st.session_state.preferred_voice)
                r.raise_for_status()
                j = r.json()
                s.update(label=t("ready"), state="complete")

                st.subheader(t("stt")); st.write(j.get("question") or j.get("transcript") or "")
                st.subheader(t("answer")); st.write(j.get("answer") or j.get("answer_text") or "")
                # 兼容扁平 & 分段返回
                segs = j.get("segments")
                if segs and isinstance(segs, list) and segs and "audio_b64" in segs[0]:
                    play_segments([s["audio_b64"] for s in segs], fmt=segs[0].get("format","mp3"))
                else:
                    play_segments(j.get("audio_segments_b64", []), fmt=j.get("audio_format","mp3"))
                render_refs(j.get("refs", []))
            except requests.HTTPError as e:
                st.error(f"HTTPError: {e} — {e.response.text if e.response is not None else ''}")
            except Exception as e:
                st.exception(e)

with tab_text:
    q = st.text_area("", value=t("placeholder_q"), height=120)
    col1, col2 = st.columns(2)
    with col1:
        return_tts = st.checkbox(t("return_tts"), value=True)
    with col2:
        tts_voice_override = st.text_input(t("tts_voice"), value=st.session_state.preferred_voice)

    if st.button(t("submit_text"), use_container_width=True):
        with st.status(t("loading"), expanded=True) as s:
            try:
                r = send_text(q, return_tts, tts_voice_override)
                r.raise_for_status()
                j = r.json()
                s.update(label=t("ready"), state="complete")

                st.subheader(t("answer")); st.write(j.get("answer") or j.get("answer_text") or "")
                # 仅当后端开启 TTS 时会返回 segments
                segs = j.get("segments") or []
                if segs and "audio_b64" in (segs[0] if segs else {}):
                    st.subheader(t("audio"))
                    for i, seg in enumerate(segs, 1):
                        try:
                            audio = base64.b64decode(seg["audio_b64"])
                            st.audio(io.BytesIO(audio), format=f"audio/{seg.get('format','mp3')}")
                        except Exception as e:
                            st.warning(f"Segment {i} decode error: {e}")
                render_refs(j.get("refs", []))
            except requests.HTTPError as e:
                st.error(f"HTTPError: {e} — {e.response.text if e.response is not None else ''}")
            except Exception as e:
                st.exception(e)
