"""
URL Normalization and Domain Extraction Utilities
Provides consistent URL canonicalization and domain identification for caching.
"""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import tldextract
import hashlib


# Tracking parameters to strip during normalization
DEFAULT_TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'msclkid', 'mc_cid', 'mc_eid', '_ga', 'ref', 'source'
}


def normalize_url(url: str, tracking_params: set = None) -> str:
    """
    Normalize URL to canonical form for deduplication.

    Rules:
    - Lowercase scheme + host
    - Remove default ports (80, 443)
    - Sort and strip tracking params
    - Remove trailing "/" except bare host root
    - Keep path, preserve significant query params

    Args:
        url: Raw URL string
        tracking_params: Set of tracking params to strip (uses DEFAULT if None)

    Returns:
        Normalized canonical URL

    Example:
        >>> normalize_url("HTTP://Example.com:80/Path/?utm_source=google&id=123")
        'http://example.com/path?id=123'
    """
    if tracking_params is None:
        tracking_params = DEFAULT_TRACKING_PARAMS

    parsed = urlparse(url.strip())

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ''

    # Normalize localhost variants to canonical form (127.0.0.1)
    # This ensures cache hits work regardless of how the URL is formed
    if hostname in ('localhost', '0.0.0.0', '::1', '::'):
        hostname = '127.0.0.1'

    netloc = hostname

    # Add port if non-default
    port = parsed.port
    if port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)):
        netloc = f"{netloc}:{port}"

    # Parse and filter query params
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered_params = {
        k: v for k, v in query_params.items()
        if k.lower() not in tracking_params
    }

    # Sort params for consistency
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

    # Clean path (remove trailing slash except root)
    path = parsed.path
    if path != '/' and path.endswith('/'):
        path = path.rstrip('/')

    # Reconstruct
    normalized = urlunparse((
        scheme,
        netloc,
        path or '/',
        parsed.params,
        sorted_query,
        ''  # Remove fragment
    ))

    return normalized


def extract_domain(url: str) -> str:
    """
    Extract registrable domain using public suffix list.

    Args:
        url: URL to extract domain from

    Returns:
        Registrable domain (e.g., 'example.co.uk')

    Example:
        >>> extract_domain("https://www.example.co.uk/path")
        'example.co.uk'
    """
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}" if extracted.domain else extracted.suffix


def compute_content_hash(content: str) -> str:
    """
    Compute MD5 hash of content for deduplication/doc_id generation.

    Args:
        content: Content string to hash (typically URL + first 1000 chars of text)

    Returns:
        16-character MD5 hash prefix

    Example:
        >>> compute_content_hash("https://example.com" + "Sample text...")
        '2acfc43c9514920a'
    """
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
