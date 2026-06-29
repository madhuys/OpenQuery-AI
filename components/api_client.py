"""
API Client for FastAPI backend
All API calls centralized here
"""
import requests
from typing import Dict, Any, Optional, List
from config.settings import AppSettings, SETTINGS_FILE

# API endpoint - use 127.0.0.1 instead of localhost to avoid DNS resolution delay in WSL2
API_BASE_URL = "http://127.0.0.1:8000"

# Load settings
settings = AppSettings.load(SETTINGS_FILE)


def check_api_status() -> tuple[bool, int]:
    """Check if API is running

    Returns:
        tuple: (is_running: bool, status_code: int)
    """
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=settings.analysis.api_health_timeout)
        return (response.status_code == 200, response.status_code)
    except:
        return (False, 0)


def get_gpu_status() -> Optional[Dict[str, Any]]:
    """Get GPU status from API

    Returns:
        dict: GPU status data or None if unavailable
    """
    try:
        response = requests.get(f"{API_BASE_URL}/gpu-status", timeout=settings.analysis.api_health_timeout)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def search_query(payload: Dict[str, Any]) -> requests.Response:
    """Execute search query via API

    Args:
        payload: Search parameters

    Returns:
        Response object from API
    """
    return requests.post(
        f"{API_BASE_URL}/query",
        json=payload,
        timeout=settings.analysis.pdf_timeout
    )


def analyze_stream(payload: Dict[str, Any], timeout: int = 300):
    """Stream analysis results from API
    
    Args:
        payload: Analysis parameters
        timeout: Request timeout in seconds
        
    Returns:
        Streaming response context manager
    """
    return requests.post(
        f"{API_BASE_URL}/analyze-stream",
        json=payload,
        stream=True,
        timeout=timeout
    )


def process_pdfs(pdf_results: List[Dict], enable_spacy: bool = True, 
                spacy_require_gpu: bool = False, timeout: int = 300) -> requests.Response:
    """Process PDFs via API
    
    Args:
        pdf_results: List of PDF result objects
        enable_spacy: Enable spaCy NLP processing
        spacy_require_gpu: Require GPU for spaCy
        timeout: Request timeout in seconds
        
    Returns:
        Response object from API
    """
    payload = {
        "pdf_results": pdf_results,
        "enable_spacy": enable_spacy,
        "spacy_require_gpu": spacy_require_gpu
    }
    
    return requests.post(
        f"{API_BASE_URL}/process-pdfs",
        json=payload,
        timeout=timeout
    )


def get_failed_pdfs() -> requests.Response:
    """Get list of failed PDF downloads
    
    Returns:
        Response object from API
    """
    return requests.get(f"{API_BASE_URL}/failed-pdfs")


def retry_pdf_download(url: str, timeout: int = 30) -> requests.Response:
    """Retry downloading a failed PDF
    
    Args:
        url: PDF URL to retry
        timeout: Download timeout in seconds
        
    Returns:
        Response object from API
    """
    return requests.post(
        f"{API_BASE_URL}/retry-pdf",
        json={"url": url, "timeout": timeout}
    )
