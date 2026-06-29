"""
Serper API Service
Handles user input → Serper API → returns URLs
Clean separation of concerns
"""
import os
import requests
from typing import Dict, List, Optional, Literal
from dotenv import load_dotenv
from config.settings import AppSettings, SETTINGS_FILE
from services.base_provider import BaseSearchProvider

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_BASE_URL = "https://google.serper.dev"


class SerperClient(BaseSearchProvider):
    """Clean Serper API client - just fetches search results"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or SERPER_API_KEY
        # Load analysis settings
        self.settings = AppSettings.load(SETTINGS_FILE).analysis

    def search(
        self,
        query: str,
        search_type: Literal["search", "news", "videos", "scholar"] = "search",
        gl: Optional[str] = None,
        hl: Optional[str] = None,
        location: Optional[str] = None,
        num: int = 10,
        page: int = 1,
        tbs: Optional[str] = None,
        autocorrect: Optional[bool] = None,
        nfpr: Optional[bool] = None,
        safe: Optional[Literal["active", "off"]] = None
    ) -> Dict:
        """
        Call Serper API and return raw results

        Returns:
            Dict with 'results' containing search results
        """
        if not self.api_key:
            raise ValueError("SERPER_API_KEY not found in environment")
        endpoint_map = {
            "search": f"{SERPER_BASE_URL}/search",
            "news": f"{SERPER_BASE_URL}/news",
            "videos": f"{SERPER_BASE_URL}/videos",
            "scholar": f"{SERPER_BASE_URL}/scholar"
        }

        endpoint = endpoint_map.get(search_type, f"{SERPER_BASE_URL}/search")

        # Build payload
        payload = {"q": query}

        # Add optional parameters
        if gl: payload["gl"] = gl
        if hl: payload["hl"] = hl
        if location: payload["location"] = location
        if num: payload["num"] = num
        if page: payload["page"] = page
        if tbs: payload["tbs"] = tbs
        if autocorrect is not None: payload["autocorrect"] = autocorrect
        if nfpr is not None: payload["nfpr"] = nfpr
        if safe: payload["safe"] = safe

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=self.settings.url_timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Serper API error: {str(e)}")

    def extract_urls(self, results: Dict, search_type: str = "search") -> List[Dict]:
        """
        Extract URLs from Serper results

        Returns:
            List of dicts with 'url' and 'title'
        """
        urls = []

        # Different search types have different structures
        if search_type == "search":
            # Organic results
            for result in results.get("organic", []):
                if "link" in result:
                    urls.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", "")
                    })

        elif search_type == "news":
            for result in results.get("news", []):
                if "link" in result:
                    urls.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", "")
                    })

        elif search_type == "videos":
            for result in results.get("videos", []):
                if "link" in result:
                    urls.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", "")
                    })

        elif search_type == "scholar":
            for result in results.get("organic", []):
                if "link" in result:
                    urls.append({
                        "url": result["link"],
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", "")
                    })
                # Also check for PDF links in scholar results
                if "resources" in result:
                    for resource in result["resources"]:
                        if "link" in resource:
                            urls.append({
                                "url": resource["link"],
                                "title": result.get("title", "") + " (PDF)",
                                "snippet": result.get("snippet", "")
                            })

        return urls


# Convenience function
def search_and_extract(
    query: str,
    search_type: str = "search",
    **kwargs
) -> tuple[Dict, List[Dict]]:
    """
    One-shot: search + extract URLs

    Returns:
        (raw_results, url_list)
    """
    client = SerperClient()
    results = client.search(query, search_type, **kwargs)
    urls = client.extract_urls(results, search_type)
    return results, urls
