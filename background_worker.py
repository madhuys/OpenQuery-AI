"""
Background PDF Worker - Processes slow PDFs without time limits

This worker runs continuously, monitoring the background queue and processing
PDFs that timed out during fast lane processing.

Features:
- Runs as a standalone process (can be system service)
- No timeout limits - processes PDFs completely
- Automatic retry on failure (up to max_retry_attempts)
- Results cached for future queries
- Graceful shutdown on SIGTERM/SIGINT

Usage:
    python background_worker.py

    Or as a system service (systemd example):
    [Unit]
    Description=PDF Background Processing Worker
    After=network.target

    [Service]
    Type=simple
    User=your_user
    WorkingDirectory=/path/to/serper-search-app
    ExecStart=/usr/bin/python3 background_worker.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
"""

import time
import signal
import sys
import logging
import sqlite3
import hashlib
from pathlib import Path
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.background_queue_service import get_queue_service
from services.pdf_processing_service import process_pdf_complete
from services.html_processing_service import process_html_complete
from services.pdf_cache_service import PDFCacheService
from services.cache_service import CacheService
from config.settings import AppSettings, SETTINGS_FILE

# Import Playwright download function
try:
    from services.pdf_service import _download_with_playwright, PDF_DOWNLOAD_DIR
    HAS_PLAYWRIGHT_SUPPORT = True
except ImportError:
    HAS_PLAYWRIGHT_SUPPORT = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [BACKGROUND-WORKER] %(message)s',
    handlers=[
        logging.FileHandler('logs/background_worker.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def reset_stuck_items_in_queue(queue_service):
    """
    Reset items stuck in 'processing' state back to 'pending'.
    This happens when worker was stopped while processing items.

    Args:
        queue_service: Queue service instance

    Returns:
        int: Number of items reset
    """
    db_path = Path("db/background_queue.db")
    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("""
            UPDATE background_pdf_queue
            SET status = 'pending',
                started_at = NULL
            WHERE status = 'processing'
        """)
        conn.commit()
        reset_count = cursor.rowcount
        conn.close()

        return reset_count
    except Exception as e:
        logger.warning(f"Could not reset stuck items: {e}")
        return 0


def process_protected_pdf_download(url, queue_id):
    """
    Download protected PDFs using Chrome impersonation methods (no Playwright needed!).

    Tests show McKinsey, WhiteHouse.gov, Protiviti all work with simple Chrome headers.
    Uses cascade: requests → requests.Session → httpx → requests+Referer

    Args:
        url: PDF URL to download
        queue_id: Queue item ID

    Returns:
        tuple: (success, error_message, filepath)
    """
    import requests

    # Generate filepath
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    path_name = Path(urlparse(url).path).name or "download.pdf"
    filename = f"{url_hash}_{path_name}"
    filepath = PDF_DOWNLOAD_DIR / filename

    logger.info(f"[WORKER] Processing protected PDF download for queue item #{queue_id}")
    logger.info(f"[WORKER] URL: {url[:80]}...")
    logger.info(f"[WORKER] File: {filename}")

    # Chrome headers to bypass bot detection
    # Chrome 131 headers
    # NOTE: Accept-Encoding NOT included - requests handles compression automatically
    # If you set Accept-Encoding manually, requests won't auto-decompress and files get corrupted!
    CHROME_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        # Accept-Encoding removed - let requests handle it automatically
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    last_error = None

    # METHOD 1: Standard requests + Chrome headers
    try:
        logger.info(f"[WORKER] Method 1: requests + Chrome headers")
        start = time.time()

        response = requests.get(url, headers=CHROME_HEADERS, timeout=30, allow_redirects=True)
        elapsed = time.time() - start

        if response.status_code == 200 and len(response.content) > 100:
            filepath.write_bytes(response.content)
            size_mb = len(response.content) / (1024 * 1024)
            logger.info(f"[WORKER] ✅ Method 1 SUCCESS: {size_mb:.2f}MB in {elapsed:.2f}s")

            # Cache the result
            cache = CacheService()
            pdf_hash = hashlib.md5(response.content).hexdigest()
            cache.record_pdf_download_success(url, response.content, pdf_hash, 'requests_chrome', str(filepath))

            return True, None, str(filepath)
        else:
            last_error = f"HTTP {response.status_code}"
            logger.warning(f"[WORKER] Method 1 failed: {last_error}")
    except Exception as e:
        last_error = str(e)[:200]
        logger.warning(f"[WORKER] Method 1 error: {last_error}")

    # METHOD 2: requests.Session + Chrome headers
    try:
        logger.info(f"[WORKER] Method 2: requests.Session + Chrome headers")
        start = time.time()

        session = requests.Session()
        session.headers.update(CHROME_HEADERS)
        response = session.get(url, timeout=30, allow_redirects=True)
        elapsed = time.time() - start

        if response.status_code == 200 and len(response.content) > 100:
            filepath.write_bytes(response.content)
            size_mb = len(response.content) / (1024 * 1024)
            logger.info(f"[WORKER] ✅ Method 2 SUCCESS: {size_mb:.2f}MB in {elapsed:.2f}s")

            # Cache the result
            cache = CacheService()
            pdf_hash = hashlib.md5(response.content).hexdigest()
            cache.record_pdf_download_success(url, response.content, pdf_hash, 'session_chrome', str(filepath))

            return True, None, str(filepath)
        else:
            last_error = f"HTTP {response.status_code}"
            logger.warning(f"[WORKER] Method 2 failed: {last_error}")
    except Exception as e:
        last_error = str(e)[:200]
        logger.warning(f"[WORKER] Method 2 error: {last_error}")

    # METHOD 3: httpx + HTTP/2 + Chrome headers
    try:
        import httpx

        logger.info(f"[WORKER] Method 3: httpx + HTTP/2 + Chrome headers")
        start = time.time()

        with httpx.Client(headers=CHROME_HEADERS, timeout=30.0, follow_redirects=True, http2=True) as client:
            response = client.get(url)
        elapsed = time.time() - start

        if response.status_code == 200 and len(response.content) > 100:
            filepath.write_bytes(response.content)
            size_mb = len(response.content) / (1024 * 1024)
            logger.info(f"[WORKER] ✅ Method 3 SUCCESS: {size_mb:.2f}MB in {elapsed:.2f}s")

            # Cache the result
            cache = CacheService()
            pdf_hash = hashlib.md5(response.content).hexdigest()
            cache.record_pdf_download_success(url, response.content, pdf_hash, 'httpx_chrome', str(filepath))

            return True, None, str(filepath)
        else:
            last_error = f"HTTP {response.status_code}"
            logger.warning(f"[WORKER] Method 3 failed: {last_error}")
    except Exception as e:
        last_error = str(e)[:200]
        logger.warning(f"[WORKER] Method 3 error: {last_error}")

    # METHOD 4: requests + Referer header (mimic navigation)
    try:
        logger.info(f"[WORKER] Method 4: requests + Referer + Chrome headers")
        start = time.time()

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        headers = CHROME_HEADERS.copy()
        headers['Referer'] = domain

        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        elapsed = time.time() - start

        if response.status_code == 200 and len(response.content) > 100:
            filepath.write_bytes(response.content)
            size_mb = len(response.content) / (1024 * 1024)
            logger.info(f"[WORKER] ✅ Method 4 SUCCESS: {size_mb:.2f}MB in {elapsed:.2f}s")

            # Cache the result
            cache = CacheService()
            pdf_hash = hashlib.md5(response.content).hexdigest()
            cache.record_pdf_download_success(url, response.content, pdf_hash, 'requests_referer', str(filepath))

            return True, None, str(filepath)
        else:
            last_error = f"HTTP {response.status_code}"
            logger.warning(f"[WORKER] Method 4 failed: {last_error}")
    except Exception as e:
        last_error = str(e)[:200]
        logger.warning(f"[WORKER] Method 4 error: {last_error}")

    # All methods failed
    logger.error(f"[WORKER] ❌ ALL METHODS FAILED: {last_error}")
    return False, f"All download methods failed: {last_error}", None


class BackgroundWorker:
    """Background worker for processing slow PDFs"""

    def __init__(self):
        """Initialize the background worker"""
        self.running = False
        self.queue_service = get_queue_service()
        self.cache_service = PDFCacheService()

        # Load settings
        try:
            self.settings = AppSettings.load(SETTINGS_FILE)
            logger.info("Settings loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load settings, using defaults: {e}")
            self.settings = AppSettings()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info("Background worker initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()

    def start(self):
        """Start the background worker"""
        if not self.settings.background.enabled:
            logger.warning("Background processing is disabled in settings")
            return

        if not self.settings.background.worker_enabled:
            logger.warning("Background worker is disabled in settings")
            return

        logger.info("=" * 80)
        logger.info("BACKGROUND PDF WORKER STARTING")
        logger.info("=" * 80)
        logger.info(f"Queue path: {self.settings.background.queue_path}")
        logger.info(f"Worker sleep interval: {self.settings.background.worker_sleep_interval}s")
        logger.info(f"Max retry attempts: {self.settings.background.max_retry_attempts}")
        logger.info(f"Playwright support: {'Yes' if HAS_PLAYWRIGHT_SUPPORT else 'No'}")
        logger.info("=" * 80)

        # Reset any items stuck in 'processing' state
        logger.info("🔄 Syncing queue state...")
        reset_count = reset_stuck_items_in_queue(self.queue_service)
        if reset_count > 0:
            logger.info(f"✅ Reset {reset_count} stuck item(s) from 'processing' to 'pending'")
        else:
            logger.info("✅ No stuck items found")
        logger.info("")

        self.running = True
        processed_count = 0
        failed_count = 0
        playwright_count = 0

        while self.running:
            try:
                # Get next pending item from queue
                item = self.queue_service.get_next_pending()

                if item is None:
                    # No pending items - sleep and check again
                    time.sleep(self.settings.background.worker_sleep_interval)
                    continue

                # Process the document (PDF or HTML)
                doc_type = item.get('doc_type', 'pdf')
                logger.info("=" * 80)
                logger.info(f"Processing queued {doc_type.upper()} (ID: {item['id']})")
                logger.info(f"URL: {item['url'][:80]}...")
                logger.info(f"Retry count: {item['retry_count']}/{item['max_retries']}")

                # Check if this is a Playwright-specific item
                metadata = item.get('metadata', {})
                is_playwright_item = metadata.get('reason') == 'playwright_subprocess_conflict'

                if is_playwright_item:
                    logger.info("Item type: Playwright-only download (subprocess conflict)")
                elif doc_type == 'html':
                    logger.info("Item type: Full HTML processing")
                else:
                    logger.info("Item type: Full PDF processing")

                logger.info("=" * 80)

                # Mark as processing
                self.queue_service.mark_processing(item['id'])

                # Process based on item type
                start_time = time.time()

                try:
                    if is_playwright_item:
                        # PROTECTED PDF DOWNLOAD (Chrome impersonation - no Playwright needed!)
                        logger.info("🔐 Attempting protected PDF download with Chrome headers...")
                        success, error, filepath = process_protected_pdf_download(item['url'], item['id'])

                        elapsed = time.time() - start_time

                        if success:
                            logger.info(f"✅ Protected PDF download successful in {elapsed:.2f}s")
                            logger.info(f"   Filepath: {filepath}")

                            # Mark as completed
                            self.queue_service.mark_completed(item['id'], result_cache_key=filepath)
                            processed_count += 1
                        else:
                            logger.error(f"❌ Protected PDF download failed: {error}")
                            self.queue_service.mark_failed(item['id'], error, increment_retry=True)
                            failed_count += 1

                    elif doc_type == 'html':
                        # FULL HTML PROCESSING (download + extraction + scoring + NLP)
                        # Using new unified service - NO TIMEOUT in background queue
                        result = process_html_complete(
                            url=item['url'],
                            index=0,
                            progress_callback=None,
                            settings=self.settings,
                            fast_lane_mode=False  # Full NLP analysis in background
                        )

                        elapsed = time.time() - start_time

                        # Check if processing was successful
                        if result.get('status') == 'success':
                            logger.info(f"✅ Successfully processed HTML in {elapsed:.2f}s")
                            logger.info(f"   Title: {result.get('title', 'N/A')}")
                            logger.info(f"   Score: {result.get('final_score', 0)}/100")
                            logger.info(f"   Words: {result.get('word_count', 0)}")

                            # Mark as completed with cache key (using URL or doc_id)
                            cache_key = result.get('doc_id') or item['url']
                            self.queue_service.mark_completed(item['id'], cache_key)

                            processed_count += 1

                        else:
                            # Processing failed
                            error_msg = result.get('error', 'Unknown error')
                            logger.error(f"❌ Processing failed: {error_msg}")

                            self.queue_service.mark_failed(
                                item['id'],
                                error_msg,
                                increment_retry=True
                            )

                            failed_count += 1

                    else:
                        # FULL PDF PROCESSING (download + text extraction + scoring)
                        result = process_pdf_complete(
                            url=item['url'],
                            index=0,
                            progress_callback=None,
                            max_size_mb=self.settings.analysis.pdf_max_size_mb,
                            enable_scoring=True,
                            timeout=None,  # No timeout for background processing
                            max_retries=self.settings.analysis.max_retry_attempts
                        )

                        elapsed = time.time() - start_time

                        # Check if processing was successful
                        if result.get('status') == 'success':
                            logger.info(f"✅ Successfully processed PDF in {elapsed:.2f}s")
                            logger.info(f"   Title: {result.get('title', 'N/A')}")
                            logger.info(f"   Score: {result.get('final_score', 0)}/100")
                            logger.info(f"   Words: {result.get('word_count', 0)}")

                            # Mark as completed with cache key (using URL or fingerprint)
                            cache_key = result.get('fingerprint') or result.get('doc_id') or item['url']
                            self.queue_service.mark_completed(item['id'], cache_key)

                            processed_count += 1

                        else:
                            # Processing failed
                            error_msg = result.get('error', 'Unknown error')
                            logger.error(f"❌ Processing failed: {error_msg}")

                            self.queue_service.mark_failed(
                                item['id'],
                                error_msg,
                                increment_retry=True
                            )

                            failed_count += 1

                except Exception as e:
                    # Exception during processing
                    elapsed = time.time() - start_time
                    error_msg = str(e)

                    logger.error(f"❌ Exception during processing: {error_msg}")
                    logger.exception(e)

                    self.queue_service.mark_failed(
                        item['id'],
                        error_msg,
                        increment_retry=True
                    )

                    failed_count += 1

                # Log statistics
                logger.info("-" * 80)
                logger.info(f"Session stats: Processed={processed_count} (Playwright: {playwright_count}), Failed={failed_count}")

                # Get queue stats
                stats = self.queue_service.get_queue_stats()
                logger.info(f"Queue stats: Pending={stats['pending']}, Processing={stats['processing']}, "
                           f"Completed={stats['completed']}, Failed={stats['failed']}")
                logger.info("-" * 80)

            except Exception as e:
                logger.error(f"Error in main worker loop: {e}")
                logger.exception(e)
                time.sleep(self.settings.background.worker_sleep_interval)

        logger.info("=" * 80)
        logger.info("BACKGROUND WORKER STOPPED")
        logger.info(f"Total processed: {processed_count} (Playwright: {playwright_count})")
        logger.info(f"Total failed: {failed_count}")
        logger.info("=" * 80)

    def stop(self):
        """Stop the background worker"""
        self.running = False

    def cleanup_old_completed(self):
        """Clean up old completed items from queue"""
        try:
            days = self.settings.background.cleanup_completed_days
            removed = self.queue_service.clear_completed(older_than_days=days)
            if removed > 0:
                logger.info(f"Cleaned up {removed} completed items older than {days} days")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Main entry point"""
    # Create logs directory if it doesn't exist
    Path('logs').mkdir(exist_ok=True)

    # Create worker and start
    worker = BackgroundWorker()

    # Perform cleanup before starting
    logger.info("Performing initial cleanup...")
    worker.cleanup_old_completed()

    # Start processing
    worker.start()


if __name__ == "__main__":
    main()
