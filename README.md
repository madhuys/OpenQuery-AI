# OpenQuery AI

> **Provider-Agnostic Intelligent Web Search, Content Extraction & NLP Analysis Platform**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![Backend Framework](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Frontend UI](https://img.shields.io/badge/frontend-Streamlit-FF4B4B.svg)](https://streamlit.io)
[![Storage Engine](https://img.shields.io/badge/storage-SQLite%20%28WAL%29-003B57.svg)](https://sqlite.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**OpenQuery AI** is a high-performance, autonomous web intelligence and content analysis platform. Built with a unified search engine provider architecture, OpenQuery AI seamlessly orchestrates searches across **DuckDuckGo** (free, zero API keys required) and **Google** (via Serper API), automatically extracting HTML and PDF content, executing parallel processing pipelines, and applying spaCy-powered NLP quality scoring in real time.

---

## 🚀 Architectural Overview

OpenQuery AI features a decoupled architecture with a FastAPI backend server, parallel content extraction pipelines, multi-layer SQLite caching, and an interactive Streamlit dashboard.

```
                  ┌───────────────────────────────┐
                  │   User Query (Web UI / API)   │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │     Search Provider Layer     │
                  │   (search_factory.py)         │
                  └──────┬─────────────────┬──────┘
                         │                 │
     DuckDuckGo (Free)   │                 │ Google (Serper API)
     (ddg_service.py)    ▼                 ▼ (serper_service.py)
                  ┌──────────────┐  ┌──────────────┐
                  │  DDG Engine  │  │ Serper Client│
                  └──────┬───────┘  └──────┬───────┘
                         │                 │
                         └────────┬────────┘
                                  │ Standardized Search Results
                                  ▼
                  ┌───────────────────────────────┐
                  │  Content Router & Pipelines   │
                  │  (ThreadPoolExecutor Pool)    │
                  └──────┬─────────────────┬──────┘
                         │                 │
             HTML URLs   │                 │ PDF URLs
                         ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐
                  │  Trafilatura │  │ PyMuPDF /    │ Fast Lane (30s) /
                  │  Extractor   │  │ pdfplumber   │ Background Worker
                  └──────┬───────┘  └──────┬───────┘
                         │                 │
                         └────────┬────────┘
                                  │ Extracted Content & Text
                                  ▼
                  ┌───────────────────────────────┐
                  │     Quality Scoring Engine    │
                  │ (70% Heuristic + 30% spaCy NLP)│
                  └──────────────┬────────────────┘
                                 │ Scored Web Intelligence
                                 ▼
                  ┌───────────────────────────────┐
                  │ Multi-Layer SQLite Cache Store│
                  │  (WAL Mode / serper_cache.db) │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │ Streamlit Interactive Dashboard│
                  └───────────────────────────────┘
```

---

## 🌟 Key Features

* 🔍 **Multi-Engine Search Provider**: Unified abstraction supporting **DuckDuckGo** out-of-the-box (no API key required) and **Google** (via Serper API) across Web, News, Videos, and Scholar tabs.
* ⚡ **High-Throughput Parallel Execution**: Multi-threaded I/O processing pool (`ContentRouter`) capable of concurrently fetching, parsing, and cleaning dozens of web pages and PDF documents in seconds.
* 📄 **Dual-Lane PDF Extraction Pipeline**: Advanced PDF processing featuring a fast-lane UI worker (30s timeout) and an asynchronous background worker (`background_worker.py`) for heavy or slow PDF downloads.
* 🧠 **Hybrid Quality Scoring Engine**: Combines 70% heuristic domain authority, freshness, and word count evaluation with 30% spaCy NLP entity extraction, readability analysis, and vocabulary diversity scoring.
* 💾 **Multi-Layer SQLite Caching Store**: Powered by SQLite in Write-Ahead Logging (WAL) mode for thread-safe concurrent access across raw HTTP responses, processed clean text, and vector embedding snapshots.
* ⚙️ **Comprehensive Management UI**: Multi-page Streamlit application (`app.py`, `pages/`) featuring centralized settings management with 50+ configurable parameters, real-time search history tracking, and manual PDF upload scoring.

---

## 🛠️ Quick Start

### Prerequisites
* Python 3.10+
* Internet connection for web scraping and search engines

### 1. Clone & Install Dependencies
```bash
git clone <your-repository-url> && cd serper-search-app
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure Search Engines (Optional)
* **DuckDuckGo (Default)**: Requires **NO API KEY**. Ready to use immediately!
* **Google (Serper API - Optional)**: If using Serper, add your key to a `.env` file:
```env
SERPER_API_KEY=your_serper_api_key_here
```

---

## 💡 Usage & Workflow

### 1. Run the Application
Open two terminal windows or use the convenience script:

**Terminal 1 - FastAPI Backend:**
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 - Streamlit Frontend:**
```bash
streamlit run app.py
```

*Alternatively, run the clean restart script:*
```bash
./restart.sh
```

### 2. Access Dashboards & Documentation
* **Streamlit Web Dashboard**: `http://localhost:8501`
* **FastAPI Interactive Docs**: `http://localhost:8000/docs`
* **API Health Check**: `http://localhost:8000`

### 3. Run Automated Unit Tests
Verify search providers, factory dispatch, and engine execution:
```bash
pytest tests/
```

---

## 📁 Repository Structure

```
serper-search-app/
├── config/                    # Configuration dataclasses & user preferences
│   ├── settings.py            # Centralized settings dataclasses
│   └── user_settings.json     # Auto-generated user settings override
├── db/                        # Database schemas & SQLite cache engine
│   ├── cache_schema.sql       # Core searches & HTML cache schema
│   ├── cache_schema_pdf.sql   # PDF metadata & extracted content schema
│   ├── cache_schema_hybrid.sql# Hybrid download state schema
│   ├── cache_schema_embeddings.sql # Vector embedding cache schema
│   └── serper_cache.db        # Active SQLite database (WAL mode)
├── docs/                      # Technical architecture documentation
│   ├── AGENT_CONTEXT.md       # AI agent context & quick reference guide
│   ├── HOW_IT_WORKS.md        # Detailed architecture & pipeline flow
│   └── superpowers/           # Superpowers design specs & execution plans
├── pages/                     # Streamlit multi-page application
│   ├── 2_🗂️_History.py        # Search history viewer & manual PDF upload
│   ├── 3_⚙️_Settings.py       # Comprehensive application settings manager
│   ├── 4_🔍_Live_Search.py    # Real-time search with semantic matching
│   ├── 5_🔍_Search_V2.py      # Search V2 interface
│   ├── 6_🔍_Search_V3.py      # Search V3 semantic interface
│   └── home.py                # Main home page renderer
├── services/                  # Core Python business logic & engines
│   ├── base_provider.py       # Abstract Base Search Provider interface
│   ├── ddg_service.py         # DuckDuckGo search provider (free engine)
│   ├── serper_service.py      # Google Serper API search provider
│   ├── search_factory.py      # Search provider factory & query helpers
│   ├── router_service.py      # Parallel URL classifier & worker orchestrator
│   ├── cache_service.py       # Unified cache facade
│   ├── html_service.py        # Trafilatura HTML extraction & cleaning
│   ├── pdf_service.py         # PDF download & fast-lane extraction
│   └── helpers/               # NLP, scoring, and date utilities
├── tests/                     # Automated test suite
│   └── test_search_providers.py # Pytest unit tests for search providers
├── app.py                     # Streamlit entrypoint script
├── main.py                    # FastAPI backend server entrypoint
├── background_worker.py       # Asynchronous PDF background processor
├── restart.sh                 # Convenient Linux/WSL clean restart script
├── start.bat                  # Windows batch runner script
└── requirements.txt           # Python package dependencies
```

---

## 👤 Author & Maintainer

* **Developer**: [@madhuys](https://github.com/madhuys)
* **GitHub**: [github.com/madhuys](https://github.com/madhuys)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
