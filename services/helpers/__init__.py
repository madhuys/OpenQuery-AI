"""
Helper utilities for OpenQuery AI application

This package contains utility modules for:
- Content quality scoring
- NLP analysis
- Date provenance detection
- HTTP freshness checking
- PDF processing and extraction
- URL normalization and domain extraction
- Content hashing and normalization
"""

from .content_scorer import ContentScorer
from .nlp_analyzer import NLPAnalyzer
from .date_provenance import DateProvenanceDetector
from .freshness_checker import FreshnessChecker
from .pdf_processor import (
    extract_pdf_title,
    extract_pdf_date,
    extract_pdf_text,
    process_pdf,
    validate_pdf
)
from .url_utils import normalize_url, extract_domain, DEFAULT_TRACKING_PARAMS
from .content_utils import compute_content_hash, normalize_text

__all__ = [
    'ContentScorer',
    'NLPAnalyzer',
    'DateProvenanceDetector',
    'FreshnessChecker',
    'extract_pdf_title',
    'extract_pdf_date',
    'extract_pdf_text',
    'process_pdf',
    'validate_pdf',
    'normalize_url',
    'extract_domain',
    'DEFAULT_TRACKING_PARAMS',
    'compute_content_hash',
    'normalize_text',
]
