"""
Content Hashing and Normalization Utilities
Provides consistent content fingerprinting for cache deduplication.
"""

import hashlib
import re


def compute_content_hash(html: str) -> str:
    """
    Compute SHA-256 hash of normalized HTML content.

    Normalization removes:
    - <script> tags and content
    - <style> tags and content
    - HTML comments
    - Excessive whitespace
    - Ad containers (common class patterns)

    This ensures content changes are detected while ignoring cosmetic/ad changes.

    Args:
        html: Raw HTML string

    Returns:
        SHA-256 hex digest

    Example:
        >>> compute_content_hash("<html><head><script>...</script></head><body>Content</body></html>")
        '5d41402abc4b2a76b9719d911017c592...'
    """
    if not html:
        return hashlib.sha256(b'').hexdigest()

    # Remove scripts and styles
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove comments
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Remove common ad containers (heuristic)
    html = re.sub(r'<div[^>]*class="[^"]*\b(ad|advertisement|advert|sponsored)\b[^"]*"[^>]*>.*?</div>',
                 '', html, flags=re.DOTALL | re.IGNORECASE)

    # Collapse whitespace
    html = re.sub(r'\s+', ' ', html)
    html = html.strip()

    return hashlib.sha256(html.encode('utf-8')).hexdigest()


def normalize_text(text: str) -> str:
    """
    Normalize text content for comparison.

    Removes:
    - Extra whitespace
    - Leading/trailing space
    - Non-breaking spaces

    Args:
        text: Raw text string

    Returns:
        Normalized text
    """
    if not text:
        return ""

    # Replace non-breaking spaces
    text = text.replace('\xa0', ' ')
    text = text.replace('\u200b', '')  # Zero-width space

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text
