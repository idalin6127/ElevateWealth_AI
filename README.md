ElevateWealth AI — Intelligent Wealth Growth Platform
<p align="center"> <img src="https://raw.githubusercontent.com/github/explore/main/topics/ai/ai.png" width="90"> </p> <p align="center"> <b>ElevateWealth AI</b> | Intelligent Wealth Companion <br> <i>Wealth Checkup · Startup Agent · Investment · Career Growth</i> <br> Powered by <a href="https://openai.com">OpenAI GPT-4o</a> • Streamlit • FastAPI • SQLite FTS5 </p>
🌟 Overview

ElevateWealth AI is an intelligent wealth growth platform
designed for high-knowledge professionals seeking financial freedom.
The unified app.py dashboard allows users to access multiple intelligent modules:

Module	Description
💰 Wealth Checkup	Analyze assets, liabilities, and cash flow; generate personalized freedom reports
🚀 Startup Agent (MinBiz)	Entrepreneurial coaching using RAG + LLM; strategy, branding, execution
📈 Investment Agent (Coming Soon)	Portfolio allocation, ETF analysis, risk insights
🎓 Career Growth Agent (Planned)	Professional development, communication, and career transition guidance
🧭 Architecture Flow
graph TD
A[User] --> B[Streamlit Main app.py]
B --> C1[Wealth Checkup]
B --> C2[Startup Agent MinBiz]
B --> C3[Investment Agent]
B --> C4[Career Agent]
C2 --> D1[/ask-business-v1 → FastAPI]
D1 --> D2[voice_agent.py → brain.py]
D2 --> D3[rags_search → rag_fts5.db]
D3 --> D4[OpenAI GPT-4o]
D4 --> D5[Return text + evidence]

📂 Project Structure
ElevateWealth_AI/
├── app.py                        # 🌐 Main dashboard — multi-agent navigation
│
├── minbiz_agent/                 # 🚀 Startup Companion Module
│   ├── data/                     # Active RAG data
│   ├── src/                      # Core logic (agent / rag / server / ui)
│   └── legacy_advanced_rag/      # Archived RAG Lab
│
├── wealth_checkup/               # 💰 Financial Freedom Checkup Reports
├── invest_agent/ (planned)       # 📈 Investment Intelligence Module
├── career_agent/ (future)        # 🎓 Career Growth Assistant
└── README.md

🧩 MinBiz Agent Overview
Layer	Module	Description
Data	data/paragraphs, rag_fts5.db	Knowledge base + search index
Retrieval	rag/sqlite_fts.py	FTS5 index build/query
Brain	agent/brain.py	RAG + LLM + memory
Service	server/voice_agent.py	FastAPI endpoints
UI	ui/app_minbiz_chat.py	Streamlit frontend (voice + text)
🚀 Run Instructions
# Launch Main Dashboard
streamlit run app.py
# Launch Backend for Startup Agent
uvicorn minbiz_agent.src.server.voice_agent:app --reload


Access via http://localhost:8501

💾 Data Description (Startup Agent)
Path	Description	Status
data/paragraphs/	Active RAG knowledge	✅ Active
data/rag_fts5.db	FTS5 database	✅ Active
data/minbiz.db	Chat memory	✅ Active
legacy_advanced_rag/data/	Old index data	🧩 Archived
✨ Author’s Note

Curated and maintained by Ida Lin.
ElevateWealth AI integrates Wealth Checkup, Startup Companion,
and soon Investment & Career Growth agents,
forming a holistic AI-driven Wealth Empowerment Ecosystem.