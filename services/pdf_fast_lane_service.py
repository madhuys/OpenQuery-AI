"""
PDF Fast Lane Service - Two-Tier Processing System

This service implements a two-tier PDF processing system:
- Fast Lane: 8 second timeout for immediate results
- Background Queue: Unlimited time for slow PDFs, cached for future use

Flow:
1. Check background queue for existing results
2. Try fast lane processing (8s timeout)
3. If timeout: Add to background queue, return placeholder
4. If success: Return results immediately
"""

import time
import logging
import signal
from contextlib import contextmanager
from typing import Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from services.pdf_processing_service import process_pdf_complete
from services.background_queue_service import get_queue_service
from services.pdf_cache_service import PDFCacheService
from config.settings import AppSettings, SETTINGS_FILE

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Custom exception for timeouts"""
    pass


@contextmanager
def time_limit(seconds: int):
    """
    Context manager for enforcing time limits using signals.
    Note: Only works on Unix systems. Falls back to ThreadPoolExecutor on Windows.
    """
    def signal_handler(signum, frame):
        raise TimeoutException(f"Timed out after {seconds} seconds")

    # Check if signal is available (Unix systems)
    try:
        signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
    except (AttributeError, ValueError):
        # Windows or signal not available - will use ThreadPoolExecutor instead
        yield


def process_pdf_with_timeout(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    timeout: int = 8,
    **kwargs
) -> Dict:
    """
    Process PDF with a timeout limit.

    Uses ThreadPoolExecutor for cross-platform timeout support.

    Args:
        url: PDF URL
        index: URL index
        progress_callback: Optional callback
        timeout: Timeout in seconds
        **kwargs: Additional arguments for process_pdf_complete

    Returns:
        Processing result or timeout error
    """
    # Load settings for router_max_workers
    settings = AppSettings.load(SETTINGS_FILE).analysis

    # Use manual executor management instead of context manager
    # Context manager calls shutdown(wait=True) which blocks until completion
    executor = ThreadPoolExecutor(max_workers=settings.router_max_workers)
    try:
        future = executor.submit(
            process_pdf_complete,
            url,
            index,
            progress_callback,
            **kwargs
        )

        try:
            result = future.result(timeout=timeout)
            return result
        except FutureTimeoutError:
            # Cancel the future (won't stop running futures, but prevents new ones)
            future.cancel()
            raise TimeoutException(f"PDF processing timed out after {timeout}s")
    finally:
        # Shutdown immediately without waiting
        executor.shutdown(wait=False)


def process_pdf_fast_lane(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    settings: Optional[AppSettings] = None,
) -> Dict:
    """
    Process PDF with two-tier system: Fast Lane → Background Queue.

    Flow:
    1. Check if URL is in background queue with completed status
       → If completed: Return cached result
    2. Check if URL is currently processing in background
       → If processing: Return placeholder
    3. Try fast lane processing (8s timeout)
       → If success: Return result
       → If timeout: Add to background queue, return placeholder

    Args:
        url: PDF URL to process
        index: URL index for progress tracking
        progress_callback: Optional callback(index, stage, percent)
        settings: Optional AppSettings instance

    Returns:
        Dict with processing result or background processing placeholder
    """
    start_time = time.time()

    # Load settings
    if settings is None:
        try:
            settings = AppSettings.load(SETTINGS_FILE)
        except Exception as e:
            logger.warning(f"Could not load settings, using defaults: {e}")
            settings = AppSettings()

    # Check if background processing is enabled
    if not settings.background.enabled:
        # Background processing disabled - use normal processing
        logger.info(f"[PDF-FASTLANE-{index}] Background processing disabled, using normal flow")
        return process_pdf_complete(
            url,
            index,
            progress_callback,
            max_size_mb=settings.analysis.pdf_max_size_mb,
            enable_scoring=True,
            timeout=settings.analysis.pdf_timeout,
            max_retries=settings.analysis.max_retry_attempts
        )

    # Initialize services
    queue_service = get_queue_service()
    cache_service = PDFCacheService()

    logger.info(f"[PDF-FASTLANE-{index}] Starting fast lane processing for: {url[:60]}...")

    # STEP 0: Check PDF cache FIRST (most important - skip if fresh)
    should_download, cached_data = cache_service.should_download_pdf(url)

    if not should_download and cached_data:
        # Fresh PDF in cache - return immediately
        logger.info(f"[PDF-FASTLANE-{index}] ✅ Fresh PDF found in cache!")

        # Check if it's an error/failure
        if 'error' in cached_data:
            logger.warning(f"[PDF-FASTLANE-{index}] Cached error/failure: {cached_data.get('error')}")
            elapsed = time.time() - start_time
            return {
                'status': 'error',
                'url': url,
                'index': index,
                'title': 'Cached Error',
                'content': '',
                'error': cached_data.get('error'),
                'heuristic_score': 0,
                'nlp_score': 0,
                'final_score': 0,
                'quality_class': 'error',
                'word_count': 0,
                'processing_time': elapsed,
                'cache_hit': True,
                'cache_reason': cached_data.get('cache_reason')
            }

        # Success case - need to load full PDF result from JSON file
        # The cached_data only has basic metadata, need to load full result
        logger.info(f"[PDF-FASTLANE-{index}] Loading full PDF result from JSON...")
        pdf_filepath = cache_service.get_cached_pdf_filepath(url)

        if pdf_filepath:
            # Try to load the JSON result file
            import json
            from pathlib import Path

            json_dir = Path('outputs') / 'pdf_json'
            # Find JSON file matching this PDF
            json_files = list(json_dir.glob(f"*{Path(pdf_filepath).stem}*.json"))

            if json_files:
                try:
                    with open(json_files[0], 'r', encoding='utf-8') as f:
                        full_result = json.load(f)

                    logger.info(f"[PDF-FASTLANE-{index}] ✅ Loaded cached PDF result from {json_files[0].name}")
                    elapsed = time.time() - start_time
                    full_result['processing_time'] = elapsed
                    full_result['cache_hit'] = True
                    full_result['cache_reason'] = cached_data.get('cache_reason', 'fresh_pdf')
                    return full_result
                except Exception as e:
                    logger.error(f"[PDF-FASTLANE-{index}] Error loading cached JSON: {e}")
                    # Fall through to reprocess

        # If we can't load the full result, fall through to reprocess
        logger.warning(f"[PDF-FASTLANE-{index}] Could not load full cached result, will reprocess")

    # STEP 1: Check background queue status
    queue_status = queue_service.get_status(url)

    if queue_status == 'completed':
        # PDF was processed in background - should also be in cache now
        logger.info(f"[PDF-FASTLANE-{index}] Found completed background processing, checking cache...")
        # The PDF cache check above should have caught this, but double-check
        should_download, cached_data = cache_service.should_download_pdf(url)
        if not should_download and cached_data and 'error' not in cached_data:
            logger.info(f"[PDF-FASTLANE-{index}] Background PDF now in cache")
            # Try to load full result (same logic as above)
            # For now, just note it's cached
            pass

    if queue_status == 'processing':
        # PDF is currently being processed in background
        logger.info(f"[PDF-FASTLANE-{index}] PDF currently processing in background queue")
        return {
            'status': 'background_processing',
            'url': url,
            'index': index,
            'title': 'Processing in background...',
            'content': '',
            'message': 'This PDF is being processed in the background. Results will be available for future queries.',
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_class': 'processing',
            'word_count': 0,
            'processing_time': time.time() - start_time
        }

    if queue_status == 'pending':
        # PDF is queued but not yet processing
        logger.info(f"[PDF-FASTLANE-{index}] PDF pending in background queue")
        return {
            'status': 'background_pending',
            'url': url,
            'index': index,
            'title': 'Queued for background processing...',
            'content': '',
            'message': 'This PDF is queued for background processing. Results will be available for future queries.',
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_class': 'pending',
            'word_count': 0,
            'processing_time': time.time() - start_time
        }

    # STEP 1.5: Check file size with HEAD request BEFORE downloading
    # If file is too large (>10MB), immediately queue to background
    try:
        import httpx
        with httpx.Client(timeout=3.0) as client:
            head_response = client.head(url, follow_redirects=True)
            content_length = int(head_response.headers.get('Content-Length', 0))

            if content_length > 0:
                size_mb = content_length / (1024 * 1024)
                logger.info(f"[PDF-FASTLANE-{index}] Detected file size: {size_mb:.2f} MB")

                # If file is larger than 10MB, skip fast lane entirely
                if size_mb > 10:
                    logger.info(f"[PDF-FASTLANE-{index}] 🚀 Large file ({size_mb:.2f} MB) - queuing to background immediately")

                    # Add to background queue immediately
                    metadata = {
                        'index': index,
                        'added_from': 'large_file_detection',
                        'file_size_mb': size_mb
                    }

                    queue_service.add_to_queue(
                        url,
                        metadata=metadata,
                        max_retries=settings.background.max_retry_attempts
                    )

                    return {
                        'status': 'background_queued',
                        'url': url,
                        'index': index,
                        'title': f'Processing in background (large PDF: {size_mb:.1f} MB)...',
                        'content': '',
                        'message': f'This PDF is {size_mb:.1f} MB. Large files are processed in the background to keep the UI responsive. Results will be available for future queries.',
                        'heuristic_score': 0,
                        'nlp_score': 0,
                        'final_score': 0,
                        'quality_class': 'queued',
                        'word_count': 0,
                        'processing_time': time.time() - start_time,
                        'file_size_mb': size_mb
                    }
    except Exception as e:
        # HEAD request failed - proceed with normal fast lane
        logger.debug(f"[PDF-FASTLANE-{index}] HEAD request failed: {e} - proceeding with fast lane")
        pass

    # STEP 2: Try fast lane processing with timeout
    logger.info(f"[PDF-FASTLANE-{index}] Attempting fast lane processing (timeout: {settings.background.fast_lane_timeout}s)")

    try:
        # Process with timeout
        result = process_pdf_with_timeout(
            url=url,
            index=index,
            progress_callback=progress_callback,
            timeout=settings.background.fast_lane_timeout,
            max_size_mb=settings.analysis.pdf_max_size_mb,
            enable_scoring=True,
            max_retries=settings.analysis.max_retry_attempts
        )

        elapsed = time.time() - start_time
        logger.info(f"[PDF-FASTLANE-{index}] ✅ Fast lane success in {elapsed:.2f}s")

        result['fast_lane_success'] = True
        result['processing_time'] = elapsed
        return result

    except TimeoutException as e:
        # Timeout occurred - add to background queue
        elapsed = time.time() - start_time
        logger.warning(f"[PDF-FASTLANE-{index}] ⏱️  Fast lane timeout after {elapsed:.2f}s - adding to background queue")

        # Add to background queue
        metadata = {
            'index': index,
            'added_from': 'fast_lane_timeout',
            'timeout_duration': elapsed
        }

        queue_service.add_to_queue(
            url,
            metadata=metadata,
            max_retries=settings.background.max_retry_attempts
        )

        return {
            'status': 'background_queued',
            'url': url,
            'index': index,
            'title': 'Processing in background (slow PDF)...',
            'content': '',
            'message': f'This PDF took too long to process (>{settings.background.fast_lane_timeout}s). It has been added to the background queue and will be available for future queries.',
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_class': 'queued',
            'word_count': 0,
            'processing_time': elapsed,
            'timeout_seconds': settings.background.fast_lane_timeout
        }

    except Exception as e:
        # Other error occurred
        elapsed = time.time() - start_time
        logger.error(f"[PDF-FASTLANE-{index}] ❌ Fast lane error: {e}")

        return {
            'status': 'error',
            'url': url,
            'index': index,
            'title': 'Processing Error',
            'content': '',
            'error': str(e),
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_class': 'error',
            'word_count': 0,
            'processing_time': elapsed
        }


def batch_process_pdfs_fast_lane(
    pdf_urls: list,
    progress_callback: Optional[Callable] = None,
    settings: Optional[AppSettings] = None,
    max_workers: int = 5
) -> list:
    """
    Process multiple PDFs in parallel using fast lane system.

    Args:
        pdf_urls: List of PDF URLs
        progress_callback: Optional callback
        settings: Optional AppSettings
        max_workers: Maximum parallel workers

    Returns:
        List of processing results
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if settings is None:
        try:
            settings = AppSettings.load(SETTINGS_FILE)
        except:
            settings = AppSettings()

    results = [None] * len(pdf_urls)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_pdf_fast_lane,
                url,
                index,
                progress_callback,
                settings
            ): index
            for index, url in enumerate(pdf_urls)
        }

        for future in as_completed(futures):
            index = futures[future]
            try:
                result = future.result()
                results[index] = result
            except Exception as e:
                logger.error(f"Error processing PDF {index}: {e}")
                results[index] = {
                    'status': 'error',
                    'url': pdf_urls[index],
                    'index': index,
                    'error': str(e),
                    'title': 'Processing Error',
                    'content': '',
                    'heuristic_score': 0,
                    'nlp_score': 0,
                    'final_score': 0,
                    'quality_class': 'error',
                    'word_count': 0
                }

    return results
