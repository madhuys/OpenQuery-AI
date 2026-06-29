"""
Services Package
Contains all business logic services
"""
from .base_provider import BaseSearchProvider
from .serper_service import SerperClient
from .ddg_service import DuckDuckGoProvider
from .search_factory import get_search_provider, search_and_extract

__all__ = [
    "BaseSearchProvider",
    "SerperClient",
    "DuckDuckGoProvider",
    "get_search_provider",
    "search_and_extract"
]
