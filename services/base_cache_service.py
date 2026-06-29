"""
Base Cache Service - Shared Core Functionality
Provides database connection, URL normalization, domain management, and search query caching.
"""

import sqlite3
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from functools import wraps

# Import helper utilities
from .helpers.url_utils import normalize_url, extract_domain, DEFAULT_TRACKING_PARAMS
from .helpers.content_utils import compute_content_hash
from .helpers.query_normalizer import normalize_query, find_best_cache_match
from config.settings import AppSettings, SETTINGS_FILE


def retry_on_db_lock(max_retries=3, delay=0.1):
    """Decorator to retry database operations on lock errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
                        continue
                    raise
            return func(*args, **kwargs)  # Final attempt
        return wrapper
    return decorator


class BaseCacheService:
    """Base service for database connection, URL normalization, and shared cache operations"""

    PIPELINE_VERSION = "1.0.0"  # Bump when extraction logic changes
    SCHEMA_VERSION = "1.0.0"     # Bump when data structure changes

    def __init__(self, db_path: str = "db/serper_cache.db", shared_conn=None):
        """
        Initialize cache service with SQLite database

        Args:
            db_path: Path to SQLite database
            shared_conn: Optional existing connection to share (avoids creating multiple connections)
        """
        self.db_path = db_path
        self.conn = None
        app_settings = AppSettings.load(SETTINGS_FILE)
        self.settings = app_settings.analysis  # Load analysis settings
        self.cache_settings = app_settings.cache  # Load cache settings (for fuzzy matching)

        if shared_conn:
            # Use shared connection (for specialized services in facade pattern)
            self.conn = shared_conn
        else:
            # Create new connection
            self._init_database()

    def _init_database(self):
        """Initialize database schema if not exists"""
        # Get path relative to this file's directory
        base_dir = Path(__file__).parent.parent  # Go up to project root
        schema_path = base_dir / "db" / "cache_schema.sql"
        pdf_schema_path = base_dir / "db" / "cache_schema_pdf.sql"
        hybrid_schema_path = base_dir / "db" / "cache_schema_hybrid.sql"

        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0  # Wait up to 30 seconds for locks
        )

        # Use custom row_factory that returns dict
        def dict_factory(cursor, row):
            fields = [column[0] for column in cursor.description]
            return {key: value for key, value in zip(fields, row)}
        self.conn.row_factory = dict_factory

        # Enable WAL mode for better concurrent access
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                print(f"[CACHE] Warning: Could not enable WAL mode (database locked). Will retry on next startup.")
            else:
                raise

        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Set busy timeout (milliseconds)
        self.conn.execute(f"PRAGMA busy_timeout = {self.settings.database_busy_timeout * 1000}")

        # Check if database is already initialized
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='domains'"
        )
        is_initialized = cursor.fetchone() is not None
        cursor.close()

        # Run main schema if database not initialized
        if not is_initialized and schema_path.exists():
            with open(schema_path, 'r') as f:
                self.conn.executescript(f.read())
        elif is_initialized and schema_path.exists():
            # Database exists, but we still need to ensure views are created
            # (they might be missing if schema was run before views were added)
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
                # Extract and run only CREATE VIEW statements
                for statement in schema_sql.split(';'):
                    if 'CREATE VIEW' in statement:
                        try:
                            self.conn.execute(statement + ';')
                        except sqlite3.OperationalError:
                            # View might already exist, continue
                            pass

        # Always run PDF and hybrid schemas (they use IF NOT EXISTS)
        if pdf_schema_path.exists():
            with open(pdf_schema_path, 'r') as f:
                self.conn.executescript(f.read())

        if hybrid_schema_path.exists():
            with open(hybrid_schema_path, 'r') as f:
                self.conn.executescript(f.read())

        # Run PDF fingerprints migration
        fingerprints_migration_path = base_dir / "db" / "migration_pdf_fingerprints.sql"
        if fingerprints_migration_path.exists():
            with open(fingerprints_migration_path, 'r') as f:
                self.conn.executescript(f.read())

        self.conn.commit()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    # =========================================================================
    # DOMAIN & URL MANAGEMENT
    # =========================================================================

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def upsert_domain(self, registrable_domain: str) -> int:
        """Insert or get existing domain ID"""
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO domains (registrable_domain)
                VALUES (?)
            """, (registrable_domain,))
            domain_id = cursor.lastrowid
            cursor.close()
            self.conn.commit()
            return domain_id
        except sqlite3.IntegrityError:
            # Already exists, fetch it
            cursor.execute("""
                SELECT domain_id FROM domains WHERE registrable_domain = ?
            """, (registrable_domain,))
            row = cursor.fetchone()
            cursor.close()
            return row['domain_id']

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def upsert_url(self, raw_url: str) -> int:
        """Insert or update URL, applying normalization"""
        normalized = normalize_url(raw_url)
        domain = extract_domain(normalized)
        domain_id = self.upsert_domain(domain)

        cursor = self.conn.cursor()
        now = datetime.utcnow()

        try:
            cursor.execute("""
                INSERT INTO urls (normalized_url, domain_id, first_seen_at, last_seen_at, revalidate_after)
                VALUES (?, ?, ?, ?, ?)
            """, (normalized, domain_id, now, now, now + timedelta(days=7)))
            url_id = cursor.lastrowid
            cursor.close()
            self.conn.commit()
            return url_id
        except sqlite3.IntegrityError:
            # Already exists, update last_seen_at
            cursor.execute("""
                UPDATE urls
                SET last_seen_at = ?
                WHERE normalized_url = ?
            """, (now, normalized))
            cursor.execute("""
                SELECT url_id FROM urls WHERE normalized_url = ?
            """, (normalized,))
            row = cursor.fetchone()
            url_id = row['url_id']
            cursor.close()
            self.conn.commit()
            return url_id

    def _ensure_url_record(self, normalized_url: str) -> int:
        """Ensure URL record exists and return url_id"""
        return self.upsert_url(normalized_url)

    def _ensure_domain_record(self, domain: str) -> int:
        """Ensure domain record exists and return domain_id"""
        return self.upsert_domain(domain)

    # =========================================================================
    # SEARCH QUERY CACHING
    # =========================================================================

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def get_cached_search(
        self,
        query_text: str,
        settings: Dict[str, Any],
        max_age_hours: int = 24,
        fuzzy_match_threshold: Optional[int] = None,
        enable_fuzzy_matching: Optional[bool] = None
    ) -> Optional[Dict]:
        """
        Check if this exact or similar search exists in cache

        Args:
            query_text: Search query (will be normalized)
            settings: Search settings (search_type, gl, hl, num, etc.)
            max_age_hours: Maximum age in hours to consider cache valid (default 24)
            fuzzy_match_threshold: Minimum similarity score for near-duplicate matching (0-100)
                                   If None, uses value from cache_settings
            enable_fuzzy_matching: Enable/disable fuzzy matching
                                   If None, uses value from cache_settings

        Returns:
            Dict with 'query_id', 'results' (URLs), 'match_type' ('exact' or 'fuzzy'),
            'matched_query', 'similarity_score', and optionally 'analysis_results' if available
        """
        cursor = self.conn.cursor()

        # Use settings from config if not provided
        if fuzzy_match_threshold is None:
            fuzzy_match_threshold = self.cache_settings.fuzzy_match_threshold

        if enable_fuzzy_matching is None:
            enable_fuzzy_matching = self.cache_settings.enable_fuzzy_cache_matching

        # Step 1: Normalize the query
        normalized_query = normalize_query(query_text)

        # Normalize settings JSON (sorted keys for consistent matching)
        settings_json = json.dumps(settings, sort_keys=True)

        # Step 2: Try exact match on normalized query first
        cursor.execute("""
            SELECT
                query_id,
                query_text,
                created_at,
                analysis_results_json,
                analysis_completed_at
            FROM searches
            WHERE query_text = ?
            AND settings_json = ?
            AND (julianday('now') - julianday(created_at)) * 24 <= ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (normalized_query, settings_json, max_age_hours))

        row = cursor.fetchone()
        match_type = None
        similarity_score = None
        matched_query = None

        if row:
            # Exact match found
            match_type = 'exact'
            similarity_score = 100
            matched_query = row['query_text']
        elif enable_fuzzy_matching:
            # Step 3: No exact match - try near-duplicate matching (if enabled)
            # Get all cached queries with same settings within max_age
            cursor.execute("""
                SELECT DISTINCT query_text
                FROM searches
                WHERE settings_json = ?
                AND (julianday('now') - julianday(created_at)) * 24 <= ?
            """, (settings_json, max_age_hours))

            cached_queries = [r['query_text'] for r in cursor.fetchall()]

            if cached_queries:
                # Find best matching query using RapidFuzz
                best_match = find_best_cache_match(
                    normalized_query,
                    cached_queries,
                    threshold=fuzzy_match_threshold
                )

                if best_match:
                    matched_query_text, similarity_score = best_match
                    match_type = 'fuzzy'
                    matched_query = matched_query_text

                    # Fetch the cached search for this fuzzy match
                    cursor.execute("""
                        SELECT
                            query_id,
                            query_text,
                            created_at,
                            analysis_results_json,
                            analysis_completed_at
                        FROM searches
                        WHERE query_text = ?
                        AND settings_json = ?
                        AND (julianday('now') - julianday(created_at)) * 24 <= ?
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (matched_query_text, settings_json, max_age_hours))

                    row = cursor.fetchone()

        # No match found (exact or fuzzy)
        if not row:
            cursor.close()
            return None

        query_id = row['query_id']

        # Get URL results for this search
        cursor.execute("""
            SELECT
                u.normalized_url as url,
                qr.title_at_fetch as title,
                qr.snippet_at_fetch as snippet,
                qr.serp_position as position
            FROM query_results qr
            JOIN urls u ON qr.url_id = u.url_id
            WHERE qr.query_id = ?
            ORDER BY qr.serp_position
        """, (query_id,))

        results = cursor.fetchall()
        cursor.close()

        cache_data = {
            'query_id': query_id,
            'results': results,
            'cached_at': row['created_at'],
            'match_type': match_type,  # 'exact' or 'fuzzy'
            'matched_query': matched_query,  # The actual cached query that matched
            'original_query': query_text,  # User's original query (before normalization)
            'normalized_query': normalized_query,  # Normalized version
            'similarity_score': similarity_score  # 100 for exact, 85-99 for fuzzy
        }

        # If we have complete analysis results, include them
        if row.get('analysis_results_json'):
            try:
                cache_data['analysis_results'] = json.loads(row['analysis_results_json'])
                cache_data['analysis_completed_at'] = row['analysis_completed_at']
            except:
                pass  # Ignore JSON parse errors

        return cache_data

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def start_search(self, query_text: str, settings: Dict[str, Any]) -> int:
        """
        Record a new search query (normalized before storage)

        Args:
            query_text: Raw query text (will be normalized)
            settings: Search settings dict

        Returns:
            query_id for the new search
        """
        cursor = self.conn.cursor()

        # Normalize query before storing
        normalized_query = normalize_query(query_text)

        # Use sorted JSON for consistent matching with get_cached_search
        cursor.execute("""
            INSERT INTO searches (query_text, settings_json)
            VALUES (?, ?)
        """, (normalized_query, json.dumps(settings, sort_keys=True)))

        query_id = cursor.lastrowid
        cursor.close()
        self.conn.commit()
        return query_id

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def record_result(self, query_id: int, raw_url: str, engine: str = "serper",
                     serp_position: Optional[int] = None, title: Optional[str] = None,
                     snippet: Optional[str] = None) -> int:
        """Record a single search result"""
        url_id = self.upsert_url(raw_url)

        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO query_results (query_id, url_id, engine, serp_position, title_at_fetch, snippet_at_fetch)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (query_id, url_id, engine, serp_position, title, snippet))
            result_id = cursor.lastrowid
            cursor.close()
            self.conn.commit()
            return result_id
        except sqlite3.IntegrityError:
            # Duplicate (query_id, url_id) - update instead
            cursor.execute("""
                UPDATE query_results
                SET serp_position = ?, title_at_fetch = ?, snippet_at_fetch = ?
                WHERE query_id = ? AND url_id = ?
            """, (serp_position, title, snippet, query_id, url_id))
            cursor.close()
            self.conn.commit()
            return None

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def save_analysis_results(self, query_id: int, analysis_results: List[Dict[str, Any]]):
        """
        Save complete analysis results for a query

        Args:
            query_id: Query ID to update
            analysis_results: Complete list of analyzed results
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE searches
            SET analysis_results_json = ?,
                analysis_completed_at = CURRENT_TIMESTAMP
            WHERE query_id = ?
        """, (json.dumps(analysis_results), query_id))
        cursor.close()
        self.conn.commit()

    @retry_on_db_lock(max_retries=5, delay=0.2)
    def record_results_batch(self, query_id: int, results: List[Dict[str, Any]], engine: str = "serper"):
        """Record multiple search results efficiently (batch operation)"""
        # First, upsert all URLs and get their IDs
        url_map = {}  # normalized_url -> url_id
        for result in results:
            raw_url = result.get('url', result.get('link', ''))
            if not raw_url:
                continue
            normalized = normalize_url(raw_url)
            if normalized not in url_map:
                url_map[normalized] = self.upsert_url(raw_url)

        # Batch insert query results
        cursor = self.conn.cursor()
        for result in results:
            raw_url = result.get('url', result.get('link', ''))
            if not raw_url:
                continue

            normalized = normalize_url(raw_url)
            url_id = url_map.get(normalized)
            if not url_id:
                continue

            position = result.get('position')
            title = result.get('title')
            snippet = result.get('snippet')

            try:
                cursor.execute("""
                    INSERT INTO query_results (query_id, url_id, engine, serp_position, title_at_fetch, snippet_at_fetch)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (query_id, url_id, engine, position, title, snippet))
            except sqlite3.IntegrityError:
                # Duplicate - update instead
                cursor.execute("""
                    UPDATE query_results
                    SET serp_position = ?, title_at_fetch = ?, snippet_at_fetch = ?
                    WHERE query_id = ? AND url_id = ?
                """, (position, title, snippet, query_id, url_id))

        cursor.close()
        self.conn.commit()

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def get_search_history(self, limit: int = 50) -> List[Dict]:
        """Get recent searches"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM v_recent_searches
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        results = cursor.fetchall()
        cursor.close()
        return results

    def get_url_info(self, url: str) -> Optional[Dict]:
        """Get URL details"""
        normalized = normalize_url(url)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM urls WHERE normalized_url = ?
        """, (normalized,))
        result = cursor.fetchone()
        cursor.close()
        return result

    def purge_url(self, url: str):
        """Delete URL and all related data (CASCADE)"""
        normalized = normalize_url(url)
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM urls WHERE normalized_url = ?
        """, (normalized,))
        cursor.close()
        self.conn.commit()

    def purge_search(self, query_id: int):
        """Delete search and all related data (CASCADE)"""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM searches WHERE query_id = ?
        """, (query_id,))
        cursor.close()
        self.conn.commit()

    def get_database_stats(self) -> Dict[str, int]:
        """Get table row counts"""
        cursor = self.conn.cursor()
        stats = {}

        tables = ['domains', 'urls', 'searches', 'query_results', 'url_raw', 'url_processed']
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            row = cursor.fetchone()
            stats[table] = row['count'] if row else 0

        cursor.close()
        return stats
