# Agent Context - Quick Reference

**For AI Agents working on this codebase**  
**Project:** OpenQuery AI  

## Architecture Overview

```
User Query → Search Factory (DDG / Serper) → Content Router → [HTML | PDF Pipeline] → Quality Scorer → SQLite Cache → Output
```

**Key Pattern**: Multi-engine provider abstraction with parallel worker pools and multi-layer caching.

---

## Core Files & Modules

| File | Purpose |
|------|---------|
| `main.py` | FastAPI backend server (port 8000) |
| `app.py` | Streamlit multi-page frontend UI (port 8501) |
| `background_worker.py` | Standalone PDF background processor |
| `config/settings.py` | Centralized settings dataclasses |
| `services/base_provider.py` | Abstract base class for search engine providers |
| `services/ddg_service.py` | DuckDuckGo search provider (`ddgs`) |
| `services/serper_service.py` | Google Serper API search provider |
| `services/search_factory.py` | Provider factory and search helpers |
| `services/router_service.py` | Content classification and parallel worker orchestrator |
| `services/cache_service.py` | Unified cache facade |

---

## Cache System & Database

- **Database Path**: `db/serper_cache.db` (SQLite with WAL mode)
- **Active Schemas**:
  - `db/cache_schema.sql` - Core searches and HTML caches
  - `db/cache_schema_pdf.sql` - PDF metadata and extracted text
  - `db/cache_schema_hybrid.sql` - Download state tracking
  - `db/cache_schema_embeddings.sql` - Semantic vector embeddings
  - `db/migration_pdf_fingerprints.sql` - Content hashing migration

---

## Quality Scoring Formula

`final_score = (heuristic_score * 0.7) + (nlp_score * 0.3)`

- **Heuristic** (`services/helpers/content_scorer.py`): Domain authority, freshness, word count, metadata, structured tags.
- **NLP** (`services/helpers/nlp_analyzer.py`): spaCy entity extraction, readability scores, text diversity.
