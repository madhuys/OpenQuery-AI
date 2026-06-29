# Design Document: OpenQuery AI & DuckDuckGo Search Integration

**Date:** 2026-06-29  
**Status:** Approved  
**Project:** OpenQuery AI (formerly Serper Search App)

---

## 1. Overview
This project transforms the existing Serper Search App into **OpenQuery AI**, a provider-agnostic, multi-engine intelligent search and NLP content analysis platform. In addition to Google (via Serper API), OpenQuery AI integrates **DuckDuckGo (DDG)** search using a clean unified provider abstraction layer.

---

## 2. Goals & Objectives
1. **Rebrand**: Update application identity across FastAPI backend, Streamlit frontend, and documentation to OpenQuery AI.
2. **Unified Provider Architecture**: Refactor search functionality into abstract search providers (`SerperProvider` and `DuckDuckGoProvider`).
3. **DuckDuckGo Integration**: Support web, news, and video search via DuckDuckGo without requiring paid API keys.
4. **User Preference & Control**: Allow users to select their preferred search engine dynamically via UI controls and save defaults in configuration.

---

## 3. Architecture & Detailed Component Design

### 3.1 Base Search Provider Abstraction (`services/base_provider.py`)
Create `BaseSearchProvider` as an abstract class defining standard operations:
- `search(query: str, search_type: str, num: int, ...)` -> Dict (normalized raw response format)
- `extract_urls(results: Dict, search_type: str)` -> List[Dict] (`[{'url': ..., 'title': ..., 'snippet': ...}]`)

### 3.2 Provider Implementations (`services/`)
- `services/serper_service.py`: Refactor `SerperClient` to inherit from `BaseSearchProvider`.
- `services/ddg_service.py`: Implement `DuckDuckGoClient` inheriting from `BaseSearchProvider` using `duckduckgo_search.DDGS`. Maps DDG outputs to normalized search response structures.
- `services/search_factory.py`: Provides `get_search_provider(name: str)` factory function to instantiate the requested provider.

### 3.3 Configuration (`config/settings.py`)
- Add `default_provider: Literal["serper", "ddg"] = "serper"` to `SearchSettings`.
- Update `user_settings.json` serialization and default configuration loading.

### 3.4 API Layer (`main.py`)
- Update OpenAPI title to "OpenQuery AI API".
- Update `SearchRequest` and `LiveSearchRequest` models to include `provider: Optional[Literal["serper", "ddg"]] = None`.
- Dynamically instantiate providers via `get_search_provider()` based on request payload or global config.

### 3.5 Frontend UI (`app.py`, `pages/`, `components/`)
- Update page title to "OpenQuery AI".
- Update `components/search_panel_v2.py` and search UI tabs to include a provider selector (`Google (Serper)` / `DuckDuckGo`).
- Update `pages/3_⚙️_Settings.py` to allow setting the default search provider.

---

## 4. Error Handling & Edge Cases
- **DDG Rate Limiting**: If DuckDuckGo rate-limits requests, catch `RatelimitException` and return a user-friendly error message or fallback to Serper if API key is available.
- **Dependency Management**: Ensure `duckduckgo_search` is added to `requirements.txt`.
- **Schema Normalization**: Ensure URL extraction output consistently returns `url`, `title`, and `snippet` fields regardless of provider.

---

## 5. Verification & Testing Plan
1. **Dependency Installation**: Verify `duckduckgo_search` installs smoothly in `requirements.txt`.
2. **Backend Unit/API Tests**: Test `/query` and `/search` endpoints using both `provider="serper"` and `provider="ddg"`.
3. **Frontend E2E Validation**: Run Streamlit app and verify search engine selection works and populates analysis pipelines.
