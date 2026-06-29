"""
HTML Cache Service - HTML Content Caching Operations
Handles caching of raw HTML fetches and processed analysis for web pages.
Works with url_raw and url_processed database tables.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Tuple

from .base_cache_service import BaseCacheService, retry_on_db_lock
from .helpers.url_utils import normalize_url
from .helpers.content_utils import compute_content_hash


class HTMLCacheService(BaseCacheService):
    """Service for HTML content caching and analysis reuse decisions"""

    def record_fetch(
        self,
        url_id: int,
        http_status: int,
        final_url: str,
        etag: Optional[str],
        last_modified_header: Optional[str],
        raw_html: str,
        fetch_meta: Dict[str, Any]
    ) -> Tuple[int, str]:
        """
        Record a new fetch of a URL.

        Args:
            url_id: URL being fetched
            http_status: HTTP status code
            final_url: URL after redirects
            etag: ETag header (if any)
            last_modified_header: Last-Modified header (if any)
            raw_html: Full HTML content
            fetch_meta: Additional metadata (headers, redirect chain, timing)

        Returns:
            (raw_id, content_hash): ID for this fetch and content hash
        """
        content_hash = compute_content_hash(raw_html)

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO url_raw
            (url_id, http_status, final_url, etag, last_modified_header, content_hash, raw_html, fetch_meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url_id, http_status, final_url, etag, last_modified_header,
            content_hash, raw_html, json.dumps(fetch_meta)
        ))

        raw_id = cursor.lastrowid
        cursor.close()
        self.conn.commit()
        return raw_id, content_hash

    def record_processed_simple(
        self,
        url_id: int,
        clean_text: str,
        word_count: int,
        sentence_count: int,
        entities: list,
        quality_score: int,
        processing_meta: dict,
        detected_published_date: str = None,
        detected_modified_date: str = None,
        title: str = None,
        final_score: int = None
    ) -> int:
        """
        Simplified record_processed for backward compatibility.
        Accepts old signature and calls new method with default versions.
        """
        # Use default versions (same as get_reuse_decision_simple)
        pipeline_version = "1.0.0"
        model_name = "default"
        model_version = "1.0.0"
        schema_version = "1.0.0"

        # Get latest raw_id for this URL
        raw_id = self._get_latest_raw_id(url_id)
        if not raw_id:
            # If no raw fetch exists, create a placeholder
            raw_id = -1  # Will need to handle this case

        # Convert to new signature format - store ALL processing_meta in quality_scores
        quality_scores = {
            'heuristic_score': processing_meta.get('heuristic_score', quality_score),
            'nlp_score': processing_meta.get('nlp_score', quality_score),
            'final_score': final_score or quality_score,
            'score_breakdown': processing_meta.get('score_breakdown', {}),
            'nlp_analysis': processing_meta.get('nlp_analysis', {}),
            'word_count': word_count,
            'quality_class': processing_meta.get('quality_class', 'unknown')
        }

        analysis_summary = title or ''

        published_at = None
        if detected_published_date:
            try:
                published_at = datetime.fromisoformat(detected_published_date)
            except:
                pass

        updated_at = None
        if detected_modified_date:
            try:
                updated_at = datetime.fromisoformat(detected_modified_date)
            except:
                pass

        # Call the full method
        return self.record_processed(
            url_id=url_id,
            raw_id=raw_id,
            pipeline_version=pipeline_version,
            model_name=model_name,
            model_version=model_version,
            schema_version=schema_version,
            content_text=clean_text,
            analysis_summary=analysis_summary,
            entities={'entities': entities} if entities else {},
            quality_scores=quality_scores,
            published_at=published_at,
            updated_at=updated_at,
            published_source='auto_detected' if published_at else None,
            updated_source='auto_detected' if updated_at else None,
            processing_status='success'
        )

    def _get_latest_raw_id(self, url_id: int) -> Optional[int]:
        """Get the latest raw_id for a URL"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT raw_id FROM url_raw
            WHERE url_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
        """, (url_id,))
        row = cursor.fetchone()
        cursor.close()
        return row['raw_id'] if row else None

    def record_processed(
        self,
        url_id: int,
        raw_id: int,
        pipeline_version: str,
        model_name: str,
        model_version: str,
        schema_version: str,
        content_text: str,
        analysis_summary: str,
        entities: Dict[str, Any],
        quality_scores: Dict[str, Any],
        published_at: Optional[datetime],
        updated_at: Optional[datetime],
        published_source: Optional[str],
        updated_source: Optional[str],
        processing_status: Optional[str] = 'success'
    ) -> int:
        """
        Record processed analysis for a URL.

        Args:
            url_id: URL being analyzed
            raw_id: Fetch this analysis is based on
            pipeline_version: ETL/processing pipeline version
            model_name: Model used (if any)
            model_version: Model version
            schema_version: Output schema version
            content_text: Extracted text content
            analysis_summary: Analysis summary
            entities: Extracted entities (JSON)
            quality_scores: Quality metrics (JSON)
            published_at: Publication date (if detected)
            updated_at: Update date (if detected)
            published_source: Source of publication date
            updated_source: Source of update date
            processing_status: Processing result ('success', 'filtered', 'failed')

        Returns:
            proc_id: Unique ID for this processed result
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO url_processed
                (url_id, raw_id, pipeline_version, model_name, model_version, schema_version,
                 content_text, analysis_summary, entities_json, quality_scores_json,
                 published_at, updated_at, published_source, updated_source, processing_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url_id, raw_id, pipeline_version, model_name, model_version, schema_version,
                content_text, analysis_summary, json.dumps(entities), json.dumps(quality_scores),
                published_at, updated_at, published_source, updated_source, processing_status
            ))

            proc_id = cursor.lastrowid
            cursor.close()
            self.conn.commit()

            # Update urls table with detected dates if newer/better
            self._update_url_dates(url_id, published_at, updated_at)

            return proc_id
        except sqlite3.IntegrityError:
            # Already exists with these exact versions, return existing
            cursor.execute("""
                SELECT proc_id FROM url_processed
                WHERE url_id = ? AND raw_id = ?
                  AND pipeline_version = ? AND model_name = ?
                  AND model_version = ? AND schema_version = ?
            """, (url_id, raw_id, pipeline_version, model_name, model_version, schema_version))
            row = cursor.fetchone()
            proc_id = row['proc_id']
            cursor.close()
            return proc_id

    def record_html_processing_error(self, url_id: int, error_msg: str) -> int:
        """
        Record HTML processing error in cache (for 15-day skip).
        This method properly sets processing_status='error' so check_url_cache_status() can detect it.

        Args:
            url_id: URL ID (from upsert_url)
            error_msg: Error message (e.g., 'HTTP 403', 'Timeout after 10s')

        Returns:
            proc_id: ID of the error record
        """
        # Get or create a placeholder raw_id for errors
        raw_id = None

        try:
            # Try to get the latest raw_id if one exists
            latest_raw = self._get_latest_raw_id(url_id)
            if latest_raw:
                raw_id = latest_raw
        except Exception:
            pass

        # If no raw_id exists, create a placeholder fetch record
        if not raw_id:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO url_raw
                (url_id, http_status, final_url, etag, last_modified_header, content_hash, raw_html, fetch_meta_json)
                VALUES (?, 0, '', NULL, NULL, 'error', '', ?)
            """, (url_id, json.dumps({'error': error_msg})))
            raw_id = cursor.lastrowid
            cursor.close()
            self.conn.commit()

        return self.record_processed(
            url_id=url_id,
            raw_id=raw_id,
            pipeline_version="1.0.0",
            model_name="default",
            model_version="1.0.0",
            schema_version="1.0.0",
            content_text='',
            analysis_summary=error_msg,
            entities={},
            quality_scores={'error': error_msg},
            published_at=None,
            updated_at=None,
            published_source=None,
            updated_source=None,
            processing_status='error'  # KEY: This marks it as an error
        )

    def _update_url_dates(self, url_id: int, published_at: Optional[datetime], updated_at: Optional[datetime]):
        """Update urls.first_published_at_detected / last_updated_at_detected if newer/better"""
        cursor = self.conn.cursor()

        # Get current dates
        cursor.execute("""
            SELECT first_published_at_detected, last_updated_at_detected
            FROM urls WHERE url_id = ?
        """, (url_id,))
        row = cursor.fetchone()

        current_pub = row['first_published_at_detected']
        current_upd = row['last_updated_at_detected']

        # Update if new date is earlier (published) or later (updated)
        updates = []
        params = []

        if published_at and (not current_pub or published_at < datetime.fromisoformat(current_pub)):
            updates.append("first_published_at_detected = ?")
            params.append(published_at)

        if updated_at and (not current_upd or updated_at > datetime.fromisoformat(current_upd)):
            updates.append("last_updated_at_detected = ?")
            params.append(updated_at)

        if updates:
            params.append(url_id)
            cursor.execute(f"""
                UPDATE urls
                SET {', '.join(updates)}
                WHERE url_id = ?
            """, params)
            cursor.close()
            self.conn.commit()
        else:
            cursor.close()

    def check_cached_analysis(self, url_id: int, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Check if this exact content has already been analyzed.

        Args:
            url_id: URL being checked
            content_hash: SHA-256 hash of the content

        Returns:
            Dict with cached analysis data, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                up.proc_id,
                up.content_text,
                up.analysis_summary,
                up.entities_json,
                up.quality_scores_json,
                up.published_at,
                up.updated_at,
                up.processing_status,
                up.created_at,
                ur.fetched_at,
                u.normalized_url
            FROM url_processed up
            INNER JOIN url_raw ur ON up.raw_id = ur.raw_id
            INNER JOIN urls u ON up.url_id = u.url_id
            WHERE up.url_id = ? AND ur.content_hash = ?
            AND up.pipeline_version = ? AND up.schema_version = ?
            ORDER BY up.created_at DESC
            LIMIT 1
        """, (url_id, content_hash, self.PIPELINE_VERSION, self.SCHEMA_VERSION))

        row = cursor.fetchone()
        if row:
            return {
                'proc_id': row['proc_id'],
                'content_text': row['content_text'],
                'title': row['analysis_summary'],
                'entities': json.loads(row['entities_json']) if row['entities_json'] else {},
                'quality_scores': json.loads(row['quality_scores_json']) if row['quality_scores_json'] else {},
                'published_at': row['published_at'],
                'updated_at': row['updated_at'],
                'status': row['processing_status'],
                'fetched_at': row['fetched_at'],
                'url': row['normalized_url'],
                'cached': True
            }
        return None

    def check_url_cache_status(self, url: str, error_ttl_days: int = 15, filtered_ttl_days: int = 15) -> Optional[Dict[str, Any]]:
        """
        Step 1: Check if URL should skip analysis based on recent status.

        Logic:
        - If status='error' and age < 15 days: SKIP (return cached error)
        - If status='filtered' and age < 15 days: SKIP (return cached filtered)
        - If status='success' OR age > 15 days: return None (proceed to freshness check)

        Args:
            url: The URL to check
            error_ttl_days: Days to skip error URLs (default 15)
            filtered_ttl_days: Days to skip filtered URLs (default 15)

        Returns:
            Dict with cached data if should skip, None if should proceed to freshness check
        """
        normalized = normalize_url(url)
        cursor = self.conn.cursor()

        # Get URL ID and latest processed status
        cursor.execute("""
            SELECT
                u.url_id,
                up.processing_status,
                up.created_at,
                up.content_text,
                up.analysis_summary,
                up.entities_json,
                up.quality_scores_json,
                julianday('now') - julianday(up.created_at) as age_days
            FROM urls u
            LEFT JOIN url_processed up ON u.url_id = up.url_id
            WHERE u.normalized_url = ?
            AND up.pipeline_version = ?
            AND up.schema_version = ?
            ORDER BY up.created_at DESC
            LIMIT 1
        """, (normalized, self.PIPELINE_VERSION, self.SCHEMA_VERSION))

        row = cursor.fetchone()
        if not row:
            return None  # No cache - proceed to fetch

        status = row['processing_status']
        age_days = row['age_days'] if row['age_days'] else 999

        # Check error status
        if status == 'error' and age_days < error_ttl_days:
            # Use ASCII encoding for Windows console safety
            try:
                print(f"[CACHE] Skipping {url} - error cached ({age_days:.1f}d < {error_ttl_days}d)")
            except UnicodeEncodeError:
                print(f"[CACHE] Skipping [URL with Unicode chars] - error cached ({age_days:.1f}d < {error_ttl_days}d)")
            return {
                'url': url,
                'status': 'error',
                'error': row['analysis_summary'] or 'Previous error',
                'title': 'Error',
                'content': '',
                'cleaned_text': '',
                'cached': True,
                'cache_reason': f'error_skip_{age_days:.1f}d'
            }

        # Check filtered status
        if status == 'filtered' and age_days < filtered_ttl_days:
            entities = json.loads(row['entities_json']) if row['entities_json'] else {}
            quality = json.loads(row['quality_scores_json']) if row['quality_scores_json'] else {}

            # Use ASCII encoding for Windows console safety
            try:
                print(f"[CACHE] Skipping {url} - filtered cached ({age_days:.1f}d < {filtered_ttl_days}d)")
            except UnicodeEncodeError:
                print(f"[CACHE] Skipping [URL with Unicode chars] - filtered cached ({age_days:.1f}d < {filtered_ttl_days}d)")
            return {
                'url': url,
                'status': 'filtered',
                'error': row['analysis_summary'] or 'Content filtered',
                'title': row['analysis_summary'] or '',
                'content': '',
                'cleaned_text': '',
                'word_count': entities.get('word_count', 0),
                'quality_score': quality.get('quality_score', 0),
                'quality_class': quality.get('quality_class', 'skip'),
                'cached': True,
                'cache_reason': f'filtered_skip_{age_days:.1f}d'
            }

        # Success status OR old error/filtered → proceed to freshness check
        return None

    def check_recent_filtered(self, url: str, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Check if this URL was recently filtered (within max_age_days).

        For filtered items, we use URL-based caching because the filter reason
        is typically permanent for that URL (e.g., newsletter page, aggregation page).

        Args:
            url: The URL to check
            max_age_days: Maximum age in days to consider "recent" (default 30)

        Returns:
            Dict with cached filtered data if found, None otherwise
        """
        normalized = normalize_url(url)
        cursor = self.conn.cursor()

        # Get URL ID
        cursor.execute("SELECT url_id FROM urls WHERE normalized_url = ?", (normalized,))
        row = cursor.fetchone()
        if not row:
            return None

        url_id = row['url_id']

        # Check for recent filtered processing
        cursor.execute("""
            SELECT
                up.proc_id,
                up.content_text,
                up.analysis_summary,
                up.entities_json,
                up.quality_scores_json,
                up.processing_status,
                up.created_at,
                ur.fetched_at
            FROM url_processed up
            INNER JOIN url_raw ur ON up.raw_id = ur.raw_id
            WHERE up.url_id = ?
            AND up.processing_status = 'filtered'
            AND up.pipeline_version = ?
            AND up.schema_version = ?
            AND julianday('now') - julianday(up.created_at) <= ?
            ORDER BY up.created_at DESC
            LIMIT 1
        """, (url_id, self.PIPELINE_VERSION, self.SCHEMA_VERSION, max_age_days))

        row = cursor.fetchone()
        if row:
            entities = json.loads(row['entities_json']) if row['entities_json'] else {}
            quality = json.loads(row['quality_scores_json']) if row['quality_scores_json'] else {}

            return {
                'url': url,
                'status': 'filtered',
                'error': row['analysis_summary'] or 'Content filtered',
                'title': row['analysis_summary'] or '',
                'content': '',
                'cleaned_text': '',
                'word_count': entities.get('word_count', 0),
                'quality_score': quality.get('quality_score', 0),
                'quality_class': quality.get('quality_class', 'skip'),
                'cached': True,
                'cache_age_days': max_age_days
            }
        return None

    def check_recent_error(self, url: str, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Check if this URL recently resulted in an error (within max_age_days).

        This allows us to skip re-fetching URLs that are known to fail.

        Args:
            url: The URL to check
            max_age_days: Maximum age in days to consider "recent" (default 30)

        Returns:
            Dict with cached error data if found, None otherwise
        """
        normalized = normalize_url(url)
        cursor = self.conn.cursor()

        # Get URL ID
        cursor.execute("SELECT url_id FROM urls WHERE normalized_url = ?", (normalized,))
        row = cursor.fetchone()
        if not row:
            return None

        url_id = row['url_id']

        # Check for recent error processing
        cursor.execute("""
            SELECT
                up.proc_id,
                up.content_text,
                up.analysis_summary,
                up.entities_json,
                up.quality_scores_json,
                up.processing_status,
                up.created_at,
                ur.fetched_at
            FROM url_processed up
            INNER JOIN url_raw ur ON up.raw_id = ur.raw_id
            WHERE up.url_id = ?
            AND up.processing_status = 'error'
            AND up.pipeline_version = ?
            AND up.schema_version = ?
            AND julianday('now') - julianday(up.created_at) <= ?
            ORDER BY up.created_at DESC
            LIMIT 1
        """, (url_id, self.PIPELINE_VERSION, self.SCHEMA_VERSION, max_age_days))

        row = cursor.fetchone()
        if row:
            return {
                'url': url,
                'status': 'error',
                'error': row['analysis_summary'] or 'Previous error',
                'title': 'Error',
                'content': '',
                'cleaned_text': '',
                'cached': True,
                'cache_age_days': max_age_days
            }
        return None

    def get_latest_processed(self, url_id: int) -> Optional[int]:
        """
        Get the most recent processed result for a URL.

        Args:
            url_id: URL to query

        Returns:
            proc_id or None if never processed
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT proc_id FROM url_processed
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))

        row = cursor.fetchone()
        return row['proc_id'] if row else None

    def get_processed_by_id(self, proc_id: int) -> Optional[Dict]:
        """
        Get processed result by ID and return as a result dict.

        Returns:
            Result dict compatible with html_service output format
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                p.*,
                u.normalized_url as url
            FROM url_processed p
            JOIN urls u ON p.url_id = u.url_id
            WHERE p.proc_id = ?
        """, (proc_id,))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        # Parse stored JSON data
        quality_scores = json.loads(row['quality_scores_json']) if row.get('quality_scores_json') else {}
        entities_data = json.loads(row['entities_json']) if row.get('entities_json') else {}

        # Extract all data from quality_scores_json
        heuristic_score = quality_scores.get('heuristic_score', 0)
        nlp_score = quality_scores.get('nlp_score', 0)
        final_score = quality_scores.get('final_score', 0)
        score_breakdown = quality_scores.get('score_breakdown', {})
        nlp_analysis = quality_scores.get('nlp_analysis', {})
        stored_quality_class = quality_scores.get('quality_class', None)

        # Get word count (stored or calculate from content_text)
        word_count = quality_scores.get('word_count', 0)
        content_text = row.get('content_text', '')
        if word_count == 0 and content_text:
            word_count = len(content_text.split())

        # Determine quality class (use stored or calculate)
        if stored_quality_class:
            quality_class = stored_quality_class
        elif final_score >= 70:
            quality_class = 'legit'
        elif final_score >= 40:
            quality_class = 'maybe'
        else:
            quality_class = 'skip'

        # Return in html_service format
        return {
            'status': 'success',
            'url': row['url'],
            'title': row.get('analysis_summary', ''),
            'cleaned_text': content_text,
            'word_count': word_count,
            'heuristic_score': heuristic_score,
            'nlp_score': nlp_score,
            'final_score': final_score,
            'quality_class': quality_class,
            'score_breakdown': score_breakdown,
            'nlp_analysis': nlp_analysis,
            'content_type': 'html',
            'cached': True,
            'cache_reason': 'fresh_cached'
        }

    def get_reuse_decision_simple(
        self,
        url: str,
        raw_html: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Simplified reuse decision based on URL and optional HTML content.

        Args:
            url: URL to check
            raw_html: Optional raw HTML (for content hash comparison)

        Returns:
            {
                'action': 'reuse' | 'reprocess' | 'refetch',
                'reason': str,
                'result': dict (if action='reuse')
            }
        """
        # Use default versions
        pipeline_version = "1.0.0"
        model_name = "default"
        model_version = "1.0.0"
        schema_version = "1.0.0"

        # Get or create URL ID
        url_id = self.upsert_url(url)
        print(f"[CACHE-SIMPLE] Called for {url[:60]}... (url_id={url_id}, raw_html={'provided' if raw_html else 'None'})")

        # OPTIMIZATION: If no raw_html provided, check for ANY recent successful cache (URL-based)
        if raw_html is None:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    up.proc_id,
                    up.processing_status,
                    up.created_at,
                    julianday('now') - julianday(up.created_at) as age_days
                FROM url_processed up
                WHERE up.url_id = ?
                  AND up.pipeline_version = ?
                  AND up.schema_version = ?
                  AND up.processing_status = 'success'
                ORDER BY up.created_at DESC
                LIMIT 1
            """, (url_id, pipeline_version, schema_version))

            row = cursor.fetchone()
            cursor.close()

            if row:
                age_days = row['age_days']

                # Use 7-day TTL for all content (most content is news/blog)
                # User can adjust this based on their needs
                ttl_days = 7

                print(f"[CACHE-CHECK] Found cached result: proc_id={row['proc_id']}, age={age_days:.1f}d, ttl={ttl_days}d")

                if age_days < ttl_days:
                    proc_id = row['proc_id']
                    result = self.get_processed_by_id(proc_id)
                    if result:
                        print(f"[CACHE-HIT] Reusing cached result for {url[:60]}... (age={age_days:.1f}d < {ttl_days}d)")
                        return {
                            'action': 'reuse',
                            'reason': f'age={age_days:.1f}d < {ttl_days}d',
                            'result': result
                        }
                else:
                    print(f"[CACHE-STALE] Cache too old (age={age_days:.1f}d >= {ttl_days}d)")
                    return {
                        'action': 'refetch',
                        'reason': f'Cache expired (age={age_days:.1f}d >= {ttl_days}d)'
                    }
            else:
                print(f"[CACHE-MISS] No cache found for url_id={url_id}, pipeline={pipeline_version}, schema={schema_version}")

            # No recent cache - refetch
            return {
                'action': 'refetch',
                'reason': 'No recent cache found'
            }

        # If raw_html IS provided, use content-hash based caching
        current_hash = compute_content_hash(raw_html)

        # Call the full method
        decision = self.get_reuse_decision(
            url_id=url_id,
            pipeline_version=pipeline_version,
            model_name=model_name,
            model_version=model_version,
            schema_version=schema_version,
            current_content_hash=current_hash
        )

        # If action is 'reuse-analysis', fetch the cached result
        if decision['action'] == 'reuse-analysis':
            proc_id = decision.get('proc_id')
            if proc_id:
                # Get the processed result
                result = self.get_processed_by_id(proc_id)
                if result:
                    return {
                        'action': 'reuse',
                        'reason': decision['reason'],
                        'result': result
                    }

        # Otherwise, map to simpler actions
        if decision['action'] == 'reprocess-same-raw':
            return {
                'action': 'reprocess',
                'reason': decision['reason']
            }

        return {
            'action': 'refetch',
            'reason': decision.get('reason', 'No cached content')
        }

    def get_reuse_decision(
        self,
        url_id: int,
        pipeline_version: str,
        model_name: str,
        model_version: str,
        schema_version: str,
        current_content_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decide whether to reuse cached analysis, reprocess, or refetch.

        Decision logic:
        1. If no fetch exists → "refetch"
        2. If content_hash unchanged:
           a. If pipeline/model/schema match → "reuse-analysis"
           b. If versions differ → "reprocess-same-raw"
        3. If content_hash changed → "refetch"

        Args:
            url_id: URL to check
            pipeline_version: Current pipeline version
            model_name: Current model
            model_version: Current model version
            schema_version: Current schema version
            current_content_hash: Hash of current fetch (if already fetched)

        Returns:
            {
                'action': 'reuse-analysis' | 'reprocess-same-raw' | 'refetch',
                'reason': str,
                'proc_id': int (if reuse-analysis),
                'raw_id': int (if reprocess-same-raw)
            }
        """
        cursor = self.conn.cursor()

        # Get latest fetch
        cursor.execute("""
            SELECT raw_id, content_hash, fetched_at
            FROM url_raw
            WHERE url_id = ?
            ORDER BY fetched_at DESC
            LIMIT 1
        """, (url_id,))

        latest_fetch = cursor.fetchone()

        if not latest_fetch:
            return {
                'action': 'refetch',
                'reason': 'No prior fetch exists'
            }

        latest_raw_id = latest_fetch['raw_id']
        latest_hash = latest_fetch['content_hash']

        # If current_content_hash provided, check if content changed
        if current_content_hash and current_content_hash != latest_hash:
            return {
                'action': 'refetch',
                'reason': f'Content hash changed (was {latest_hash[:8]}..., now {current_content_hash[:8]}...)'
            }

        # Content unchanged, check if we have matching processed version
        cursor.execute("""
            SELECT proc_id, created_at
            FROM url_processed
            WHERE raw_id = ?
              AND pipeline_version = ?
              AND model_name = ?
              AND model_version = ?
              AND schema_version = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (latest_raw_id, pipeline_version, model_name, model_version, schema_version))

        matching_processed = cursor.fetchone()

        if matching_processed:
            return {
                'action': 'reuse-analysis',
                'reason': f'Exact match found (proc_id={matching_processed["proc_id"]})',
                'proc_id': matching_processed['proc_id'],
                'raw_id': latest_raw_id
            }

        # Content unchanged but versions differ
        return {
            'action': 'reprocess-same-raw',
            'reason': f'Pipeline/model/schema version mismatch, content unchanged',
            'raw_id': latest_raw_id
        }

    def mark_url_staleness(
        self,
        url_id: int,
        cache_state: str,
        revalidate_after: Optional[datetime] = None
    ):
        """
        Update URL staleness state.

        Args:
            url_id: URL to update
            cache_state: 'fresh' | 'stale' | 'revalidate'
            revalidate_after: When to revalidate (or None to auto-compute)
        """
        if revalidate_after is None:
            # Default policy: 7 days, or 24h for recent news
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT first_published_at_detected FROM urls WHERE url_id = ?
            """, (url_id,))
            row = cursor.fetchone()

            pub_date = row['first_published_at_detected']
            if pub_date and (datetime.utcnow() - datetime.fromisoformat(pub_date)) < timedelta(days=30):
                # Recent news: revalidate in 24h
                revalidate_after = datetime.utcnow() + timedelta(hours=24)
            else:
                # Normal: revalidate in 7 days
                revalidate_after = datetime.utcnow() + timedelta(days=7)

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE urls
            SET cache_state = ?, revalidate_after = ?
            WHERE url_id = ?
        """, (cache_state, revalidate_after, url_id))
        cursor.close()
        self.conn.commit()
