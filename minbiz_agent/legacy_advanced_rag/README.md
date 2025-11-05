# Legacy Advanced RAG Pipeline

这里归档了 MinBiz v1 的“高级 RAG 实验室”代码：

- 多阶段 RAG 流程：证据包 → Draft(JSON claims + support) → 校验 / Refine → 最终带 [chunk_id] 引用的回答；
- HybridSearcher + 自建索引构建脚本；
- 旧版 Streamlit 界面（`app_streamlit_minbiz.py` 等）。

当前 Startup Companion 页面使用的是简化版主线：

- `minbiz_agent/src/agent/brain.py`
- `minbiz_agent/src/rag/sqlite_fts.py`
- `minbiz_agent/src/server/voice_agent.py` (`/ask-business-v1`)
- `minbiz_agent/src/ui/app_minbiz_chat.py`

以后如果要做“可溯源、可审计”的高级 RAG，可以从这里重新取材。
