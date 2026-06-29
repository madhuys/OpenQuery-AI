# How It Works - Architecture Guide

**Project:** OpenQuery AI  
**Version:** 3.5  

---

## Overview

**OpenQuery AI** is an intelligent web search and content analysis system supporting parallel processing, multi-engine search (Google via Serper API and DuckDuckGo), PDF extraction, NLP analysis, and quality scoring.

**Key Features**:
- **Multi-Engine Search**: Google (Serper API) and DuckDuckGo (web, news, videos, scholar)
- **Parallel Content Processing**: High-throughput HTML and PDF processing via ThreadPoolExecutor
- **Multi-Layer SQLite Caching**: Caching queries, raw HTTP responses, processed clean HTML, and extracted PDF contents
- **Dual Quality Scoring**: 70% heuristic scoring + 30% spaCy NLP scoring
- **Background PDF Processing**: Standalone worker for handling large or slow PDF downloads asynchronously

---

## System Architecture & Data Flow

```
┌──────────────────────────────────────────────┐
│ User Query (UI / API)                       │
└──────────────────────┬───────────────────────┘
                       │
                       v
┌──────────────────────────────────────────────┐
│ Search Factory / Provider Abstraction        │ ← Checks Cache / Routes to Engine
│ (SerperProvider / DuckDuckGoProvider)        │
└──────────────────────┬───────────────────────┘
                       │
                       v
┌──────────────────────────────────────────────┐
│ Content Router & Classification              │ ← Separates HTML & PDF URLs
└──────────────────────┬───────────────────────┘
                       │
       ├───────────────┴───────────────┐
       v                               v
┌───────────────┐               ┌───────────────┐
│ HTML Pipeline │               │ PDF Pipeline  │
│  (Parallel)   │               │  (Parallel)   │
└───────┬───────┘               └───────┬───────┘
        │                               │
        v                               v
┌───────────────┐               ┌───────────────┐
│ HTML Extract  │               │ PDF Extract   │
│ (Trafilatura) │               │  (PyMuPDF)    │
└───────┬───────┘               └───────┬───────┘
        │                               │
        └───────────────┬───────────────┘
                        │
                        v
┌──────────────────────────────────────────────┐
│ Quality Scoring (Heuristic 70% + NLP 30%)    │
└──────────────────────┬───────────────────────┘
                       │
                       v
┌──────────────────────────────────────────────┐
│ Multi-Layer SQLite Cache & Output Delivery   │
└──────────────────────────────────────────────┘
```

---

## Settings & Configuration System

**Location**: `config/user_settings.json` (auto-generated from defaults in `config/settings.py`)

**Structure**:
```python
AppSettings
  ├── search: SearchSettings
  │   ├── default_provider ("serper" or "ddg")
  │   ├── search_type ("search", "news", "videos", "scholar")
  │   └── default_query
  ├── analysis: AnalysisSettings
  │   ├── max_workers (default: 10)
  │   ├── url_timeout (default: 10)
  │   └── pdf_timeout (default: 30)
  ├── pdf_scoring: PDFScoringSettings
  └── cache: CacheSettings
```

---

## Multi-Engine Search Providers

- **`BaseSearchProvider`** (`services/base_provider.py`): Abstract base interface.
- **`DuckDuckGoProvider`** (`services/ddg_service.py`): Uses `ddgs` Python library. Completely free, requires no API keys or accounts.
- **`SerperClient`** (`services/serper_service.py`): Connects to Google Serper API.
- **`get_search_provider()`** (`services/search_factory.py`): Instantiates provider based on request parameter or user settings.

---

## Database Caching Architecture

**Database Location**: `db/serper_cache.db` (SQLite in WAL mode for concurrent access)

**Active Schemas (`db/`)**:
- `cache_schema.sql`: Core searches, URLs, and HTML caches
- `cache_schema_pdf.sql`: PDF download attempts and extracted content
- `cache_schema_hybrid.sql`: Hybrid download state tracking
- `cache_schema_embeddings.sql`: Vector embeddings for semantic search
- `migration_pdf_fingerprints.sql`: Content fingerprinting for PDF deduplication

---

## Quality Scoring System

```
final_score = (heuristic_score * 0.7) + (nlp_score * 0.3)
```

- **Heuristic Signals** (`services/helpers/content_scorer.py`): Domain authority (.edu, .gov, .org), content freshness, word count optimization (500-5000 words), title structure, author metadata, HTTPS.
- **NLP Signals** (`services/helpers/nlp_analyzer.py`): spaCy entity recognition (PERSON, ORG, GPE, DATE), Flesch reading ease, sentence length, and vocabulary diversity.

---

## API Endpoints

- `POST /query`: Unified query endpoint routing to selected provider (`"serper"` or `"ddg"`).
- `POST /search`: Web search API.
- `POST /live-search`: Real-time search with optional semantic filtering.
- `POST /analyze-stream`: SSE streaming endpoint for real-time analysis updates.
