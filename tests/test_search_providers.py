"""
Unit tests for OpenQuery AI search providers and factory
"""
from services.search_factory import get_search_provider, search_and_extract
from services.ddg_service import DuckDuckGoProvider
from services.serper_service import SerperClient


def test_search_factory_default():
    """Test factory returns SerperClient by default or for serper"""
    provider = get_search_provider("serper")
    assert isinstance(provider, SerperClient)


def test_search_factory_ddg():
    """Test factory returns DuckDuckGoProvider for ddg"""
    provider = get_search_provider("ddg")
    assert isinstance(provider, DuckDuckGoProvider)


def test_ddg_search_execution():
    """Test DuckDuckGo search execution and URL extraction"""
    provider = DuckDuckGoProvider()
    results = provider.search("pytest python testing", search_type="search", num=3)
    assert "organic" in results
    urls = provider.extract_urls(results, search_type="search")
    assert isinstance(urls, list)
