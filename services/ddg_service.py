"""
DuckDuckGo Search Provider implementation for OpenQuery AI
"""
from typing import Dict, List, Optional
try:
    from ddgs import DDGS
except ImportError:
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

        try:
            if search_type == "news":
                results = ddgs.news(query, max_results=num)
                if results:
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
                if results:
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
                if results:
                    for r in results:
                        raw_output.append({
                            "title": r.get("title", ""),
                            "link": r.get("href", ""),
                            "snippet": r.get("body", "")
                        })
                return {"organic": raw_output}
        except Exception as e:
            # Handle potential API / rate limit exceptions cleanly
            print(f"[DDG Provider Error] {e}")
            if search_type == "news":
                return {"news": []}
            elif search_type == "videos":
                return {"videos": []}
            return {"organic": []}

    def extract_urls(self, results: Dict, search_type: str = "search") -> List[Dict]:
        urls = []
        key = "organic"
        if search_type == "news":
            key = "news"
        elif search_type == "videos":
            key = "videos"
        elif search_type == "scholar":
            key = "organic"

        for item in results.get(key, []):
            if "link" in item and item["link"]:
                urls.append({
                    "url": item["link"],
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "")
                })
        return urls
