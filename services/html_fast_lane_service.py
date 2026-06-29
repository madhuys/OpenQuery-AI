"""
HTML Fast Lane Service - Two-Tier Processing System

This service implements a two-tier HTML processing system matching PDF architecture:
- Fast Lane: 6 second timeout for immediate results
- Background Queue: Unlimited time for slow HTML, cached for future use

Flow (MATCHES PDF ARCHITECTURE):
1. Check HTML cache FIRST (outside timeout zone)
2. Check background queue for existing results
3. Try fast lane processing (6s timeout - SINGLE WRAPPER)
4. If timeout: Add to background queue, return placeholder
5. If success: Return results immediately
"""

import time
import logging
from typing import Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from services.cache_service import CacheService
from services.background_queue_service import get_queue_service
from config.settings import AppSettings, SETTINGS_FILE

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Custom exception for timeouts"""
    pass


def process_html_with_timeout(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    timeout: int = 6,
    settings: Optional[AppSettings] = None,
    fast_lane_mode: bool = True
) -> Dict:
    """
    Process HTML with a timeout limit using ThreadPoolExecutor.

    This wraps the ENTIRE HTML processing pipeline in a single timeout.
    No internal timeout checks - let the executor manage it.

    Args:
        url: HTML URL
        index: URL index
        progress_callback: Optional callback
        timeout: Timeout in seconds
        settings: Optional AppSettings instance

    Returns:
        Processing result or timeout error
    """
    # Import here to avoid circular imports
    from services.html_processing_service import process_html_complete

    # Load settings if not provided
    if settings is None:
        settings = AppSettings.load(SETTINGS_FILE)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            process_html_complete,
            url,
            index,
            progress_callback,
            settings,
            fast_lane_mode  # Pass fast lane flag to skip NLP
        )

        try:
            result = future.result(timeout=timeout)
            return result
        except FutureTimeoutError:
            # Cancel the future
            future.cancel()
            raise TimeoutException(f"HTML processing timed out after {timeout}s")


def process_html_fast_lane(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    settings: Optional[AppSettings] = None,
) -> Dict:
    """
    Process HTML with two-tier system: Fast Lane → Background Queue.

    ARCHITECTURE MATCHES PDF SERVICE - Clean, single timeout wrapper.

    Flow:
    1. Check HTML cache FIRST (outside timeout zone)
       → If fresh: Return cached result immediately
    2. Check if URL is in background queue with completed status
       → If completed: Return cached result
    3. Check if URL is currently processing in background
       → If processing: Return placeholder
    4. Try fast lane processing (6s timeout - SINGLE WRAPPER)
       → If success: Return result
       → If timeout: Add to background queue, return placeholder

    Args:
        url: HTML URL to process
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
        # Background processing disabled - use fast processing (skip NLP)
        logger.info(f"[HTML-FASTLANE-{index}] Background processing disabled, using fast flow (no NLP)")
        from services.html_processing_service import process_html_complete
        return process_html_complete(url, index, progress_callback, settings, fast_lane_mode=True)

    # Initialize services
    cache_service = CacheService()
    queue_service = get_queue_service()

    logger.info(f"[HTML-FASTLANE-{index}] Starting fast lane processing for: {url[:60]}...")

    # STEP 0: Check HTML cache FIRST (like PDF does - OUTSIDE timeout zone)
    # First check for cached errors/filtered (15 day TTL)
    cached = cache_service.check_url_cache_status(url, error_ttl_days=15, filtered_ttl_days=15)

    if cached:
        logger.info(f"[HTML-FASTLANE-{index}] ✅ Fresh HTML error/filtered found in cache!")
        elapsed = time.time() - start_time
        cached['processing_time'] = elapsed
        cached['cache_hit'] = True
        return cached

    # Then check for successful cached results (content-type-based TTL)
    cache_decision = cache_service.get_reuse_decision(url, raw_html=None)
    if cache_decision.get('action') == 'reuse':
        cached_result = cache_decision.get('result', {})
        logger.info(f"[HTML-FASTLANE-{index}] ✅ Fresh successful HTML found in cache! ({cache_decision.get('reason')})")
        elapsed = time.time() - start_time
        cached_result['processing_time'] = elapsed
        cached_result['cache_hit'] = True
        return cached_result

    # STEP 1: Check background queue status
    queue_status = queue_service.get_status(url)

    if queue_status == 'completed':
        # HTML was processed in background - should also be in cache now
        logger.info(f"[HTML-FASTLANE-{index}] Found completed background processing, checking cache...")
        # Re-check cache since background worker should have populated it
        cached = cache_service.check_url_cache_status(url, error_ttl_days=15, filtered_ttl_days=15)
        if cached:
            logger.info(f"[HTML-FASTLANE-{index}] Background HTML now in cache")
            elapsed = time.time() - start_time
            cached['processing_time'] = elapsed
            cached['cache_hit'] = True
            return cached

    if queue_status == 'processing':
        # HTML is currently being processed in background
        logger.info(f"[HTML-FASTLANE-{index}] HTML currently processing in background queue")
        return {
            'status': 'background_processing',
            'url': url,
            'index': index,
            'title': 'Processing in background...',
            'content': '',
            'message': 'This page is being processed in the background. Results will be available for future queries.',
            'heuristic_score': 0,
            'final_score': 0,
            'quality_class': 'processing',
            'word_count': 0,
            'processing_time': time.time() - start_time
        }

    if queue_status == 'pending':
        # HTML is queued but not yet processing
        logger.info(f"[HTML-FASTLANE-{index}] HTML pending in background queue")
        return {
            'status': 'background_pending',
            'url': url,
            'index': index,
            'title': 'Queued for background processing...',
            'content': '',
            'message': 'This page is queued for background processing. Results will be available for future queries.',
            'heuristic_score': 0,
            'final_score': 0,
            'quality_class': 'pending',
            'word_count': 0,
            'processing_time': time.time() - start_time
        }

    # STEP 2: Try fast lane processing with SINGLE timeout wrapper (like PDF)
    logger.info(f"[HTML-FASTLANE-{index}] Attempting fast lane processing (timeout: {settings.background.fast_lane_timeout}s)")

    try:
        # Process with timeout - SINGLE WRAPPER, NO INTERNAL CHECKS
        result = process_html_with_timeout(
            url=url,
            index=index,
            progress_callback=progress_callback,
            timeout=settings.background.fast_lane_timeout,
            settings=settings
        )

        elapsed = time.time() - start_time
        logger.info(f"[HTML-FASTLANE-{index}] ✅ Fast lane success in {elapsed:.2f}s")

        result['fast_lane_success'] = True
        result['processing_time'] = elapsed
        return result

    except TimeoutException as e:
        # Timeout occurred - add to background queue
        elapsed = time.time() - start_time
        logger.warning(f"[HTML-FASTLANE-{index}] ⏱️  Fast lane timeout after {elapsed:.2f}s - adding to background queue")

        # Add to background queue
        metadata = {
            'index': index,
            'added_from': 'fast_lane_timeout',
            'timeout_duration': elapsed
        }

        queue_service.add_to_queue(
            url,
            doc_type='html',
            metadata=metadata,
            max_retries=settings.background.max_retry_attempts
        )

        return {
            'status': 'background_queued',
            'url': url,
            'index': index,
            'title': 'Processing in background (slow page)...',
            'content': '',
            'message': f'This page took too long to process (>{settings.background.fast_lane_timeout}s). It has been added to the background queue and will be available for future queries.',
            'heuristic_score': 0,
            'final_score': 0,
            'quality_class': 'queued',
            'word_count': 0,
            'processing_time': elapsed,
            'timeout_seconds': settings.background.fast_lane_timeout
        }

    except Exception as e:
        # Other error occurred
        elapsed = time.time() - start_time
        logger.error(f"[HTML-FASTLANE-{index}] ❌ Fast lane error: {e}")

        return {
            'status': 'error',
            'url': url,
            'index': index,
            'title': 'Processing Error',
            'content': '',
            'error': str(e),
            'heuristic_score': 0,
            'final_score': 0,
            'quality_class': 'error',
            'word_count': 0,
            'processing_time': elapsed
        }
