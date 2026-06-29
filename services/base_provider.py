"""
Abstract Base Search Provider for OpenQuery AI
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


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
        """
        Execute search query and return raw dictionary
        """
        pass

    @abstractmethod
    def extract_urls(self, results: Dict, search_type: str = "search") -> List[Dict]:
        """
        Extract standardized URL list [{'url': ..., 'title': ..., 'snippet': ...}] from raw results
        """
        pass
