"""
Date Provenance Detection
Extracts publication/update dates from HTML using fallback strategy
"""

import re
import json
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from bs4 import BeautifulSoup
import extruct
from dateutil import parser as date_parser


class DateProvenanceDetector:
    """Detect published/updated dates from HTML with source tracking"""

    # Priority order (highest to lowest confidence)
    SOURCES = [
        'jsonld',  # JSON-LD structured data
        'og',  # OpenGraph / Twitter / meta tags
        'byline',  # Visible text patterns
        'http_last_modified',  # HTTP header (weak)
        'sitemap',  # From sitemap (if available)
        'feed',  # From RSS/Atom feed (if available)
        'none'  # No date found
    ]

    # Common date patterns in visible text
    BYLINE_PATTERNS = [
        r'Published[\s:]+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',  # Published: January 15, 2024
        r'Published[\s:]+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})',  # Published: 15 January 2024
        r'Updated[\s:]+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})',  # Updated: January 15, 2024
        r'Updated[\s:]+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})',  # Updated: 15 January 2024
        r'(\d{4}-\d{2}-\d{2})',  # ISO format: 2024-01-15
    ]

    def __init__(self):
        pass

    def detect_dates(
        self,
        html: str,
        http_last_modified: Optional[str] = None,
        sitemap_lastmod: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract publication and update dates from HTML.

        Priority order:
        1. JSON-LD (datePublished, dateModified)
        2. OpenGraph / meta tags
        3. Visible bylines
        4. HTTP Last-Modified header
        5. Sitemap lastmod
        6. None

        Args:
            html: Full HTML content
            http_last_modified: HTTP Last-Modified header value
            sitemap_lastmod: Lastmod from sitemap (if available)

        Returns:
            {
                'published_at': datetime | None,
                'updated_at': datetime | None,
                'published_source': str,
                'updated_source': str,
                'all_candidates': {...}  # All found dates for debugging
            }
        """
        soup = BeautifulSoup(html, 'html.parser')
        candidates = {
            'jsonld_published': [],
            'jsonld_modified': [],
            'og_published': [],
            'og_modified': [],
            'byline_published': [],
            'byline_updated': [],
            'http_last_modified': http_last_modified,
            'sitemap_lastmod': sitemap_lastmod
        }

        # 1. Try JSON-LD
        jsonld_pub, jsonld_mod = self._extract_jsonld_dates(html)
        if jsonld_pub:
            candidates['jsonld_published'].append(jsonld_pub)
        if jsonld_mod:
            candidates['jsonld_modified'].append(jsonld_mod)

        # 2. Try OpenGraph / meta tags
        og_pub, og_mod = self._extract_og_dates(soup)
        if og_pub:
            candidates['og_published'].append(og_pub)
        if og_mod:
            candidates['og_modified'].append(og_mod)

        # 3. Try visible bylines
        byline_pub, byline_upd = self._extract_byline_dates(soup)
        candidates['byline_published'].extend(byline_pub)
        candidates['byline_updated'].extend(byline_upd)

        # Decide best published date (prefer earlier, higher-confidence sources)
        published_at, published_source = self._select_best_published(candidates)

        # Decide best updated date (prefer later, higher-confidence sources)
        updated_at, updated_source = self._select_best_updated(candidates)

        return {
            'published_at': published_at,
            'updated_at': updated_at,
            'published_source': published_source,
            'updated_source': updated_source,
            'all_candidates': candidates
        }

    def _extract_jsonld_dates(self, html: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Extract dates from JSON-LD structured data"""
        try:
            data = extruct.extract(html, syntaxes=['json-ld'])
            jsonld_list = data.get('json-ld', [])

            published = None
            modified = None

            for item in jsonld_list:
                if not isinstance(item, dict):
                    continue

                # Look for datePublished
                if 'datePublished' in item:
                    try:
                        published = date_parser.parse(item['datePublished'])
                    except:
                        pass

                # Look for dateModified
                if 'dateModified' in item:
                    try:
                        modified = date_parser.parse(item['dateModified'])
                    except:
                        pass

                # Also check nested properties
                if '@graph' in item:
                    for subitem in item['@graph']:
                        if isinstance(subitem, dict):
                            if 'datePublished' in subitem and not published:
                                try:
                                    published = date_parser.parse(subitem['datePublished'])
                                except:
                                    pass
                            if 'dateModified' in subitem and not modified:
                                try:
                                    modified = date_parser.parse(subitem['dateModified'])
                                except:
                                    pass

            return published, modified
        except Exception:
            return None, None

    def _extract_og_dates(self, soup: BeautifulSoup) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Extract dates from OpenGraph / Twitter / meta tags"""
        published = None
        modified = None

        # Common meta tag names for dates
        pub_names = [
            'article:published_time',
            'og:published_time',
            'datePublished',
            'sailthru.date',
            'article.published',
            'published_date'
        ]

        mod_names = [
            'article:modified_time',
            'og:updated_time',
            'dateModified',
            'article.updated',
            'last_modified'
        ]

        # Search meta tags
        for name in pub_names:
            tag = soup.find('meta', property=name) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                try:
                    published = date_parser.parse(tag['content'])
                    break
                except:
                    pass

        for name in mod_names:
            tag = soup.find('meta', property=name) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                try:
                    modified = date_parser.parse(tag['content'])
                    break
                except:
                    pass

        # Also check <time> tags with itemprop
        if not published:
            time_tag = soup.find('time', itemprop='datePublished')
            if time_tag:
                datetime_attr = time_tag.get('datetime')
                if datetime_attr:
                    try:
                        published = date_parser.parse(datetime_attr)
                    except:
                        pass

        if not modified:
            time_tag = soup.find('time', itemprop='dateModified')
            if time_tag:
                datetime_attr = time_tag.get('datetime')
                if datetime_attr:
                    try:
                        modified = date_parser.parse(datetime_attr)
                    except:
                        pass

        return published, modified

    def _extract_byline_dates(self, soup: BeautifulSoup) -> Tuple[list, list]:
        """Extract dates from visible text patterns"""
        published = []
        updated = []

        # Get visible text
        text = soup.get_text(separator=' ', strip=True)

        # Apply regex patterns
        for pattern in self.BYLINE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1) if match.lastindex >= 1 else match.group(0)
                try:
                    parsed = date_parser.parse(date_str)

                    # Classify as published or updated based on context
                    context = text[max(0, match.start() - 20):match.end() + 20].lower()
                    if 'updated' in context or 'modified' in context:
                        updated.append(parsed)
                    else:
                        published.append(parsed)
                except:
                    pass

        return published, updated

    def _select_best_published(self, candidates: Dict) -> Tuple[Optional[datetime], str]:
        """Select best published date (prefer earlier, higher-confidence)"""
        # Priority order
        if candidates['jsonld_published']:
            return min(candidates['jsonld_published']), 'jsonld'

        if candidates['og_published']:
            return min(candidates['og_published']), 'og'

        if candidates['byline_published']:
            return min(candidates['byline_published']), 'byline'

        # HTTP Last-Modified as weak fallback
        if candidates['http_last_modified']:
            try:
                return date_parser.parse(candidates['http_last_modified']), 'http_last_modified'
            except:
                pass

        # Sitemap lastmod
        if candidates['sitemap_lastmod']:
            try:
                return date_parser.parse(candidates['sitemap_lastmod']), 'sitemap'
            except:
                pass

        return None, 'none'

    def _select_best_updated(self, candidates: Dict) -> Tuple[Optional[datetime], str]:
        """Select best updated date (prefer later, higher-confidence)"""
        # Priority order
        if candidates['jsonld_modified']:
            return max(candidates['jsonld_modified']), 'jsonld'

        if candidates['og_modified']:
            return max(candidates['og_modified']), 'og'

        if candidates['byline_updated']:
            return max(candidates['byline_updated']), 'byline'

        # HTTP Last-Modified
        if candidates['http_last_modified']:
            try:
                return date_parser.parse(candidates['http_last_modified']), 'http_last_modified'
            except:
                pass

        # Sitemap lastmod
        if candidates['sitemap_lastmod']:
            try:
                return date_parser.parse(candidates['sitemap_lastmod']), 'sitemap'
            except:
                pass

        return None, 'none'
