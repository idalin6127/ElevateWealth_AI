# 💎 ElevateWealth AI — Intelligent Wealth Growth Platform

<p align="center">
  <img src="https://raw.githubusercontent.com/github/explore/main/topics/ai/ai.png" width="90">
</p>

<p align="center">
  <b>ElevateWealth AI</b> | Intelligent Wealth Companion  
  <i>Wealth Checkup · Startup Agent · Investment · Career Growth</i>  
  Powered by <a href="https://openai.com">OpenAI GPT-4o</a> • Streamlit • FastAPI • SQLite FTS5
</p>

---

## 🌟 Overview

**ElevateWealth AI** is an intelligent wealth-growth platform for high-knowledge professionals pursuing **financial freedom**.

It unifies multiple intelligent modules within one Streamlit dashboard (`app.py`):

| Module                                  | Description                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------ |
| 💰 **Wealth Checkup**                   | Analyze assets, liabilities & cash flow; generate personalized freedom reports |
| 🚀 **Startup Agent (MinBiz)**           | Entrepreneurial coaching powered by RAG + LLM; brand strategy & automation     |
| 📈 **Investment Agent *(Coming Soon)*** | Portfolio allocation, ETF analysis, risk insights                              |
| 🎓 **Career Growth *(Planned)***        | Career development, communication, and transition guidance                     |

---

## 📂 项目结构 / Project Structure

```plaintext
ElevateWealth_AI/
├── app.py                        # 🌐 Main dashboard — multi-agent navigation
│
├── minbiz_agent/                 # 🚀 Startup Companion Module
│   ├── src/                      # Core logic
│   │   ├── rag/                  # FTS5 retriever + contextual chunk builder
│   │   │   ├── sqlite_fts.py
│   │   │   ├── context_builder.py
│   │   │   └── __init__.py
│   │   ├── voice_agent/          # Voice pipeline (TTS/STT)
│   │   │   ├── voice_pipeline.py
│   │   │   └── __init__.py
│   │   ├── server/               # FastAPI backend for /ask-business-v1
│   │   │   ├── voice_agent.py
│   │   │   ├── api_routes.py
│   │   │   └── __init__.py
│   │   ├── utils/                # PDF/text parsing helpers
│   │   │   ├── text_cleaner.py
│   │   │   ├── pdf_parser.py
│   │   │   └── __init__.py
│   │   └── __init__.py
│   │
│   ├── legacy_advanced_rag/      # 🧩 Archived experimental RAG pipelines
│   │   ├── data/
│   │   └── old_pipelines/
│   │
│   ├── eval/                     # Evaluation & test scripts
│   ├── scripts/                  # Utility build / maintenance scripts
│   ├── data/                     # Placeholder (ignored by .gitignore)
│   └── README.md                 # Internal module documentation
│
├── pages/                        # Streamlit page templates (future expansion)
├── src/                          # Shared utilities & common libraries
├── requirements.txt              # Python dependencies
├── ElevateWealth AI Agent.png    # Branding asset
├── README.md                     # ← This file
└── .gitignore                    # Security filters (.env, data/, etc.)
```

> 💡 **Note:**
> The public version keeps the **core logic** (retrieval, voice, API) but excludes all **private datasets** and **API keys**.
> Sensitive paths (e.g. `.env`, `/data/fulltext`, `/data/private_index/`) are safely ignored via `.gitignore`.

---

## 🧠 模块说明 / Module Highlights

### 💰 Wealth Checkup

A financial self-assessment tool calculating asset-liability balance, cash-flow trends, and freedom indicators.

### 🚀 Startup Agent (MinBiz)

Interactive entrepreneurial coach combining **RAG + LLM reasoning**.
Helps users with brand positioning, content ideation, execution SOPs, and growth strategy.

**Core files**

* `voice_agent.py` – Voice I/O handler
* `rag/sqlite_fts.py` – Hybrid retriever (FTS5 + context)
* `server/voice_agent.py` – FastAPI interface for `/ask-business-v1`

### 📈 Investment Agent *(Coming Soon)*

ETF & sector allocation, valuation dashboard, and market signals.

### 🎓 Career Growth *(Planned)*

Guidance for career transitions, professional storytelling, and communication skills.

---

## 🧩 Architecture Flow

graph TD
A[User] --> B[Streamlit app.py]
B --> C1[💰 Wealth Checkup]
B --> C2[🚀 Startup Agent (MinBiz)]
B --> C3[📈 Investment Agent]
B --> C4[🎓 Career Agent]

C2 --> D1[/ask-business-v1 → FastAPI]
D1 --> D2[voice_agent.py → brain.py]
D2 --> D3[rags_search → rag_fts5.db]
D3 --> D4[OpenAI GPT-4o]
D4 --> D5[Return answer + evidence]

---

## 🚀 How to Run (Demo Mode)

```bash
# 1️⃣ Launch main dashboard
streamlit run app.py

# 2️⃣ Start backend for Startup Agent
uvicorn minbiz_agent.src.server.voice_agent:app --reload
```

Access via 👉 [http://localhost:8501](http://localhost:8501)

---

## 💾 Data & Security

| File / Path            | Purpose                       | Public Status |
| ---------------------- | ----------------------------- | ------------- |
| `.env`                 | API keys & secrets            | 🔒 Ignored    |
| `data/`                | Private text chunks & indexes | 🔒 Ignored    |
| `legacy_advanced_rag/` | Deprecated experiments        | 🧩 Archived   |
| `rag_fts5.db`          | Public-safe FTS5 index        | ✅ Included    |

---

## ✨ Author’s Note

Curated and maintained by **Ida Lin** ([@idalin6127](https://github.com/idalin6127))
**ElevateWealth AI** integrates **Wealth Checkup**, **Startup Companion**,
and soon **Investment** & **Career Growth** agents —
forming a **holistic AI-driven Wealth Empowerment Ecosystem**.

> 🕊️ “Empowering intelligent entrepreneurship and financial freedom through AI.”

---

## 📜 License

MIT License © 2025 Ida Lin
*(Public edition excludes private data and API keys.)*
