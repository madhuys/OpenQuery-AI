"""
Query Normalization and Near-Duplicate Detection
Normalizes user queries and finds near-duplicate cached queries using RapidFuzz
"""
import re
import unicodedata
from typing import Tuple, Optional, List, Dict
from rapidfuzz import fuzz, process


def normalize_query(query: str) -> str:
    """
    Normalize a search query for consistent matching

    1. Trim whitespace
    2. Collapse multiple spaces
    3. Unicode normalize (NFKC - compatibility normalization)
    4. Lowercase
    5. Standardize quotes and punctuation

    Args:
        query: Raw user query

    Returns:
        Normalized query string
    """
    if not query:
        return ""

    # Step 1: Trim whitespace
    query = query.strip()

    # Step 2: Unicode normalize (NFKC - canonical decomposition + compatibility composition)
    # This handles accents, ligatures, etc.
    query = unicodedata.normalize('NFKC', query)

    # Step 3: Lowercase
    query = query.lower()

    # Step 4: Standardize quotes (convert smart quotes to regular quotes)
    quote_map = {
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201a': "'",  # Single low-9 quotation mark
        '\u201b': "'",  # Single high-reversed-9 quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u201e': '"',  # Double low-9 quotation mark
        '\u201f': '"',  # Double high-reversed-9 quotation mark
        '\u2032': "'",  # Prime
        '\u2033': '"',  # Double prime
        '\u00ab': '"',  # Left-pointing double angle quotation mark
        '\u00bb': '"',  # Right-pointing double angle quotation mark
    }

    for smart_quote, regular_quote in quote_map.items():
        query = query.replace(smart_quote, regular_quote)

    # Step 5: Standardize dashes/hyphens (convert em/en dashes to regular hyphen)
    dash_map = {
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2015': '-',  # Horizontal bar
        '\u2212': '-',  # Minus sign
    }

    for special_dash, regular_dash in dash_map.items():
        query = query.replace(special_dash, regular_dash)

    # Step 6: Collapse multiple spaces into single space
    query = re.sub(r'\s+', ' ', query)

    # Step 7: Final trim
    query = query.strip()

    return query


def find_similar_queries(
    query: str,
    cached_queries: List[str],
    threshold: int = 85,
    limit: int = 5
) -> List[Tuple[str, int]]:
    """
    Find similar queries using RapidFuzz's Levenshtein distance

    Args:
        query: Normalized query to match
        cached_queries: List of normalized cached queries
        threshold: Minimum similarity score (0-100, default 85)
        limit: Maximum number of matches to return

    Returns:
        List of (cached_query, score) tuples, sorted by score descending
    """
    if not query or not cached_queries:
        return []

    # Use RapidFuzz's process.extract for efficient fuzzy matching
    # ratio() uses Levenshtein distance for similarity
    matches = process.extract(
        query,
        cached_queries,
        scorer=fuzz.ratio,
        limit=limit,
        score_cutoff=threshold
    )

    # matches is List[Tuple[str, score, index]]
    # Convert to List[Tuple[str, score]]
    return [(match[0], int(match[1])) for match in matches]


def find_best_cache_match(
    query: str,
    cached_queries: List[str],
    threshold: int = 85
) -> Optional[Tuple[str, int]]:
    """
    Find the best matching cached query (highest similarity)

    Args:
        query: Normalized query to match
        cached_queries: List of normalized cached queries
        threshold: Minimum similarity score (0-100, default 85)

    Returns:
        (best_match, score) or None if no match above threshold
    """
    if not query or not cached_queries:
        return None

    matches = find_similar_queries(query, cached_queries, threshold, limit=1)

    if matches:
        return matches[0]

    return None


def get_similarity_score(query1: str, query2: str) -> int:
    """
    Get similarity score between two queries (0-100)

    Args:
        query1: First query (will be normalized)
        query2: Second query (will be normalized)

    Returns:
        Similarity score (0-100, 100 = identical)
    """
    if not query1 or not query2:
        return 0

    # Normalize both queries
    norm1 = normalize_query(query1)
    norm2 = normalize_query(query2)

    # Calculate similarity
    return int(fuzz.ratio(norm1, norm2))


def analyze_query_variants(query: str) -> Dict[str, str]:
    """
    Analyze a query and show its normalized variants
    Useful for debugging/testing normalization

    Args:
        query: Raw query

    Returns:
        Dict with original, normalized, and analysis info
    """
    normalized = normalize_query(query)

    return {
        'original': query,
        'normalized': normalized,
        'length_original': len(query),
        'length_normalized': len(normalized),
        'word_count': len(normalized.split()),
        'has_unicode': any(ord(c) > 127 for c in query),
        'has_smart_quotes': any(c in query for c in '\u2018\u2019\u201c\u201d'),
        'has_special_dashes': any(c in query for c in '\u2013\u2014\u2015'),
        'trimmed': query != query.strip(),
        'had_multiple_spaces': bool(re.search(r'\s{2,}', query))
    }
