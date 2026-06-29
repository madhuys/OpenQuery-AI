"""
PDF Download Service V2 - WITH SMART TIMEOUT AND curl_cffi
TRUE PARALLEL - each function call handles ONE file in ONE thread/process
NO orchestration here - just download logic

NEW FEATURES:
- 5-second "first byte" timeout (abort if download doesn't START)
- curl_cffi as PRIMARY method (fast, works on protected sites like McKinsey)
- Playwright as FALLBACK (for sites that block even curl_cffi)
- Domain-based method caching (remember what works per domain)
- ProcessPoolExecutor-safe: Playwright disabled in subprocesses (async conflict prevention)
"""
import time
import hashlib
import threading
import multiprocessing
from pathlib import Path
from typing import Optional, Callable, Dict
from urllib.parse import urlparse
from collections import defaultdict
from services.cache_service import CacheService

# Import both standard and advanced HTTP clients
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    print("[WARN] curl_cffi not installed - protected PDFs may timeout")

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("[WARN] playwright not installed - fallback unavailable")


# Global per-domain rate limiting (thread-safe)
_domain_semaphores = defaultdict(lambda: threading.Semaphore(4))
_domain_lock = threading.Lock()

PDF_DOWNLOAD_DIR = Path("downloaded_pdfs")
PDF_DOWNLOAD_DIR.mkdir(exist_ok=True)

# Timeout configuration (NEW)
CONNECT_TIMEOUT = 10  # seconds to establish connection
FIRST_BYTE_TIMEOUT = 5  # seconds to receive first byte (abort if slower)
READ_TIMEOUT = 120  # total download timeout after first byte
CHUNK_SIZE = 1 << 20  # 1 MB chunks
MIN_SPEED_BPS = 64 * 1024  # 64 KB/s minimum speed

# Domain method cache (in production, store in database)
_domain_method_cache = {}  # {domain: 'curl_cffi' | 'playwright'}


def _get_browser_headers(url: str) -> dict:
    """
    Generate Chrome 131 browser headers (tested working on McKinsey, WhiteHouse, Protiviti)

    NOTE: Accept-Encoding is NOT included - requests library handles compression automatically.
    If you set Accept-Encoding manually, requests won't auto-decompress!
    """
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        # Accept-Encoding removed - let requests handle it automatically to avoid corruption
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Referer': url,
    }


def _download_with_curl_cffi(
    url: str,
    filepath: Path,
    index: int,
    progress_callback: Optional[Callable]
) -> tuple[bool, Optional[str], float]:
    """
    PRIMARY: Fast download with curl_cffi (HTTP/2, Chrome impersonation)

    Returns: (success, error_msg, elapsed_time)
    """
    if not HAS_CURL_CFFI:
        return False, "curl_cffi not installed", 0.0

    start = time.time()

    try:
        # Try to create session with chrome impersonation
        try:
            session = curl_requests.Session(impersonate="chrome")
        except Exception as e:
            # If impersonation not supported (e.g., Windows), fall back to standard requests
            print(f"[PDF-{index}] [WARN] curl_cffi impersonation not supported: {e}, falling back to requests")
            import requests
            return _download_with_requests(url, filepath, index, progress_callback)

        try:
            # Optional: Wake up CDN with range request
            try:
                session.get(
                    url,
                    headers={**_get_browser_headers(url), "Range": "bytes=0-0"},
                    timeout=(CONNECT_TIMEOUT, 5),
                    allow_redirects=True,
                )
            except Exception:
                pass

            # Main download with streaming
            response = session.get(
                url,
                headers=_get_browser_headers(url),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                stream=True,
                allow_redirects=True,
            )
            response.raise_for_status()

            total_size = int(response.headers.get("Content-Length", 0))
            first_byte_deadline = time.time() + FIRST_BYTE_TIMEOUT

            bytes_read = 0
            speed_window_start = time.time()
            speed_window_bytes = 0
            last_progress_time = 0  # Throttle progress updates

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(CHUNK_SIZE):
                    now = time.time()

                    # Check first byte timeout
                    if bytes_read == 0 and now > first_byte_deadline:
                        print(f"[PDF-{index}] [EMOJI] First byte timeout (>{FIRST_BYTE_TIMEOUT}s)")
                        return False, f"First byte timeout (>{FIRST_BYTE_TIMEOUT}s)", now - start

                    if not chunk:
                        continue

                    f.write(chunk)
                    bytes_read += len(chunk)
                    speed_window_bytes += len(chunk)

                    # Progress callback (throttled to every 100ms to avoid overwhelming event loop)
                    if progress_callback and (now - last_progress_time >= 0.1):
                        try:
                            percent = int((bytes_read / total_size) * 90) if total_size else 50
                            progress_callback(index, 'download', percent)
                            last_progress_time = now
                        except:
                            pass

                    # Check sustained speed every 5s
                    if now - speed_window_start >= 5:
                        bps = speed_window_bytes / (now - speed_window_start)
                        speed_window_start = now
                        speed_window_bytes = 0

                        if bps < MIN_SPEED_BPS:
                            print(f"[PDF-{index}] [EMOJI] Speed too slow ({bps/1024:.1f} KB/s)")
                            return False, f"Speed too slow ({bps/1024:.1f} KB/s)", now - start

            elapsed = time.time() - start
            print(f"[PDF-{index}] [OK] curl_cffi SUCCESS: {bytes_read/1024/1024:.2f} MB in {elapsed:.2f}s")
            return True, None, elapsed
        finally:
            session.close()

    except Exception as e:
        elapsed = time.time() - start
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"[PDF-{index}] [ERROR] curl_cffi FAILED: {error_msg}")
        return False, error_msg, elapsed


def _download_with_requests(
    url: str,
    filepath: Path,
    index: int,
    progress_callback: Optional[Callable]
) -> tuple[bool, Optional[str], float]:
    """
    FALLBACK: Standard requests library with browser headers

    Returns: (success, error_msg, elapsed_time)
    """
    import requests
    start = time.time()

    try:
        response = requests.get(
            url,
            headers=_get_browser_headers(url),
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            stream=True,
            allow_redirects=True
        )
        response.raise_for_status()

        total_size = int(response.headers.get("Content-Length", 0))
        bytes_read = 0

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(CHUNK_SIZE):
                if not chunk:
                    continue

                f.write(chunk)
                bytes_read += len(chunk)

                # Progress callback
                if progress_callback and total_size:
                    try:
                        percent = int((bytes_read / total_size) * 90)
                        progress_callback(index, 'download', percent)
                    except:
                        pass

        elapsed = time.time() - start
        print(f"[PDF-{index}] [OK] requests SUCCESS: {bytes_read/1024/1024:.2f} MB in {elapsed:.2f}s")
        return True, None, elapsed

    except Exception as e:
        elapsed = time.time() - start
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"[PDF-{index}] [ERROR] requests FAILED: {error_msg}")
        return False, error_msg, elapsed


def _download_with_session(
    url: str,
    filepath: Path,
    index: int,
    progress_callback: Optional[Callable]
) -> tuple[bool, Optional[str], float]:
    """
    METHOD 2: requests.Session with persistent connection + Chrome headers

    Returns: (success, error_msg, elapsed_time)
    """
    import requests
    start = time.time()

    try:
        session = requests.Session()
        session.headers.update(_get_browser_headers(url))

        response = session.get(
            url,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            stream=True,
            allow_redirects=True
        )
        response.raise_for_status()

        total_size = int(response.headers.get("Content-Length", 0))
        bytes_read = 0

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(CHUNK_SIZE):
                if not chunk:
                    continue

                f.write(chunk)
                bytes_read += len(chunk)

                # Progress callback
                if progress_callback and total_size:
                    try:
                        percent = int((bytes_read / total_size) * 90)
                        progress_callback(index, 'download', percent)
                    except:
                        pass

        elapsed = time.time() - start
        print(f"[PDF-{index}] [OK] Session SUCCESS: {bytes_read/1024/1024:.2f} MB in {elapsed:.2f}s")
        return True, None, elapsed

    except Exception as e:
        elapsed = time.time() - start
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"[PDF-{index}] [ERROR] Session FAILED: {error_msg}")
        return False, error_msg, elapsed


def _download_with_httpx(
    url: str,
    filepath: Path,
    index: int,
    progress_callback: Optional[Callable]
) -> tuple[bool, Optional[str], float]:
    """
    METHOD 3: httpx with HTTP/2 + Chrome headers

    Returns: (success, error_msg, elapsed_time)
    """
    start = time.time()

    try:
        import httpx

        with httpx.Client(
            headers=_get_browser_headers(url),
            timeout=30.0,
            follow_redirects=True,
            http2=True
        ) as client:
            response = client.get(url)

        response.raise_for_status()

        filepath.write_bytes(response.content)
        size_mb = len(response.content) / (1024 * 1024)

        elapsed = time.time() - start
        print(f"[PDF-{index}] [OK] httpx SUCCESS: {size_mb:.2f} MB in {elapsed:.2f}s")
        return True, None, elapsed

    except Exception as e:
        elapsed = time.time() - start
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"[PDF-{index}] [ERROR] httpx FAILED: {error_msg}")
        return False, error_msg, elapsed


def _download_with_playwright(
    url: str,
    filepath: Path,
    index: int,
    progress_callback: Optional[Callable]
) -> tuple[bool, Optional[str], float]:
    """
    FALLBACK: Real browser download with Playwright

    IMPORTANT: Playwright cannot run in ProcessPoolExecutor subprocesses due to event loop conflicts.
    This function will skip Playwright when called from a subprocess.

    Returns: (success, error_msg, elapsed_time)
    """
    if not HAS_PLAYWRIGHT:
        return False, "playwright not installed", 0.0

    # Detect if we're in a ProcessPoolExecutor subprocess
    is_subprocess = multiprocessing.current_process().name != 'MainProcess'

    if is_subprocess:
        # Playwright cannot run in subprocess due to async event loop conflicts
        # Add to background queue for later processing
        try:
            from services.background_queue_service import get_queue_service
            queue = get_queue_service()
            queue.add_to_queue(
                url,
                metadata={
                    'reason': 'playwright_subprocess_conflict',
                    'index': index,
                    'original_filepath': str(filepath)
                }
            )
            print(f"[PDF-{index}] [QUEUE] Added to background queue for Playwright processing")
        except Exception as e:
            print(f"[PDF-{index}] [WARN] Failed to add to queue: {e}")

        print(f"[PDF-{index}] [WARN] Skipping Playwright in subprocess (will retry in background)")
        return False, "added to background queue for playwright retry", 0.0

    # Progress callback
    if progress_callback:
        try:
            progress_callback(index, 'download', 50)
        except:
            pass

    # Run Playwright directly (only safe in main process)
    start = time.time()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            # Navigate and trigger download
            with page.expect_download(timeout=READ_TIMEOUT * 1000) as download_info:
                page.goto(url, wait_until="domcontentloaded")

            download = download_info.value
            download.save_as(str(filepath))
            browser.close()

            elapsed = time.time() - start
            size_mb = filepath.stat().st_size / 1024 / 1024
            print(f"[PDF-{index}] [OK] Playwright SUCCESS: {size_mb:.2f} MB in {elapsed:.2f}s")
            return True, None, elapsed

    except Exception as e:
        elapsed = time.time() - start
        error_msg = f"{type(e).__name__}: {str(e)[:100]}"
        print(f"[PDF-{index}] [ERROR] Playwright FAILED: {error_msg}")
        return False, error_msg, elapsed


def download_pdf_parallel(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    max_retries: int = 2,
    timeout: int = 30,
    max_size_mb: int = 60
) -> Dict:
    """
    Download ONE PDF file in current thread/process - FAST LANE (single method)

    Strategy:
    1. Check cache first (instant return if already downloaded)
    2. Try requests + Chrome 131 headers (simple, fast, tested on McKinsey/WhiteHouse/Protiviti)
    3. If fails/timeout: Background worker will try all 4 methods with unlimited time

    Args:
        url: PDF URL
        index: URL index (for progress reporting)
        progress_callback: Optional callback(index, stage, percent)
        max_retries: Max retry attempts (deprecated - now uses method cascade)
        timeout: Download timeout in seconds (deprecated - now uses smart timeouts)
        max_size_mb: Max file size in MB

    Returns:
        Result dict with status and details
    """
    thread_id = threading.current_thread().ident
    thread_name = threading.current_thread().name
    print(f"[PDF-{index}] [THREAD] THREAD STARTED: {thread_name} (ID:{thread_id}) for {url[:60]}...")
    print(f"[PDF-{index}] [TIME] Start time: {time.strftime('%H:%M:%S')}")
    start_time = time.time()

    # Initialize cache
    cache = CacheService()

    # STEP 0: Check if PDF already downloaded (BEFORE downloading!)
    if not cache.should_download_pdf(url):
        cached_filepath = cache.get_cached_pdf_filepath(url)

        if cached_filepath and Path(cached_filepath).exists():
            print(f"[PDF-{index}] [OK] CACHE HIT: PDF already downloaded")

            file_size_mb = Path(cached_filepath).stat().st_size / (1024 * 1024)

            if progress_callback:
                try:
                    progress_callback(index, 'complete', 100)
                except:
                    pass

            return {
                'status': 'success',
                'url': url,
                'index': index,
                'title': f'PDF Cached ({file_size_mb:.1f}MB)',
                'content': f'PDF file already cached. Size: {file_size_mb:.1f}MB.',
                'cleaned_text': f'PDF cached: {file_size_mb:.1f}MB',
                'word_count': 0,
                'quality_score': 100,
                'final_score': 100,
                'quality_class': 'downloaded',
                'pdf_size_mb': file_size_mb,
                'pdf_filepath': cached_filepath,
                'content_type': 'pdf',
                'download_status': 'cached',
                'cached': True,
                'cache_reason': 'pdf_already_downloaded',
                'download_time': 0.0
            }

    print(f"[PDF-{index}] [EMOJI] NO CACHE: Starting download...")

    # Get domain for rate limiting
    domain = urlparse(url).netloc

    # Acquire domain semaphore (max 4 concurrent downloads per domain)
    with _domain_lock:
        semaphore = _domain_semaphores[domain]

    print(f"[PDF-{index}] [EMOJI] WAITING for semaphore (domain: {domain}) at {time.strftime('%H:%M:%S')}...")
    semaphore.acquire()
    print(f"[PDF-{index}] [OK] SEMAPHORE ACQUIRED at {time.strftime('%H:%M:%S')} - Starting download")

    try:
        # Generate filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
        filename = f"{url_hash}_{Path(urlparse(url).path).name}"
        filepath = PDF_DOWNLOAD_DIR / filename

        # Progress: Starting
        if progress_callback:
            try:
                progress_callback(index, 'download', 10)
            except:
                pass

        # FAST LANE: Single method (requests + Chrome 131 headers)
        # If this fails/times out, background worker will try all 4 methods
        print(f"[PDF-{index}] [DOWNLOAD] FAST LANE: requests + Chrome 131 headers - Starting at {time.strftime('%H:%M:%S')}")
        method_start = time.time()
        success, error, elapsed = _download_with_requests(url, filepath, index, progress_callback)
        print(f"[PDF-{index}] [DOWNLOAD] Fast lane returned after {time.time()-method_start:.2f}s: success={success}")

        if success and filepath.exists() and filepath.stat().st_size > 0:
            # Cache successful download
            _domain_method_cache[domain] = 'requests'
            download_method = 'requests'
        else:
            # FAST LANE FAILED - Will be queued to background for retry with all methods
            print(f"[PDF-{index}] [ERROR] FAST LANE FAILED: {error}")
            return {
                'status': 'error',
                'error': f'Fast lane download failed: {error}',
                'url': url,
                'index': index
            }

        # Verify file size
        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        if file_size_mb > max_size_mb:
            filepath.unlink()
            return {
                'status': 'error',
                'error': f'PDF too large: {file_size_mb:.1f}MB > {max_size_mb}MB limit',
                'url': url,
                'index': index
            }

        # Cache the download
        try:
            pdf_bytes = filepath.read_bytes()
            pdf_hash = hashlib.md5(pdf_bytes).hexdigest()

            cache.record_pdf_download_success(
                url=url,
                pdf_bytes=pdf_bytes,
                pdf_hash=pdf_hash,
                download_method=download_method,
                filepath=str(filepath)
            )
            print(f"[PDF-{index}] [OK] Cached download for future use (hash: {pdf_hash[:8]}...)")
        except Exception as e:
            print(f"[PDF-{index}] [WARN] Cache write failed: {e}")

        # Progress: Complete
        if progress_callback:
            try:
                progress_callback(index, 'complete', 100)
                print(f"[PDF-{index}] [EMOJI] Sent completion callback to frontend")
            except Exception as e:
                print(f"[PDF-{index}] [WARN] Completion callback failed: {e}")

        total_time = time.time() - start_time

        return {
            'status': 'success',
            'url': url,
            'index': index,
            'title': f'PDF Downloaded ({file_size_mb:.1f}MB)',
            'content': f'PDF file downloaded successfully via {download_method}. Size: {file_size_mb:.1f}MB.',
            'cleaned_text': f'PDF downloaded: {file_size_mb:.1f}MB',
            'word_count': 0,
            'quality_score': 100,
            'final_score': 100,
            'quality_class': 'downloaded',
            'pdf_size_mb': file_size_mb,
            'pdf_filepath': str(filepath),
            'content_type': 'pdf',
            'download_status': 'success',
            'download_method': download_method,
            'download_time': total_time,
            'process_time': total_time
        }

    finally:
        semaphore.release()
        print(f"[PDF-{index}] Released semaphore for domain: {domain}")
