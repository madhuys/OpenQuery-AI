"""
Factory for search provider instantiation in OpenQuery AI
"""
from typing import Optional, Dict, List, Tuple
from services.base_provider import BaseSearchProvider
from services.serper_service import SerperClient
from services.ddg_service import DuckDuckGoProvider


def get_search_provider(provider_name: Optional[str] = "serper") -> BaseSearchProvider:
    """
    Get instantiated search provider based on requested engine name
    """
    name = (provider_name or "serper").lower().strip()
    if name in ["ddg", "duckduckgo"]:
        return DuckDuckGoProvider()
    return SerperClient()


def search_and_extract(
    query: str,
    search_type: str = "search",
    provider: Optional[str] = "serper",
    **kwargs
) -> Tuple[Dict, List[Dict]]:
    """
    Unified one-shot search + extract URLs across configured provider
    """
    client = get_search_provider(provider)
    results = client.search(query, search_type=search_type, **kwargs)
    urls = client.extract_urls(results, search_type=search_type)
    return results, urls
