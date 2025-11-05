# -*- coding: utf-8 -*-
"""
MinBiz Voice Agent (Full: RAG + TTS + STT + evidence)
- /ask-business-v1 : 统一业务端点（RAG -> LLM），总是返回 evidence
- /ask-text-v2     : 文本 -> (RAG) -> LLM -> [可选TTS音频]（保留兼容）
- /ask-voice-v2    : 语音 -> STT -> (RAG) -> LLM -> [可选TTS音频]
- /stt-openai      : 语音转写
- /tts-say         : 文本转语音（自动中英文）
- /health          : 健康检查
"""

import os
import re
import io
import json
import base64
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, Form, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from importlib import import_module
from threading import Semaphore

from dotenv import load_dotenv
load_dotenv()  # 读取 .env

# --- OpenAI SDK ---
from openai import OpenAI

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# ========== 环境变量 ==========
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL     = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MINBIZ_API_KEY      = os.getenv("MINBIZ_API_KEY", "devkey")

MINBIZ_OPENAI_MODEL = os.getenv("MINBIZ_OPENAI_MODEL", "gpt-4o")
MINBIZ_INDEX_DIR    = os.getenv("MINBIZ_INDEX_DIR", "data/index")

VOICE_TTS_MODEL     = os.getenv("VOICE_TTS_MODEL", "gpt-4o-mini-tts")  # or tts-1 / tts-1-hd
VOICE_STT_MODEL     = os.getenv("VOICE_STT_MODEL", "whisper-1")
DISABLE_TTS         = os.getenv("MINBIZ_DISABLE_TTS", "false").lower() == "true"

DATA_DIR = str(Path(__file__).resolve().parents[2] / "data")
FTS_DB   = str(Path(DATA_DIR) / "rag_fts5.db")


OPENAI_MAX_CONCURRENCY = int(os.getenv("OPENAI_MAX_CONCURRENCY", "3"))
STT_MAX_CONCURRENCY    = int(os.getenv("STT_MAX_CONCURRENCY", "1"))
TTS_MAX_CONCURRENCY    = int(os.getenv("TTS_MAX_CONCURRENCY", "1"))

llm_sem = Semaphore(OPENAI_MAX_CONCURRENCY)
stt_sem = Semaphore(STT_MAX_CONCURRENCY)
tts_sem = Semaphore(TTS_MAX_CONCURRENCY)

# --- OpenAI 客户端 ---
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    timeout=30,              # ⬅ 全局默认超时（秒）
)

# ========== FastAPI ==========
app = FastAPI(title="MinBiz Voice Agent", version="2.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ========== 业务大脑（RAG + 记忆） ==========
# 你的 brain.answer 会：读画像+对话、做轻量RAG、强风格输出，并返回 {"text","evidence","topic"}
from ..agent.brain import answer as biz_answer
from ..rag.sqlite_fts import build_index as rag_build

# ========== 可选：适配层，供 ask-text-v2 / ask-voice-v2 使用 ==========
# 旧版 UI 用到的“RAG上下文拼接”函数（若存在则用；失败则空上下文）
_searcher = None
def get_searcher():
    """尝试从 src.app.retriever 加载 HybridSearcher（若项目有）"""
    global _searcher
    if _searcher is not None:
        return _searcher
    try:
        mod = import_module("src.app.retriever")
        _searcher = mod.HybridSearcher(index_dir=MINBIZ_INDEX_DIR)
        print(f"[RAG] HybridSearcher ready, index_dir={MINBIZ_INDEX_DIR}")
        return _searcher
    except Exception as e:
        print("[RAG] import HybridSearcher fail:", e)
        _searcher = None
        return None

try:
    from src.app.rag import build_context_for_query_secure
    _HAVE_RAG_BUILD = True
except Exception as e:
    print("[RAG] import build_context_for_query_secure fail:", e)
    _HAVE_RAG_BUILD = False

def _normalize_hits(hits: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not hits:
        return out
    for h in hits:
        try:
            text  = getattr(h, "text", None) or getattr(h, "chunk", None) or ""
            score = getattr(h, "score", None) or getattr(h, "similarity", None) or 0.0
            meta = {
                "source":        getattr(h, "source_file", None) or getattr(h, "source", None),
                "chunk_id":      getattr(h, "chunk_id", None),
                "section_title": getattr(h, "section_title", None),
                "start":         getattr(h, "start", None),
                "end":           getattr(h, "end", None),
            }
        except Exception:
            text  = (h.get("text") or h.get("chunk") or "")
            score = (h.get("score") or h.get("similarity") or 0.0)
            md    = (h.get("meta") or h.get("metadata") or {})
            meta  = {
                "source":        md.get("source_file") or md.get("source"),
                "chunk_id":      h.get("chunk_id") or md.get("chunk_id"),
                "section_title": h.get("section_title") or md.get("section_title"),
                "start":         h.get("start") or md.get("start"),
                "end":           h.get("end") or md.get("end"),
            }
        out.append({"text": text or "", "score": float(score or 0.0), "meta": meta})
    return out

def build_rag_context_and_refs(question: str, top_k: int = 6) -> Tuple[str, List[Dict[str, Any]]]:
    searcher = get_searcher()
    if searcher is None:
        return "", []

    try:
        hits = searcher.search(question, top_k=top_k)
    except Exception as e:
        print("[RAG] search error ->", e)
        return "", []

    norm_hits = _normalize_hits(hits)

    if _HAVE_RAG_BUILD:
        try:
            ctx_text, refs = build_context_for_query_secure(
                hits,
                display_mode="summary",
                max_chars_per_snippet=90,
                max_total_quote_chars=300,
                per_ctx_blocks=6
            )
            rag_debug = []
            for h, r in zip(norm_hits, refs):
                rag_debug.append({
                    "score": h["score"],
                    "source": (h["meta"] or {}).get("source"),
                    "preview": (h["text"] or "")[:200],
                    "chunk_id": r.get("chunk_id"),
                    "title": r.get("title"),
                    "start_s": r.get("start_s"),
                    "end_s": r.get("end_s"),
                })
            if ctx_text.strip():
                ctx_text = "【检索参考】\n" + ctx_text
            return ctx_text, rag_debug
        except Exception as e:
            print("[RAG] build_context_for_query_secure error ->", e)

    if not norm_hits:
        return "", []
    ctx_text = "【检索参考】\n" + "\n\n".join((h["text"] or "")[:500] for h in norm_hits)
    rag_debug = [
        {
            "score": h["score"],
            "source": (h["meta"] or {}).get("source"),
            "preview": (h["text"] or "")[:200],
            "chunk_id": (h["meta"] or {}).get("chunk_id"),
            "title": (h["meta"] or {}).get("section_title"),
            "start_s": (h["meta"] or {}).get("start"),
            "end_s": (h["meta"] or {}).get("end"),
        }
        for h in norm_hits
    ]
    return ctx_text, rag_debug

# ========== LLM / STT / TTS ==========
def generate_answer(question: str, style: str, lang: str, bilingual: bool, rag_context: str) -> str:
    """优先基于 RAG 上下文；超时/异常快速返回；可用 MINBIZ_FAKE_LLM 跳过 OpenAI。"""
    lang_tag = decide_lang_tag(question, lang)

    prompt = (
        "You are MinBiz, a startup consultant. Always ground your answer in the PROVIDED CONTEXT first. "
        "If something is not in the context, add it as short general tips. "
        f"Write in {lang_tag}. "
        "Style: friendly, vivid, example-driven, short sentences, bullet points.\n\n"
        "User question:\n"
        f"{question}\n\n"
        "PROVIDED CONTEXT:\n"
        f"{rag_context if rag_context else '(no context)'}\n\n"
        "Format:\n"
        "1) TL;DR\n"
        "2) 3 actionable steps (with mini examples)\n"
        "3) Risks & next move\n"
    )

    # 调试：不走 OpenAI，确认后端链路是否通畅
    if MINBIZ_FAKE_LLM:
        return f"[FAKE_ANSWER in {lang_tag}] TL;DR …\n- Step1 …\n- Step2 …\n- Step3 …\n(used context={bool(rag_context)})"

    t0 = time.time()
    try:
        # 单次请求再加一层更严格的超时（比如 28s）
        oc = client.with_options(timeout=28)
        with llm_sem:
            oc = client.with_options(timeout=28)
            completion = oc.chat.completions.create(
                model=MINBIZ_OPENAI_MODEL,
                messages=[...],
                temperature=0.3,
            )
        text = (completion.choices[0].message.content or "").strip()
        log.info("[LLM] ok in %.2fs, tokens≈%s", time.time()-t0, getattr(completion, "usage", None))
        return text
    except Exception as e:
        log.error("[LLM] fail after %.2fs -> %s", time.time()-t0, e)
        return f"System is busy now (model timeout). Please try again later.\n\n(error: {e})"

def transcribe_audio_to_text(file_bytes: bytes, suffix: str = "mp3") -> str:
    """Whisper 识别：并发闸门 + 每次调用级超时；临时文件更稳。"""
    try:
        with stt_sem:
            # 简单清理后缀
            suf = (suffix or "mp3").lower().strip(".")
            tmp = Path(f"tmp_input.{suf}")
            tmp.write_bytes(file_bytes)

            with tmp.open("rb") as f:
                # 每次调用再加一次较短超时，避免卡住整个服务
                oc = client.with_options(timeout=28)
                r = oc.audio.transcriptions.create(model=VOICE_STT_MODEL, file=f)

            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

            return getattr(r, "text", "") or ""
    except Exception as e:
        print("[STT] error ->", e)
        return ""


def synthesize_tts_to_mp3_b64(text: str, voice: str | None = None, lang: str | None = None) -> str:
    """
    返回 base64 编码的 mp3。并发闸门 + 每次调用级超时。
    VOICE_TTS_MODEL 支持 gpt-4o-mini-tts / tts-1 / tts-1-hd 等；voice 默认为 'alloy'。
    """
    if DISABLE_TTS:
        return ""
    try:
        with tts_sem:
            model = VOICE_TTS_MODEL or "tts-1"
            v = voice or "alloy"

            oc = client.with_options(timeout=28)  # 每次调用再指定更短超时
            audio = oc.audio.speech.create(
                model=model,
                voice=v,
                input=text,
                response_format="mp3",
            )
            data = audio.read() if hasattr(audio, "read") else audio
            return base64.b64encode(data).decode("utf-8")
    except Exception as e:
        print("[TTS] error ->", e)
        return ""


def guess_lang(text: str) -> str:
    """含中文字符 -> zh，否则 en"""
    return "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"

import time
import logging
log = logging.getLogger("minbiz")

def decide_lang_tag(question: str, lang: str | None) -> str:
    if lang:
        l = lang.lower()
        if l in ("en", "english"): return "English"
        if l in ("zh", "chinese", "zh-cn", "zh-hans"): return "简体中文"
    return "简体中文" if guess_lang(question) == "zh" else "English"

MINBIZ_FAKE_LLM = os.getenv("MINBIZ_FAKE_LLM", "0") == "1"  # 调试开关：1=不走OpenAI


class TTSReq(BaseModel):
    text: str

# --- 原: class BizReq(BaseModel): session, query
class BizReq(BaseModel):
    session: str
    query: str
    debug: bool = False            # ⬅ 新增：是否回传 evidence（给 UI 的 “Show RAG evidence” 用）


class AskWithCtx(BaseModel):
    q: str
    context: List[str] = []
    style: str = "pro"
    lang: str = "auto"
    bilingual: bool = False
    debug: bool = False

# ========== 路由 ==========
@app.get("/")
def root():
    return {"ok": True, "msg": "MinBiz Voice Agent online."}

@app.get("/health")
def health():
    return {
        "ok": True,
        "model": MINBIZ_OPENAI_MODEL,
        "tts": VOICE_TTS_MODEL,
        "stt": VOICE_STT_MODEL,
        "index_dir": str(Path(MINBIZ_INDEX_DIR).resolve()),
    }

# 统一业务端点：总是返回 evidence；语言在 brain.answer 内部 auto 处理
@app.post("/ask-business-v1")
def ask_business(req: BizReq, x_api_key: str = Header(None)):
    if x_api_key != MINBIZ_API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)
    try:
        out = biz_answer(session=req.session, query=req.query, db_path=FTS_DB, debug=req.debug)
        return {"ok": True, "data": out}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"ok": False, "error": str(e)}

# 兼容旧文本端点（仍可用）
@app.post("/ask-text-v2")
async def ask_text_v2(
    q: str = Form(...),
    style: str = Form("pro"),
    lang: str = Form("auto"),
    bilingual: bool = Form(False),
    do_tts: bool = Form(False),
    debug: bool = Form(False),
    x_api_key: str = Header(None),
):
    if x_api_key != MINBIZ_API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    try:
        rag_ctx, rag_debug = build_rag_context_and_refs(q, top_k=6)
        if rag_debug is None or rag_debug is Ellipsis:
            rag_debug = []   # <-- 防御式
        answer = generate_answer(q, style, lang, bilingual, rag_ctx)

        if not do_tts:
            resp: Dict[str, Any] = {"answer": answer, "rag_debug": rag_debug if debug else []}
            return resp

        lg = guess_lang(answer)
        voice = "alloy"  # 如用 Azure，可改为 zh-CN-XiaoxiaoNeural / en-US-JennyNeural
        tts_b64 = synthesize_tts_to_mp3_b64(answer, voice=voice, lang=lg)
        if not tts_b64:
            return {"answer": answer, "warn": "TTS unavailable; returned text."}

        out_path = "answer.mp3"
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(tts_b64))
        return FileResponse(out_path, media_type="audio/mpeg", filename="answer.mp3")

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# 兼容旧语音端点（STT -> RAG -> LLM）
@app.post("/ask-voice-v2")
async def ask_voice_v2(
    audio: UploadFile = File(...),
    style: str = Form("pro"),
    lang: str = Form("auto"),
    bilingual: bool = Form(False),
    do_tts: bool = Form(True),
    debug: bool = Form(False),
    x_api_key: str = Header(None),
):
    if x_api_key != MINBIZ_API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    try:
        data = await audio.read()
        suf = "wav"
        if audio.filename and "." in audio.filename:
            suf = audio.filename.rsplit(".", 1)[-1].lower() or "wav"

        text = transcribe_audio_to_text(data, suffix=suf)
        if not text:
            return JSONResponse({"error": "STT failed"}, status_code=400)

        rag_ctx, rag_debug = build_rag_context_and_refs(text, top_k=6)
        answer = generate_answer(text, style, lang, bilingual, rag_ctx)

        if not do_tts:
            resp: Dict[str, Any] = {"question": text, "answer": answer, "rag_debug": rag_debug if debug else []}
            return resp

        lg = guess_lang(answer)
        voice = "alloy"
        tts_b64 = synthesize_tts_to_mp3_b64(answer, voice=voice, lang=lg)
        if not tts_b64:
            return {"question": text, "answer": answer, "warn": "TTS unavailable; returned text."}

        out_path = "answer.mp3"
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(tts_b64))
        return FileResponse(out_path, media_type="audio/mpeg", filename="answer.mp3")

    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# 语音转写（供前端语音按钮用）
@app.post("/stt-openai")
async def stt_openai(file: UploadFile = File(...), x_api_key: str = Header(None)):
    if x_api_key != MINBIZ_API_KEY:
        return JSONResponse({"error":"Invalid API key"}, status_code=401)
    try:
        audio_bytes = await file.read()
        res = client.audio.transcriptions.create(
            model=VOICE_STT_MODEL,
            file=("audio.wav", io.BytesIO(audio_bytes))
        )
        text = res.text.strip()
        return {"ok": True, "text": text}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# 文本转语音（自动根据文本语言选择 voice）
@app.post("/tts-say")
async def tts_say(req: TTSReq, x_api_key: str = Header(None)):
    if x_api_key != MINBIZ_API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)
    try:
        lang = guess_lang(req.text)
        voice = "alloy"  # 如接入 Azure，这里改为 zh-CN-XiaoxiaoNeural / en-US-JennyNeural
        b64 = synthesize_tts_to_mp3_b64(req.text, voice=voice, lang=lang)
        if not b64:
            return JSONResponse({"error": "TTS unavailable"}, status_code=500)
        audio_bytes = base64.b64decode(b64)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

# 启动时确保索引
@app.on_event("startup")
async def _ensure_rag():
    try:
        if not Path(FTS_DB).exists():
            rag_build(DATA_DIR)
    except Exception as e:
        print("RAG index build error:", e)
