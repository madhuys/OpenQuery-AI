"""
PDF Cache Service - PDF Download and Processing Cache Management
Handles PDF download state, processing state, retry limits, and hybrid download preferences.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from .base_cache_service import BaseCacheService, retry_on_db_lock
from .helpers.url_utils import normalize_url


class PDFCacheService(BaseCacheService):
    """PDF-specific caching operations for downloads and processing"""

    # =========================================================================
    # PDF DOWNLOAD DECISION & LIFECYCLE
    # =========================================================================

    def should_download_pdf(self, url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if a PDF should be downloaded based on cache state.

        Returns:
            (should_download, cached_data)
            - If should_download=False, cached_data contains the processed PDF
            - If should_download=True, cached_data is None
        """
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                pdf_id,
                download_state,
                processing_state,
                freshness_state,
                revalidate_after,
                num_pages,
                num_words,
                text_preview,
                pdf_hash,
                downloaded_at,
                processed_at,
                download_error,
                processing_error,
                download_retry_count,
                processing_retry_count
            FROM pdf_downloads
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))

        row = cursor.fetchone()
        cursor.close()

        # No previous download attempt - must download
        if not row:
            print(f"[PDF CACHE] No cache for {url} - DOWNLOAD REQUIRED")
            return (True, None)

        # Check freshness
        if row['freshness_state'] == 'fresh' and row['processing_state'] == 'processed_success':
            # Check if still fresh
            revalidate_after = row['revalidate_after']
            if revalidate_after:
                revalidate_dt = datetime.fromisoformat(revalidate_after)
                if datetime.utcnow() < revalidate_dt:
                    print(f"[PDF CACHE] Using FRESH cached PDF for {url} - valid until {revalidate_after}")
                    return (False, {
                        'pdf_id': row['pdf_id'],
                        'num_pages': row['num_pages'],
                        'num_words': row['num_words'],
                        'text_preview': row['text_preview'],
                        'pdf_hash': row['pdf_hash'],
                        'cache_reason': f'fresh_pdf_{row["processed_at"]}'
                    })

        # Processing failed - retry with limits
        if row['processing_state'] == 'processing_failed':
            if row['processing_retry_count'] < 2:  # Max 2 retries
                print(f"[PDF CACHE] Processing failed ({row['processing_retry_count']} retries) - RETRY PROCESSING")
                return (True, None)
            else:
                print(f"[PDF CACHE] Processing failed too many times - SKIP")
                return (False, {
                    'pdf_id': row['pdf_id'],
                    'error': row['processing_error'],
                    'cache_reason': 'processing_failed_max_retries'
                })

        # Download failed - retry with limits
        if row['download_state'] == 'download_failed':
            if row['download_retry_count'] < 3:  # Max 3 retries
                print(f"[PDF CACHE] Download failed ({row['download_retry_count']} retries) - RETRY DOWNLOAD")
                return (True, None)
            else:
                print(f"[PDF CACHE] Download failed too many times - SKIP")
                return (False, {
                    'pdf_id': row['pdf_id'],
                    'error': row['download_error'],
                    'cache_reason': 'download_failed_max_retries'
                })

        # Stale or expired - redownload
        if row['freshness_state'] in ['stale', 'expired']:
            print(f"[PDF CACHE] PDF is {row['freshness_state']} - REDOWNLOAD")
            return (True, None)

        # Default: download (unexpected state - log for debugging)
        print(f"[PDF CACHE] No valid cache - DOWNLOAD")
        print(f"[PDF CACHE] DEBUG: download_state={row.get('download_state')}, processing_state={row.get('processing_state')}, freshness_state={row.get('freshness_state')}")
        return (True, None)

    @retry_on_db_lock()
    def record_pdf_download_success(
        self,
        url: str,
        pdf_bytes: bytes,
        pdf_hash: str,
        download_method: str = 'requests',
        filepath: str = None
    ) -> int:
        """
        Record successful PDF download.

        Args:
            url: PDF URL
            pdf_bytes: PDF bytes (for size calculation)
            pdf_hash: SHA-256 hash of PDF
            download_method: 'requests', 'playwright', or 'manual'
            filepath: Path where PDF was saved on disk
        """
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()

        # Check if there's an existing record to update
        cursor.execute("""
            SELECT pdf_id, download_retry_count FROM pdf_downloads
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing record
            cursor.execute("""
                UPDATE pdf_downloads
                SET
                    download_state = 'download_success',
                    downloaded_at = CURRENT_TIMESTAMP,
                    last_fetched = CURRENT_TIMESTAMP,
                    pdf_size_bytes = ?,
                    pdf_hash = ?,
                    download_method = ?,
                    filepath = ?,
                    download_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE pdf_id = ?
            """, (len(pdf_bytes), pdf_hash, download_method, filepath, existing['pdf_id']))
            pdf_id = existing['pdf_id']
        else:
            # Create new record
            cursor.execute("""
                INSERT INTO pdf_downloads (
                    url_id,
                    download_state,
                    downloaded_at,
                    last_fetched,
                    pdf_size_bytes,
                    pdf_hash,
                    download_method,
                    filepath
                ) VALUES (?, 'download_success', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            """, (url_id, len(pdf_bytes), pdf_hash, download_method, filepath))
            pdf_id = cursor.lastrowid

        cursor.close()
        self.conn.commit()
        return pdf_id

    @retry_on_db_lock()
    def record_pdf_download_failure(
        self,
        url: str,
        error: str
    ):
        """Record failed PDF download"""
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()

        # Check if there's an existing record
        cursor.execute("""
            SELECT pdf_id, download_retry_count FROM pdf_downloads
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing record
            cursor.execute("""
                UPDATE pdf_downloads
                SET
                    download_state = 'download_failed',
                    download_attempted_at = CURRENT_TIMESTAMP,
                    download_error = ?,
                    download_retry_count = download_retry_count + 1,
                    last_retry_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE pdf_id = ?
            """, (error, existing['pdf_id']))
        else:
            # Create new record
            cursor.execute("""
                INSERT INTO pdf_downloads (
                    url_id,
                    download_state,
                    download_attempted_at,
                    download_error,
                    download_retry_count
                ) VALUES (?, 'download_failed', CURRENT_TIMESTAMP, ?, 1)
            """, (url_id, error))

        cursor.close()
        self.conn.commit()

    # =========================================================================
    # PDF PROCESSING LIFECYCLE
    # =========================================================================

    @retry_on_db_lock()
    def record_pdf_processing_success(
        self,
        url: str,
        num_pages: int,
        num_words: int,
        text_preview: str,
        freshness_days: int = 30
    ):
        """Record successful PDF processing with freshness period"""
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()

        # Get the latest pdf_id
        cursor.execute("""
            SELECT pdf_id FROM pdf_downloads
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))
        row = cursor.fetchone()

        if not row:
            print(f"[PDF CACHE] Warning: No PDF download record found for {url}")
            return

        pdf_id = row['pdf_id']

        # Calculate freshness
        revalidate_after = datetime.utcnow() + timedelta(days=freshness_days)

        cursor.execute("""
            UPDATE pdf_downloads
            SET
                processing_state = 'processed_success',
                processed_at = CURRENT_TIMESTAMP,
                num_pages = ?,
                num_words = ?,
                text_preview = ?,
                freshness_state = 'fresh',
                revalidate_after = ?,
                processing_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE pdf_id = ?
        """, (num_pages, num_words, text_preview[:1000], revalidate_after, pdf_id))

        cursor.close()
        self.conn.commit()

        print(f"[PDF CACHE] Marked PDF as FRESH (valid for {freshness_days} days until {revalidate_after})")

    @retry_on_db_lock()
    def record_pdf_processing_failure(
        self,
        url: str,
        error: str
    ):
        """Record failed PDF processing"""
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()

        # Get the latest pdf_id
        cursor.execute("""
            SELECT pdf_id, processing_retry_count FROM pdf_downloads
            WHERE url_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))
        row = cursor.fetchone()

        if not row:
            print(f"[PDF CACHE] Warning: No PDF download record found for {url}")
            return

        pdf_id = row['pdf_id']

        cursor.execute("""
            UPDATE pdf_downloads
            SET
                processing_state = 'processing_failed',
                processing_attempted_at = CURRENT_TIMESTAMP,
                processing_error = ?,
                processing_retry_count = processing_retry_count + 1,
                last_retry_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE pdf_id = ?
        """, (error, pdf_id))

        cursor.close()
        self.conn.commit()

    # =========================================================================
    # PDF FLAGS
    # =========================================================================

    @retry_on_db_lock()
    def mark_pdf_extracted(self, url: str, extracted: bool = True):
        """Mark PDF as extracted (text extraction attempted/successful)"""
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE pdf_downloads
            SET extracted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE url_id = ?
        """, (1 if extracted else 0, url_id))

        cursor.close()
        self.conn.commit()

    @retry_on_db_lock()
    def mark_pdf_processed(self, url: str, processed: bool = True):
        """Mark PDF as processed (NLP analysis completed)"""
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE pdf_downloads
            SET processed = ?, updated_at = CURRENT_TIMESTAMP
            WHERE url_id = ?
        """, (1 if processed else 0, url_id))

        cursor.close()
        self.conn.commit()

    # =========================================================================
    # PDF QUERY & RETRIEVAL
    # =========================================================================

    @retry_on_db_lock()
    def get_cached_pdf_filepath(self, url: str) -> Optional[str]:
        """
        Get filepath of successfully downloaded PDF from cache.

        Args:
            url: PDF URL

        Returns:
            Filepath string if PDF is cached and downloaded successfully, None otherwise
        """
        normalized = normalize_url(url)
        url_id = self._ensure_url_record(normalized)

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT filepath
            FROM pdf_downloads
            WHERE url_id = ?
              AND download_state = 'download_success'
              AND filepath IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
        """, (url_id,))

        row = cursor.fetchone()
        cursor.close()

        if row and row['filepath']:
            # Verify file actually exists on disk
            if os.path.exists(row['filepath']):
                return row['filepath']
            else:
                print(f"[PDF CACHE] Cached filepath doesn't exist on disk: {row['filepath']}")

        return None

    @retry_on_db_lock()
    def get_failed_pdfs(self, limit: int = 100) -> List[Dict]:
        """
        Get all PDFs that failed to download.
        Returns list of dicts with url, error, retry_count, etc.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                u.normalized_url as url,
                p.download_state,
                p.download_error,
                p.download_retry_count,
                p.download_attempted_at,
                p.last_retry_at,
                p.pdf_id,
                d.registrable_domain as domain
            FROM pdf_downloads p
            INNER JOIN urls u ON p.url_id = u.url_id
            INNER JOIN domains d ON u.domain_id = d.domain_id
            WHERE p.download_state = 'download_failed'
            ORDER BY p.download_attempted_at DESC
            LIMIT ?
        """, (limit,))

        failed = cursor.fetchall()
        cursor.close()
        return failed

    # =========================================================================
    # MIGRATION
    # =========================================================================

    def _extend_pdf_downloads_table(self):
        """Add hybrid download columns to pdf_downloads table if they don't exist"""
        import sqlite3

        cursor = self.conn.cursor()

        # Check if pdf_downloads table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_downloads'")
        if not cursor.fetchone():
            cursor.close()
            return

        # Get current columns
        cursor.execute("PRAGMA table_info(pdf_downloads)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        # Add new columns if they don't exist
        columns_to_add = [
            ("download_method_used", "TEXT CHECK (download_method_used IN ('requests', 'browser'))"),
            ("download_duration_ms", "INTEGER"),
            ("switched_from_method", "TEXT"),
            ("download_started_at", "TIMESTAMP"),
            ("browser_session_id", "TEXT"),
            # V2 columns for download tracking and processing flags
            ("download_method", "TEXT CHECK (download_method IN ('requests', 'playwright', 'manual', 'curl_cffi'))"),
            ("filepath", "TEXT"),
            ("extracted", "INTEGER DEFAULT 0 CHECK (extracted IN (0, 1))"),
            ("processed", "INTEGER DEFAULT 0 CHECK (processed IN (0, 1))"),
            ("last_fetched", "TIMESTAMP")
        ]

        for column_name, column_def in columns_to_add:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE pdf_downloads ADD COLUMN {column_name} {column_def}")
                    print(f"[CACHE] Added column {column_name} to pdf_downloads table")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        print(f"[CACHE] Warning: Could not add column {column_name}: {e}")

        cursor.close()

    # =========================================================================
    # HYBRID DOWNLOAD METHODS (Domain Preferences)
    # =========================================================================

    @retry_on_db_lock()
    def get_domain_download_preference(self, domain: str) -> Dict[str, Any]:
        """
        Get download method preference for a domain.

        Returns:
            Dict with:
            - preferred_method: 'auto', 'requests', or 'browser'
            - preference_reason: Why this preference was set
            - requests_success_rate: Success rate for requests method
            - browser_success_rate: Success rate for browser method
            - requests_avg_duration_ms: Average duration for requests
            - browser_avg_duration_ms: Average duration for browser
        """
        # Get or create domain_id
        domain_id = self._ensure_domain_record(domain)

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                preferred_method,
                preference_reason,
                requests_attempts,
                requests_successes,
                requests_avg_duration_ms,
                browser_attempts,
                browser_successes,
                browser_avg_duration_ms,
                auto_switched_to_browser_at,
                auto_switch_trigger
            FROM domain_download_preferences
            WHERE domain_id = ?
        """, (domain_id,))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            # No preference set - return defaults
            return {
                'preferred_method': 'auto',
                'preference_reason': 'default',
                'requests_success_rate': 0.0,
                'browser_success_rate': 0.0,
                'requests_avg_duration_ms': 0,
                'browser_avg_duration_ms': 0
            }

        # Calculate success rates
        requests_rate = (
            100.0 * row['requests_successes'] / row['requests_attempts']
            if row['requests_attempts'] > 0 else 0.0
        )
        browser_rate = (
            100.0 * row['browser_successes'] / row['browser_attempts']
            if row['browser_attempts'] > 0 else 0.0
        )

        return {
            'preferred_method': row['preferred_method'],
            'preference_reason': row['preference_reason'],
            'requests_success_rate': requests_rate,
            'browser_success_rate': browser_rate,
            'requests_avg_duration_ms': row['requests_avg_duration_ms'] or 0,
            'browser_avg_duration_ms': row['browser_avg_duration_ms'] or 0,
            'auto_switched_at': row['auto_switched_to_browser_at'],
            'auto_switch_trigger': row['auto_switch_trigger']
        }

    @retry_on_db_lock()
    def mark_domain_for_browser(
        self,
        domain: str,
        reason: str,
        trigger: Optional[str] = None,
        manual: bool = False,
        user: Optional[str] = None
    ):
        """
        Mark a domain to prefer browser-based downloads.

        Args:
            domain: Domain to update
            reason: Why browser is preferred (e.g., 'timeout_8s', 'bot_detection')
            trigger: Auto-switch trigger if applicable
            manual: Whether this is a manual override by user
            user: User identifier if manual override
        """
        domain_id = self._ensure_domain_record(domain)

        cursor = self.conn.cursor()

        # Check if preference exists
        cursor.execute("SELECT pref_id FROM domain_download_preferences WHERE domain_id = ?", (domain_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing preference
            if manual:
                cursor.execute("""
                    UPDATE domain_download_preferences
                    SET
                        preferred_method = 'browser',
                        preference_reason = ?,
                        manually_set_to = 'browser',
                        manually_set_at = CURRENT_TIMESTAMP,
                        manually_set_by = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE domain_id = ?
                """, (reason, user, domain_id))
            else:
                cursor.execute("""
                    UPDATE domain_download_preferences
                    SET
                        preferred_method = 'browser',
                        preference_reason = ?,
                        auto_switched_to_browser_at = CURRENT_TIMESTAMP,
                        auto_switch_trigger = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE domain_id = ?
                """, (reason, trigger, domain_id))
        else:
            # Create new preference
            if manual:
                cursor.execute("""
                    INSERT INTO domain_download_preferences (
                        domain_id, preferred_method, preference_reason,
                        manually_set_to, manually_set_at, manually_set_by
                    ) VALUES (?, 'browser', ?, 'browser', CURRENT_TIMESTAMP, ?)
                """, (domain_id, reason, user))
            else:
                cursor.execute("""
                    INSERT INTO domain_download_preferences (
                        domain_id, preferred_method, preference_reason,
                        auto_switched_to_browser_at, auto_switch_trigger
                    ) VALUES (?, 'browser', ?, CURRENT_TIMESTAMP, ?)
                """, (domain_id, reason, trigger))

        cursor.close()
        self.conn.commit()

        print(f"[CACHE] Marked domain {domain} for BROWSER downloads (reason: {reason})")

    @retry_on_db_lock()
    def record_domain_download(
        self,
        domain: str,
        method: str,
        duration_ms: int,
        success: bool,
        switched_from: Optional[str] = None
    ):
        """
        Record a download attempt for a domain to update statistics.

        Args:
            domain: Domain that was downloaded from
            method: 'requests' or 'browser'
            duration_ms: How long the download took
            success: Whether download succeeded
            switched_from: If method was switched, what was the original method
        """
        domain_id = self._ensure_domain_record(domain)

        cursor = self.conn.cursor()

        # Check if preference exists
        cursor.execute("SELECT pref_id FROM domain_download_preferences WHERE domain_id = ?", (domain_id,))
        existing = cursor.fetchone()

        if existing:
            # Update statistics
            if method == 'requests':
                cursor.execute("""
                    UPDATE domain_download_preferences
                    SET
                        requests_attempts = requests_attempts + 1,
                        requests_successes = requests_successes + ?,
                        requests_total_duration_ms = requests_total_duration_ms + ?,
                        requests_avg_duration_ms = (requests_total_duration_ms + ?) / (requests_attempts + 1),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE domain_id = ?
                """, (1 if success else 0, duration_ms, duration_ms, domain_id))
            else:  # browser
                cursor.execute("""
                    UPDATE domain_download_preferences
                    SET
                        browser_attempts = browser_attempts + 1,
                        browser_successes = browser_successes + ?,
                        browser_total_duration_ms = browser_total_duration_ms + ?,
                        browser_avg_duration_ms = (browser_total_duration_ms + ?) / (browser_attempts + 1),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE domain_id = ?
                """, (1 if success else 0, duration_ms, duration_ms, domain_id))
        else:
            # Create new preference with initial stats
            if method == 'requests':
                cursor.execute("""
                    INSERT INTO domain_download_preferences (
                        domain_id, preferred_method,
                        requests_attempts, requests_successes,
                        requests_total_duration_ms, requests_avg_duration_ms
                    ) VALUES (?, 'auto', 1, ?, ?, ?)
                """, (domain_id, 1 if success else 0, duration_ms, duration_ms))
            else:  # browser
                cursor.execute("""
                    INSERT INTO domain_download_preferences (
                        domain_id, preferred_method,
                        browser_attempts, browser_successes,
                        browser_total_duration_ms, browser_avg_duration_ms
                    ) VALUES (?, 'auto', 1, ?, ?, ?)
                """, (domain_id, 1 if success else 0, duration_ms, duration_ms))

        cursor.close()
        self.conn.commit()

    # =========================================================================
    # APP SETTINGS (Used by PDF service for worker configuration)
    # =========================================================================

    @retry_on_db_lock()
    def get_app_setting(self, key: str, default: Any = None) -> Any:
        """
        Get application setting value.

        Args:
            key: Setting key (e.g., 'pdf_worker_count')
            default: Default value if setting doesn't exist

        Returns:
            Setting value (converted to appropriate type)
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT setting_value, setting_type
            FROM app_settings
            WHERE setting_key = ?
        """, (key,))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return default

        value = row['setting_value']
        setting_type = row['setting_type']

        # Convert to appropriate type
        if setting_type == 'int':
            return int(value)
        elif setting_type == 'float':
            return float(value)
        elif setting_type == 'bool':
            return value.lower() in ('true', '1', 'yes')
        elif setting_type == 'json':
            return json.loads(value)
        else:
            return value

    @retry_on_db_lock()
    def set_app_setting(
        self,
        key: str,
        value: Any,
        setting_type: Optional[str] = None,
        description: Optional[str] = None
    ):
        """
        Set application setting value.

        Args:
            key: Setting key
            value: Setting value
            setting_type: Type hint ('int', 'float', 'bool', 'string', 'json')
            description: Human-readable description
        """
        # Auto-detect type if not provided
        if setting_type is None:
            if isinstance(value, bool):
                setting_type = 'bool'
            elif isinstance(value, int):
                setting_type = 'int'
            elif isinstance(value, float):
                setting_type = 'float'
            elif isinstance(value, (dict, list)):
                setting_type = 'json'
            else:
                setting_type = 'string'

        # Convert value to string for storage
        if setting_type == 'bool':
            value_str = 'true' if value else 'false'
        elif setting_type == 'json':
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO app_settings (
                setting_key, setting_value, setting_type, description, updated_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (key, value_str, setting_type, description))

        cursor.close()
        self.conn.commit()

        print(f"[CACHE] Updated setting {key} = {value} ({setting_type})")

    # =========================================================================
    # PDF FINGERPRINTING FOR DEDUPLICATION
    # =========================================================================

    def check_pdf_fingerprint_exists(self, fingerprint: str) -> bool:
        """
        Check if PDF fingerprint exists in database (for deduplication)

        Args:
            fingerprint: SHA-256 hash of (title + author + date)

        Returns:
            True if fingerprint exists, False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT pdf_fingerprint_id FROM pdf_fingerprints
            WHERE fingerprint = ?
            LIMIT 1
        """, (fingerprint,))

        row = cursor.fetchone()
        cursor.close()

        return row is not None

    @retry_on_db_lock()
    def record_pdf_fingerprint(self, fingerprint: str, doc_id: str, metadata: Dict):
        """
        Record PDF fingerprint for deduplication

        Args:
            fingerprint: SHA-256 hash of (title + author + date)
            doc_id: Document ID from PDFLiteExtractor (sha256:...)
            metadata: Full metadata dict from extraction

        Returns:
            pdf_fingerprint_id
        """
        cursor = self.conn.cursor()

        # Check if already exists
        cursor.execute("""
            SELECT pdf_fingerprint_id FROM pdf_fingerprints
            WHERE fingerprint = ?
            LIMIT 1
        """, (fingerprint,))

        existing = cursor.fetchone()

        if existing:
            print(f"[PDF CACHE] Fingerprint already exists: {fingerprint[:16]}...")
            return existing['pdf_fingerprint_id']

        # Insert new fingerprint
        cursor.execute("""
            INSERT INTO pdf_fingerprints (
                fingerprint,
                doc_id,
                title,
                author,
                creation_date,
                modification_date,
                num_pages,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            fingerprint,
            doc_id,
            metadata.get('title'),
            metadata.get('author'),
            metadata.get('creation_date'),
            metadata.get('modification_date'),
            metadata.get('num_pages')
        ))

        fingerprint_id = cursor.lastrowid
        cursor.close()
        self.conn.commit()

        print(f"[PDF CACHE] Recorded fingerprint: {fingerprint[:16]}... (id={fingerprint_id})")
        return fingerprint_id

    def get_pdf_by_fingerprint(self, fingerprint: str) -> Optional[Dict]:
        """
        Get PDF details by fingerprint

        Args:
            fingerprint: SHA-256 hash of (title + author + date)

        Returns:
            Dict with fingerprint record or None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                pdf_fingerprint_id,
                fingerprint,
                doc_id,
                title,
                author,
                creation_date,
                modification_date,
                num_pages,
                created_at
            FROM pdf_fingerprints
            WHERE fingerprint = ?
            LIMIT 1
        """, (fingerprint,))

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            'pdf_fingerprint_id': row['pdf_fingerprint_id'],
            'fingerprint': row['fingerprint'],
            'doc_id': row['doc_id'],
            'title': row['title'],
            'author': row['author'],
            'creation_date': row['creation_date'],
            'modification_date': row['modification_date'],
            'num_pages': row['num_pages'],
            'created_at': row['created_at']
        }
