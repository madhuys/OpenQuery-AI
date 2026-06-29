"""
Cache Service - Unified Facade
Delegates to specialized cache services while maintaining backward compatibility.
"""

from typing import Optional
from .html_cache_service import HTMLCacheService
from .pdf_cache_service import PDFCacheService


class CacheService:
    """
    Unified cache service facade that delegates to specialized services.
    Maintains backward compatibility with existing code.
    """

    def __init__(self, db_path: str = "db/serper_cache.db"):
        """
        Initialize unified cache service.

        Uses composition to delegate to:
        - HTMLCacheService for HTML-specific operations
        - PDFCacheService for PDF-specific operations

        Both services share the same database connection via inheritance from BaseCacheService.
        """
        self.db_path = db_path

        # Create base instance to establish single connection
        from .base_cache_service import BaseCacheService
        base = BaseCacheService(db_path)
        self.conn = base.conn

        # Initialize specialized services with shared connection
        self.html_cache = HTMLCacheService(db_path, shared_conn=self.conn)
        self.pdf_cache = PDFCacheService(db_path, shared_conn=self.conn)

    # =========================================================================
    # CORE/SHARED METHODS - Delegate to html_cache (could be either)
    # =========================================================================

    def close(self):
        """Close shared database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            # Set to None for specialized services too (they share the same connection)
            self.html_cache.conn = None
            self.pdf_cache.conn = None

    def get_search_history(self, limit: int = 50):
        """Get recent searches"""
        return self.html_cache.get_search_history(limit)

    def get_url_info(self, url: str):
        """Get URL details"""
        return self.html_cache.get_url_info(url)

    def purge_url(self, url: str):
        """Delete URL and all related data"""
        return self.html_cache.purge_url(url)

    def purge_search(self, query_id: int):
        """Delete search and all related data"""
        return self.html_cache.purge_search(query_id)

    def get_database_stats(self):
        """Get table row counts"""
        return self.html_cache.get_database_stats()

    # =========================================================================
    # SEARCH QUERY CACHING - Delegate to html_cache
    # =========================================================================

    def get_cached_search(
        self,
        query_text: str,
        settings: dict,
        max_age_hours: int = 24,
        fuzzy_match_threshold: Optional[int] = None,
        enable_fuzzy_matching: Optional[bool] = None
    ):
        """Check if search exists in cache with optional fuzzy matching"""
        return self.html_cache.get_cached_search(
            query_text,
            settings,
            max_age_hours,
            fuzzy_match_threshold=fuzzy_match_threshold,
            enable_fuzzy_matching=enable_fuzzy_matching
        )

    def start_search(self, query_text: str, settings: dict):
        """Record a new search query"""
        return self.html_cache.start_search(query_text, settings)

    def save_analysis_results(self, query_id: int, analysis_results: list):
        """Save complete analysis results for a query"""
        return self.html_cache.save_analysis_results(query_id, analysis_results)

    def record_result(self, query_id: int, raw_url: str, engine: str = "serper",
                     serp_position: int = None, title: str = None, snippet: str = None):
        """Record a single search result"""
        return self.html_cache.record_result(query_id, raw_url, engine, serp_position, title, snippet)

    def record_results_batch(self, query_id: int, results: list, engine: str = "serper"):
        """Record multiple search results efficiently"""
        return self.html_cache.record_results_batch(query_id, results, engine)

    # =========================================================================
    # HTML-SPECIFIC METHODS - Delegate to html_cache
    # =========================================================================

    def upsert_url(self, url: str) -> int:
        """Get or create URL ID"""
        return self.html_cache.upsert_url(url)

    def record_fetch(self, url_id: int, http_status: int, final_url: str,
                    etag: str, last_modified_header: str, raw_html: str, fetch_meta: dict):
        """Record HTML fetch"""
        return self.html_cache.record_fetch(url_id, http_status, final_url,
                                           etag, last_modified_header, raw_html, fetch_meta)

    def record_processed(self, url_id: int, clean_text: str, word_count: int,
                        sentence_count: int, entities: list, quality_score: int,
                        processing_meta: dict, detected_published_date: str = None,
                        detected_modified_date: str = None, title: str = None,
                        final_score: int = None):
        """Record HTML processing results"""
        return self.html_cache.record_processed_simple(url_id, clean_text, word_count, sentence_count,
                                               entities, quality_score, processing_meta,
                                               detected_published_date, detected_modified_date,
                                               title, final_score)

    def check_cached_analysis(self, url: str, raw_html: str):
        """Check if HTML content already analyzed"""
        return self.html_cache.check_cached_analysis(url, raw_html)

    def check_url_cache_status(self, url: str, error_ttl_days: int = 15, filtered_ttl_days: int = 30):
        """Check if URL should be skipped based on cache"""
        return self.html_cache.check_url_cache_status(url, error_ttl_days, filtered_ttl_days)

    def check_recent_filtered(self, url: str, days: int = 30):
        """Check if URL was recently filtered"""
        return self.html_cache.check_recent_filtered(url, days)

    def check_recent_error(self, url: str, days: int = 30):
        """Check if URL had recent error"""
        return self.html_cache.check_recent_error(url, days)

    def get_latest_processed(self, url: str):
        """Get most recent processed result"""
        return self.html_cache.get_latest_processed(url)

    def record_html_processing_error(self, url_id: int, error_msg: str) -> int:
        """Record HTML processing error"""
        return self.html_cache.record_html_processing_error(url_id, error_msg)

    def get_reuse_decision(self, url: str, raw_html: str = None):
        """Decide whether to reuse, reprocess, or refetch"""
        return self.html_cache.get_reuse_decision_simple(url, raw_html)

    def mark_url_staleness(self, url: str, freshness_state: str, revalidate_days: int = None):
        """Mark URL staleness state"""
        return self.html_cache.mark_url_staleness(url, freshness_state, revalidate_days)

    # =========================================================================
    # PDF-SPECIFIC METHODS - Delegate to pdf_cache
    # =========================================================================

    def should_download_pdf(self, url: str):
        """Check if PDF should be downloaded"""
        return self.pdf_cache.should_download_pdf(url)

    def record_pdf_download_success(self, url: str, pdf_bytes: bytes, pdf_hash: str,
                                   download_method: str = 'requests', filepath: str = None):
        """Record successful PDF download"""
        return self.pdf_cache.record_pdf_download_success(url, pdf_bytes, pdf_hash,
                                                         download_method, filepath)

    def record_pdf_download_failure(self, url: str, error: str):
        """Record failed PDF download"""
        return self.pdf_cache.record_pdf_download_failure(url, error)

    def record_pdf_processing_success(self, url: str, num_pages: int, num_words: int,
                                     text_preview: str, freshness_days: int = 30):
        """Record successful PDF processing"""
        return self.pdf_cache.record_pdf_processing_success(url, num_pages, num_words,
                                                          text_preview, freshness_days)

    def record_pdf_processing_failure(self, url: str, error: str):
        """Record failed PDF processing"""
        return self.pdf_cache.record_pdf_processing_failure(url, error)

    def mark_pdf_extracted(self, url: str, extracted: bool = True):
        """Mark PDF as extracted"""
        return self.pdf_cache.mark_pdf_extracted(url, extracted)

    def mark_pdf_processed(self, url: str, processed: bool = True):
        """Mark PDF as processed"""
        return self.pdf_cache.mark_pdf_processed(url, processed)

    def get_cached_pdf_filepath(self, url: str):
        """Get cached PDF filepath"""
        return self.pdf_cache.get_cached_pdf_filepath(url)

    def get_failed_pdfs(self, limit: int = 100):
        """Get failed PDF downloads"""
        return self.pdf_cache.get_failed_pdfs(limit)

    # =========================================================================
    # HYBRID DOWNLOAD METHODS - Delegate to pdf_cache
    # =========================================================================

    def get_domain_download_preference(self, domain: str):
        """Get domain download preference"""
        return self.pdf_cache.get_domain_download_preference(domain)

    def mark_domain_for_browser(self, domain: str, reason: str, trigger: str = None,
                               manual: bool = False, user: str = None):
        """Mark domain for browser downloads"""
        return self.pdf_cache.mark_domain_for_browser(domain, reason, trigger, manual, user)

    def record_domain_download(self, domain: str, method: str, duration_ms: int,
                              success: bool, switched_from: str = None):
        """Record domain download statistics"""
        return self.pdf_cache.record_domain_download(domain, method, duration_ms,
                                                    success, switched_from)

    # =========================================================================
    # APP SETTINGS - Delegate to pdf_cache
    # =========================================================================

    def get_app_setting(self, key: str, default = None):
        """Get application setting"""
        return self.pdf_cache.get_app_setting(key, default)

    def set_app_setting(self, key: str, value, setting_type: str = None, description: str = None):
        """Set application setting"""
        return self.pdf_cache.set_app_setting(key, value, setting_type, description)

    # =========================================================================
    # PDF FINGERPRINTING - Delegate to pdf_cache
    # =========================================================================

    def check_pdf_fingerprint_exists(self, fingerprint: str) -> bool:
        """Check if PDF fingerprint exists (for deduplication)"""
        return self.pdf_cache.check_pdf_fingerprint_exists(fingerprint)

    def record_pdf_fingerprint(self, fingerprint: str, doc_id: str, metadata: dict):
        """Record PDF fingerprint for deduplication"""
        return self.pdf_cache.record_pdf_fingerprint(fingerprint, doc_id, metadata)

    def get_pdf_by_fingerprint(self, fingerprint: str):
        """Get PDF details by fingerprint"""
        return self.pdf_cache.get_pdf_by_fingerprint(fingerprint)
