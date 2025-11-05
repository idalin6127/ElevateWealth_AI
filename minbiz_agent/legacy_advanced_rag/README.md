# Legacy Advanced RAG Pipeline

This directory archives the code from MinBiz v1's "Advanced RAG Lab":

- Multi-stage RAG pipeline: Evidence package → Draft (JSON claims + support) → Validation / Refine → Final answer with [chunk_id] citations;
- HybridSearcher + self-built index construction scripts;
- Legacy Streamlit interface (`app_streamlit_minbiz.py`, etc.).

The current Startup Companion page uses a simplified mainline:

- `minbiz_agent/src/agent/brain.py`
- `minbiz_agent/src/rag/sqlite_fts.py`
- `minbiz_agent/src/server/voice_agent.py` (`/ask-business-v1`)
- `minbiz_agent/src/ui/app_minbiz_chat.py`

If you need to build a traceable and auditable advanced RAG system in the future, you can reference the code here.
