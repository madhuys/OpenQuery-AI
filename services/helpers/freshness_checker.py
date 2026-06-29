"""
Freshness Checker - Determines if cached content needs reindexing
Implements the Reindex Decision Policy (v2)
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import requests
from urllib.parse import urlparse
import feedparser
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
from config.settings import AppSettings, SETTINGS_FILE


class FreshnessChecker:
    """Checks if cached content is still fresh using multiple signals"""

    # Default staleness schedules by content type (in days)
    DEFAULT_STALENESS_SCHEDULE = {
        'news': 7,
        'blog': 7,
        'product': 30,
        'docs': 30,
        'documentation': 30,
        'evergreen': 90,
        'unknown': 30,  # Default
    }

    def __init__(self, staleness_schedule: Optional[Dict[str, int]] = None):
        """
        Initialize FreshnessChecker with configurable staleness schedule

        Args:
            staleness_schedule: Custom staleness schedule dict (content_type -> days)
                               If None, uses DEFAULT_STALENESS_SCHEDULE
        """
        self.settings = AppSettings.load(SETTINGS_FILE).analysis  # Load analysis settings

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; FreshnessBot/1.0)'
        })

        # Use provided schedule or fall back to defaults
        self.STALENESS_SCHEDULE = staleness_schedule if staleness_schedule is not None else self.DEFAULT_STALENESS_SCHEDULE.copy()

    def check_freshness(
        self,
        url: str,
        stored_etag: Optional[str] = None,
        stored_last_modified: Optional[str] = None,
        last_fetched_at: Optional[datetime] = None,
        content_type: str = 'unknown',
        content_published_at: Optional[datetime] = None,
        content_updated_at: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if cached content is still fresh.

        Args:
            url: The URL to check
            stored_etag: Previously stored ETag
            stored_last_modified: Previously stored Last-Modified header
            last_fetched_at: When content was last fetched
            content_type: Type of content (news, blog, docs, evergreen, etc.)
            content_published_at: When the CONTENT was published (from metadata)
            content_updated_at: When the CONTENT was last updated (from metadata)

        Returns:
            (is_fresh, reason): Tuple of boolean and reason string
        """

        # Priority 1: HTTP Validators (ETag, Last-Modified)
        if stored_etag or stored_last_modified:
            is_fresh, reason = self._check_http_validators(url, stored_etag, stored_last_modified)
            if is_fresh is not None:
                return is_fresh, reason

        # Priority 2: Compare last index date vs content update date
        # If content was updated MORE RECENTLY than when we last indexed it → STALE
        # If last_index_date > content_update_date → FRESH (no updates since we indexed)
        if content_updated_at and last_fetched_at:
            # Remove timezone info for comparison if present
            content_updated_naive = content_updated_at.replace(tzinfo=None) if content_updated_at.tzinfo else content_updated_at
            last_fetched_naive = last_fetched_at.replace(tzinfo=None) if last_fetched_at.tzinfo else last_fetched_at

            if content_updated_naive > last_fetched_naive:
                # Content was updated AFTER we last indexed it → STALE
                days_behind = (content_updated_naive - last_fetched_naive).days
                hours_behind = (content_updated_naive - last_fetched_naive).seconds // 3600
                if days_behind > 0:
                    return False, f"Content updated {days_behind}d after last index - STALE"
                else:
                    return False, f"Content updated {hours_behind}h after last index - STALE"
            else:
                # No content updates since we last indexed → FRESH
                days_ahead = (last_fetched_naive - content_updated_naive).days
                return True, f"No updates since last index ({days_ahead}d) - FRESH"

        # Priority 3: Time-based fallback (if no content update date available)
        # Check if our INDEX is stale based on time threshold
        if last_fetched_at:
            staleness_days = self.STALENESS_SCHEDULE.get(content_type, self.STALENESS_SCHEDULE['unknown'])
            cache_age = datetime.now() - last_fetched_at

            if cache_age.days < staleness_days:
                return True, f"Index fresh (last crawled {cache_age.days}d ago < {staleness_days}d threshold)"
            else:
                return False, f"Index stale (last crawled {cache_age.days}d ago >= {staleness_days}d threshold)"

        # Priority 4: Content age fallback (if no fetch date)
        content_date = content_updated_at or content_published_at
        if content_date:
            staleness_days = self.STALENESS_SCHEDULE.get(content_type, self.STALENESS_SCHEDULE['unknown'])
            content_age_days = (datetime.now() - content_date).days

            if content_age_days < staleness_days:
                return True, f"Content fresh (published/updated {content_age_days}d ago < {staleness_days}d threshold)"
            else:
                return False, f"Content stale (published/updated {content_age_days}d ago >= {staleness_days}d threshold)"

        # No freshness info available - assume stale
        return False, "No freshness information available"

    def _check_http_validators(
        self,
        url: str,
        stored_etag: Optional[str],
        stored_last_modified: Optional[str]
    ) -> Tuple[Optional[bool], str]:
        """
        Check HTTP validators (ETag, Last-Modified) via conditional request.

        Returns:
            (is_fresh, reason) or (None, reason) if check couldn't be performed
        """
        headers = {}

        if stored_etag:
            headers['If-None-Match'] = stored_etag

        if stored_last_modified:
            headers['If-Modified-Since'] = stored_last_modified

        if not headers:
            return None, "No HTTP validators available"

        try:
            # Send HEAD request with conditional headers
            response = self.session.head(url, headers=headers, timeout=self.settings.api_health_timeout, allow_redirects=True)

            if response.status_code == 304:
                return True, "HTTP 304 Not Modified - content unchanged"

            elif response.status_code == 200:
                # Check if ETag or Last-Modified changed
                new_etag = response.headers.get('ETag')
                new_last_modified = response.headers.get('Last-Modified')

                if stored_etag and new_etag and stored_etag != new_etag:
                    return False, f"ETag changed: {stored_etag[:16]}... → {new_etag[:16]}..."

                if stored_last_modified and new_last_modified and stored_last_modified != new_last_modified:
                    return False, f"Last-Modified changed: {stored_last_modified} → {new_last_modified}"

                # Headers present but unchanged
                return True, "HTTP validators unchanged"

            else:
                # Unexpected status code - can't determine freshness
                return None, f"HTTP {response.status_code} - can't determine freshness"

        except Exception as e:
            # Network error - can't determine freshness
            return None, f"HTTP check failed: {str(e)}"

    def extract_feed_updated_date(self, feed_url: str, target_url: str) -> Optional[datetime]:
        """
        Check RSS/Atom feed for entry with target URL and get its updated date.

        Args:
            feed_url: URL of the RSS/Atom feed
            target_url: The article URL we're looking for

        Returns:
            datetime of the entry's updated/published date, or None
        """
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                # Check if this entry's link matches our target URL
                entry_link = entry.get('link', '')
                if entry_link == target_url or entry_link.rstrip('/') == target_url.rstrip('/'):
                    # Get updated or published date
                    updated = entry.get('updated_parsed') or entry.get('published_parsed')
                    if updated:
                        return datetime(*updated[:6])

            return None
        except Exception:
            return None

    def extract_sitemap_lastmod(self, sitemap_url: str, target_url: str) -> Optional[datetime]:
        """
        Check sitemap.xml for target URL and get its <lastmod> date.

        Args:
            sitemap_url: URL of the sitemap
            target_url: The page URL we're looking for

        Returns:
            datetime of the lastmod date, or None
        """
        try:
            response = self.session.get(sitemap_url, timeout=self.settings.api_health_timeout)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Handle namespace
            ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            for url_elem in root.findall('.//ns:url', ns):
                loc = url_elem.find('ns:loc', ns)
                lastmod = url_elem.find('ns:lastmod', ns)

                if loc is not None and loc.text:
                    if loc.text == target_url or loc.text.rstrip('/') == target_url.rstrip('/'):
                        if lastmod is not None and lastmod.text:
                            # Parse ISO 8601 date
                            return datetime.fromisoformat(lastmod.text.replace('Z', '+00:00'))

            return None
        except Exception:
            return None

    def extract_jsonld_date_modified(self, html_content: str) -> Optional[datetime]:
        """
        Extract dateModified from JSON-LD structured data in HTML.

        Args:
            html_content: Raw HTML content

        Returns:
            datetime of dateModified, or None
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find all JSON-LD script tags
            scripts = soup.find_all('script', type='application/ld+json')

            for script in scripts:
                import json
                try:
                    data = json.loads(script.string)

                    # Handle both single object and array
                    if isinstance(data, list):
                        items = data
                    else:
                        items = [data]

                    for item in items:
                        # Look for dateModified
                        if 'dateModified' in item:
                            date_str = item['dateModified']
                            # Parse ISO 8601
                            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

                        # Also check nested objects
                        if '@graph' in item:
                            for graph_item in item['@graph']:
                                if 'dateModified' in graph_item:
                                    date_str = graph_item['dateModified']
                                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

                except (json.JSONDecodeError, ValueError):
                    continue

            return None
        except Exception:
            return None
