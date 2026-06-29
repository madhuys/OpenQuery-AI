# OpenQuery AI & DuckDuckGo Search Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Serper Search App into OpenQuery AI with a unified multi-engine architecture supporting both Serper and DuckDuckGo search providers.

**Architecture:** Create an abstract base class `BaseSearchProvider` in `services/base_provider.py`. Refactor `serper_service.py` into a `SerperProvider` class and implement a new `DuckDuckGoProvider` in `services/ddg_service.py` using `duckduckgo_search`. Update settings, FastAPI backend endpoints, and Streamlit UI to allow runtime selection of search engine providers.

**Tech Stack:** Python 3.8+, FastAPI, Streamlit, duckduckgo_search, requests, pydantic, dataclasses.

---

### Task 1: Add dependencies & Abstract Base Provider Interface

**Files:**
- Modify: `requirements.txt`
- Create: `services/base_provider.py`
- Modify: `services/__init__.py`

- [ ] **Step 1: Add duckduckgo_search to requirements.txt**

```text
duckduckgo_search>=6.0.0
```

- [ ] **Step 2: Install dependencies**

Run: `pip install duckduckgo_search>=6.0.0`

- [ ] **Step 3: Create services/base_provider.py**

```python
"""
Abstract Base Search Provider for OpenQuery AI
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Literal

class BaseSearchProvider(ABC):
    """Abstract search provider interface"""

    @abstractmethod
    def search(
        self,
        query: str,
        search_type: str = "search",
        gl: Optional[str] = None,
        hl: Optional[str] = None,
        location: Optional[str] = None,
        num: int = 10,
        page: int = 1,
        **kwargs
    ) -> Dict:
        """Execute search query and return normalized raw dictionary"""
        pass

    @abstractmethod
    def extract_urls(self, results: Dict, search_type: str = "search") -> List[Dict]:
        """Extract standardized URL list [{'url': ..., 'title': ..., 'snippet': ...}] from raw results"""
        pass
```

- [ ] **Step 4: Update services/__init__.py to export BaseSearchProvider**

```python
from .base_provider import BaseSearchProvider
```

---

### Task 2: Implement DuckDuckGo Search Provider & Search Factory

**Files:**
- Create: `services/ddg_service.py`
- Modify: `services/serper_service.py`
- Create: `services/search_factory.py`
- Modify: `services/__init__.py`

- [ ] **Step 1: Create services/ddg_service.py**

```python
"""
DuckDuckGo Search Provider implementation
"""
from typing import Dict, List, Optional
from duckduckgo_search import DDGS
from services.base_provider import BaseSearchProvider

class DuckDuckGoProvider(BaseSearchProvider):
    """DuckDuckGo provider implementation using duckduckgo_search"""

    def search(
        self,
        query: str,
        search_type: str = "search",
        gl: Optional[str] = None,
        hl: Optional[str] = None,
        location: Optional[str] = None,
        num: int = 10,
        page: int = 1,
        **kwargs
    ) -> Dict:
        ddgs = DDGS()
        raw_output = []

        if search_type == "news":
            results = ddgs.news(query, max_results=num)
            for r in results:
                raw_output.append({
                    "title": r.get("title", ""),
                    "link": r.get("url", ""),
                    "snippet": r.get("body", ""),
                    "date": r.get("date", "")
                })
            return {"news": raw_output}
        elif search_type == "videos":
            results = ddgs.videos(query, max_results=num)
            for r in results:
                raw_output.append({
                    "title": r.get("title", ""),
                    "link": r.get("content", "") or r.get("url", ""),
                    "snippet": r.get("description", "")
                })
            return {"videos": raw_output}
        else:
            # Organic text search
            results = ddgs.text(query, max_results=num)
            for r in results:
                raw_output.append({
                    "title": r.get("title", ""),
                    "link": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
            return {"organic": raw_output}

    def extract_urls(self, results: Dict, search_type: str = "search") -> List[Dict]:
        urls = []
        key = "organic"
        if search_type == "news":
            key = "news"
        elif search_type == "videos":
            key = "videos"

        for item in results.get(key, []):
            if "link" in item and item["link"]:
                urls.append({
                    "url": item["link"],
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "")
                })
        return urls
```

- [ ] **Step 2: Modify services/serper_service.py to inherit from BaseSearchProvider**

Inherit `SerperClient` from `BaseSearchProvider` and update imports.

- [ ] **Step 3: Create services/search_factory.py**

```python
"""
Factory for search provider instantiation
"""
from typing import Optional
from services.base_provider import BaseSearchProvider
from services.serper_service import SerperClient
from services.ddg_service import DuckDuckGoProvider

def get_search_provider(provider_name: str = "serper") -> BaseSearchProvider:
    provider_name_clean = (provider_name or "serper").lower()
    if provider_name_clean == "ddg" or provider_name_clean == "duckduckgo":
        return DuckDuckGoProvider()
    return SerperClient()
```

---

### Task 3: Update Configuration and App Settings

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: Update SearchSettings in config/settings.py**

Add `default_provider: str = "serper"` to `SearchSettings`.

---

### Task 4: Update FastAPI Backend for Provider Dispatch & Rebranding

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update app title and request models in main.py**
Update title to `"OpenQuery AI API"`.
Add `provider: Optional[str] = "serper"` to `SearchRequest` and `LiveSearchRequest`.

- [ ] **Step 2: Update endpoint handlers to use get_search_provider(req.provider)**
Dispatch `/query`, `/search`, and `/live-search` through `get_search_provider()`.

---

### Task 5: Update Streamlit UI Components and Rebrand Pages

**Files:**
- Modify: `app.py`
- Modify: `components/search_panel_v2.py`
- Modify: `components/api_client.py`
- Modify: `pages/3_⚙️_Settings.py`
- Modify: `pages/home.py`

- [ ] **Step 1: Rebrand app.py to OpenQuery AI**
Set `page_title="OpenQuery AI"`.

- [ ] **Step 2: Update Search UI components to include Search Engine Selector**
Add provider select dropdown (`Google (Serper)` / `DuckDuckGo`) in `components/search_panel_v2.py` and pass `provider` parameter to API calls.

---

### Verification & Testing
Run backend and frontend to verify searching with both Serper and DuckDuckGo works as expected.
