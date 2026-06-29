"""
Content Router & Orchestrator Service
- Checks cache
- Routes URLs to HTML or PDF pipelines
- TRUE PARALLEL execution with ProcessPoolExecutor
- No bottlenecks, no waiting!
- Separate PDF download and processing steps
- Fast lane support for both PDF and HTML (with background queue fallback)
"""
import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable
from services.cache_service import CacheService
from services.html_fast_lane_service import process_html_fast_lane
from services.pdf_fast_lane_service import process_pdf_fast_lane
from urllib.parse import urlparse
import multiprocessing
import time
import atexit

# Global persistent executor pools (initialized once, reused across all requests)
# This eliminates 2-3 second ProcessPoolExecutor startup overhead on every request
_HTML_EXECUTOR = None
_PDF_EXECUTOR = None
_EXECUTOR_LOCK = multiprocessing.Lock()

def _get_html_executor(max_workers: int = 10) -> ThreadPoolExecutor:
    """Get or create persistent HTML ThreadPoolExecutor"""
    global _HTML_EXECUTOR
    if _HTML_EXECUTOR is None:
        _HTML_EXECUTOR = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="HTMLWorker"
        )
        print(f"[ROUTER] Created persistent HTML ThreadPoolExecutor (max_workers={max_workers})")
    return _HTML_EXECUTOR

def _get_pdf_executor(max_workers: int = 61) -> ProcessPoolExecutor:
    """Get or create persistent PDF ProcessPoolExecutor (DYNAMIC: no cap, default=61)"""
    global _PDF_EXECUTOR
    if _PDF_EXECUTOR is None:
        _PDF_EXECUTOR = ProcessPoolExecutor(max_workers=max_workers)
        print(f"[ROUTER] Created persistent PDF ProcessPoolExecutor (max_workers={max_workers}, DYNAMIC)")
    return _PDF_EXECUTOR

def _cleanup_executors():
    """Cleanup executors on shutdown"""
    global _HTML_EXECUTOR, _PDF_EXECUTOR
    if _HTML_EXECUTOR:
        _HTML_EXECUTOR.shutdown(wait=True)
        print("[ROUTER] HTML ThreadPoolExecutor shut down")
    if _PDF_EXECUTOR:
        _PDF_EXECUTOR.shutdown(wait=True)
        print("[ROUTER] PDF ProcessPoolExecutor shut down")

# Register cleanup on program exit
atexit.register(_cleanup_executors)


class ContentRouter:
    """
    Orchestrates content analysis with true parallelism
    - Cache checking
    - Route to HTML or PDF pipelines
    - Process/Thread pool management
    """

    def __init__(
        self,
        max_workers: int = 10,
        use_processes: bool = False
    ):
        """
        Args:
            max_workers: Max parallel workers (threads or processes)
            use_processes: Use separate executors (ThreadPool for HTML, ProcessPool for PDF)
        """
        self.max_workers = max_workers
        self.cache = CacheService()

        # Use PERSISTENT GLOBAL executors for HTML vs PDF for optimal performance
        if use_processes:
            # Reuse global persistent executors (eliminates 2-3s startup overhead)
            self.html_executor = _get_html_executor(max_workers)
            self.pdf_executor = _get_pdf_executor(max_workers)
            self.executor = None  # Not used when use_processes=True
        else:
            # Single ThreadPool for both (backward compatibility)
            self.executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="ContentWorker"
            )
            self.html_executor = None
            self.pdf_executor = None

    def check_cache(self, url: str) -> Optional[Dict]:
        """
        Check if URL is cached (error/filtered within 15 days)

        Returns:
            Cached result dict or None
        """
        return self.cache.check_url_cache_status(url, error_ttl_days=15, filtered_ttl_days=15)

    def classify_url(self, url: str) -> str:
        """
        Classify URL as 'pdf' or 'html'
        Checks both URL extension and common PDF path patterns
        """
        url_lower = url.lower()

        # Direct .pdf extension
        if url_lower.endswith('.pdf'):
            return 'pdf'

        # Common PDF URL patterns (path ends with /pdf)
        # Examples: /articles/123/pdf, /papers/abc/pdf, /download/pdf
        if '/pdf' in url_lower:
            path_parts = url_lower.split('/')
            if path_parts and path_parts[-1] == 'pdf':
                return 'pdf'

        # Default to HTML
        return 'html'

    def route_urls(
        self,
        urls: List[str],
        progress_callback: Optional[Callable] = None,
        cache_enabled: bool = True,
        revalidation_threshold_days: int = 15,
        error_cache_days: int = 15,
        filtered_cache_days: int = 15,
        html_timeout: int = 10,
        html_quality_threshold: int = 40,
        max_retry_attempts: int = 2,
        retry_delay: int = 2,
        staleness_schedule: Optional[Dict] = None,
        # New parameters from Settings page
        pdf_timeout: int = 30,
        url_timeout: int = 10,
        max_download_workers: int = 5,
        rate_limit_per_domain: int = 4,
        rate_limit_delay: float = 0.1
    ) -> Dict:
        """
        Route URLs to appropriate pipelines and process in TRUE PARALLEL

        Args:
            urls: List of URLs to process
            progress_callback: Optional callback(url_idx, stage, percent)
            cache_enabled: Enable HTML cache (default: True)
            revalidation_threshold_days: Days before revalidation (default: 15)
            error_cache_days: Days to remember failed URLs (default: 15)
            filtered_cache_days: Days to remember filtered URLs (default: 15)
            html_timeout: HTML download timeout in seconds (default: 10)
            html_quality_threshold: Minimum quality score for HTML (default: 40)
            max_retry_attempts: Maximum retry attempts (default: 2)
            retry_delay: Delay between retries in seconds (default: 2)
            staleness_schedule: Dict of content type staleness days
            pdf_timeout: PDF download timeout in seconds (default: 30)
            url_timeout: General URL timeout in seconds (default: 10)
            max_download_workers: Maximum concurrent PDF downloads (default: 5)
            rate_limit_per_domain: Max concurrent requests per domain (default: 4)
            rate_limit_delay: Delay between requests to same domain (default: 0.1)

        Returns:
            Dict with results categorized by status
        """
        print(f"\n[ROUTER] Starting routing for {len(urls)} URLs")

        # Calculate required workers (one per URL for maximum parallelism)
        # Windows ThreadPoolExecutor has a hard limit of 61 workers
        required_workers = min(len(urls), 61)

        # Use dynamic executor if we need more workers than configured
        use_temp_executor = required_workers > self.max_workers

        if use_temp_executor:
            print(f"[ROUTER] Using DYNAMIC executor with {required_workers} workers (URLs={len(urls)}, max_workers={self.max_workers})")
        else:
            print(f"[ROUTER] Using PERSISTENT executor with {self.max_workers} workers (URLs={len(urls)})")

        # Step 1: Cache checking and classification
        tasks = []
        cached_results = []

        for idx, url in enumerate(urls):
            # Check cache first - Step 1: Check for cached errors/filtered (15 day TTL)
            cached = self.check_cache(url)
            if cached:
                print(f"[ROUTER] URL {idx+1} cached (error/filtered): {url[:60]}...")
                cached_results.append({
                    'index': idx,
                    'url': url,
                    'result': cached,
                    'cached': True
                })
                continue

            # Step 2: Check for successful cached results (content-type-based TTL)
            cache_decision = self.cache.get_reuse_decision(url, raw_html=None)
            if cache_decision.get('action') == 'reuse':
                cached_result = cache_decision.get('result', {})
                print(f"[ROUTER] URL {idx+1} cached (success): {url[:60]}... ({cache_decision.get('reason', 'fresh cache')})")
                cached_results.append({
                    'index': idx,
                    'url': url,
                    'result': cached_result,
                    'cached': True
                })
                continue

            # Classify and create task
            url_type = self.classify_url(url)
            print(f"[ROUTER] URL {idx+1} classified as {url_type}: {url}")

            tasks.append({
                'index': idx,
                'url': url,
                'type': url_type,
                'cached': False
            })

        print(f"[ROUTER] Cached: {len(cached_results)}, To process: {len(tasks)}")

        # Step 2: Create temporary executor if needed for dynamic scaling
        temp_html_executor = None
        temp_pdf_executor = None

        if use_temp_executor and len(tasks) > 0:
            # Create temporary executors sized to handle all tasks in parallel
            # Windows ThreadPoolExecutor has max 61 workers limit
            html_workers = min(len(tasks), 61)
            pdf_workers = len(tasks)  # DYNAMIC: Use as many workers as PDFs

            temp_html_executor = ThreadPoolExecutor(
                max_workers=html_workers,
                thread_name_prefix="HTML-Dynamic"
            )
            temp_pdf_executor = ProcessPoolExecutor(
                max_workers=pdf_workers
            )
            print(f"[ROUTER] Created temporary executors: HTML={html_workers} workers (requested={len(tasks)}), PDF={pdf_workers} workers")

        # Step 3: Submit ALL tasks to executor at once (TRUE PARALLEL)
        futures_map = {}

        for task in tasks:
            if task['type'] == 'pdf':
                # Import here to avoid circular imports
                from services.pdf_fast_lane_service import process_pdf_fast_lane

                # Use dynamic executor if available, otherwise persistent
                if temp_pdf_executor:
                    executor = temp_pdf_executor
                elif self.pdf_executor:
                    executor = self.pdf_executor
                else:
                    executor = self.executor

                print(f"[ROUTER] [START] SUBMITTING PDF #{task['index']} (FAST LANE): {task['url'][:60]}...")
                future = executor.submit(
                    process_pdf_fast_lane,
                    task['url'],
                    task['index'],
                    None,  # progress_callback - can't pickle with ProcessPool
                    None   # settings - will be loaded by fast lane service
                )
            else:  # html
                # Call process_html_complete directly - router already handles caching/parallelization
                from services.html_processing_service import process_html_complete

                # Use dynamic executor if available, otherwise persistent
                if temp_html_executor:
                    executor = temp_html_executor
                elif self.html_executor:
                    executor = self.html_executor
                else:
                    executor = self.executor

                print(f"[ROUTER] [START] SUBMITTING HTML #{task['index']} (DIRECT): {task['url'][:60]}...")
                future = executor.submit(
                    process_html_complete,
                    task['url'],
                    task['index'],
                    progress_callback,  # Can use callback with ThreadPool
                    None,  # settings - will be loaded
                    False  # fast_lane_mode - full NLP analysis
                )

            futures_map[future] = task

        print(f"[ROUTER] [OK] Submitted {len(futures_map)} tasks to executor at {time.strftime('%H:%M:%S')}")
        print(f"[ROUTER] [START] ALL {len(futures_map)} tasks running in PARALLEL now!")

        # Log executor configuration
        if temp_html_executor or temp_pdf_executor:
            html_workers = min(len(tasks), 61) if temp_html_executor else self.max_workers
            pdf_workers = len(tasks) if temp_pdf_executor else self.max_workers
            print(f"[ROUTER] [INFO] Using DYNAMIC executors: HTML ThreadPool ({html_workers} workers, Windows max=61), PDF ProcessPool ({pdf_workers} workers, DYNAMIC)")
        elif self.html_executor and self.pdf_executor:
            print(f"[ROUTER] [INFO] Using PERSISTENT DUAL executors: ThreadPool for HTML (max_workers={self.max_workers}), ProcessPool for PDF (max_workers={self.max_workers})")
        elif self.executor:
            executor_type = "ProcessPoolExecutor" if isinstance(self.executor, ProcessPoolExecutor) else "ThreadPoolExecutor"
            print(f"[ROUTER] [INFO] Using PERSISTENT {executor_type}: max_workers={self.max_workers}, parallel_mode={'PROCESSES (1 per file)' if isinstance(self.executor, ProcessPoolExecutor) else 'THREADS'}")

        # Step 3: Collect results as they complete (streaming)
        results = []
        completed = 0

        for future in as_completed(futures_map):
            task = futures_map[future]
            completed += 1

            try:
                result = future.result()
                results.append({
                    'index': task['index'],
                    'url': task['url'],
                    'result': result,
                    'cached': False
                })
                print(f"[ROUTER] Completed {completed}/{len(tasks)}: {task['url'][:60]}...")
            except Exception as e:
                print(f"[ROUTER] Error for {task['url']}: {e}")
                results.append({
                    'index': task['index'],
                    'url': task['url'],
                    'result': {
                        'status': 'error',
                        'error': str(e),
                        'url': task['url']
                    },
                    'cached': False
                })

        # Combine cached + processed results
        all_results = cached_results + results

        # Sort by original index
        all_results.sort(key=lambda x: x['index'])

        print(f"[ROUTER] All done! Total: {len(all_results)} results")

        # Cleanup temporary executors if used
        if temp_html_executor:
            temp_html_executor.shutdown(wait=False)
            print(f"[ROUTER] Cleaned up temporary HTML executor ({len(tasks)} workers)")
        if temp_pdf_executor:
            temp_pdf_executor.shutdown(wait=False)
            print(f"[ROUTER] Cleaned up temporary PDF executor")

        return {
            'total': len(urls),
            'cached': len(cached_results),
            'processed': len(results),
            'results': [r['result'] for r in all_results]
        }

    def process_pdfs(
        self,
        pdf_results: List[Dict],
        progress_callback: Optional[Callable] = None,
        enable_spacy: bool = False,
        spacy_require_gpu: bool = True,
        pdf_max_pages: Optional[int] = None,
        pdf_enable_tables: bool = True,
        pdf_enable_lists: bool = True
    ) -> Dict:
        """
        Process downloaded PDFs (extraction + NLP + scoring)

        Args:
            pdf_results: List of PDF download results (from route_urls)
            progress_callback: Optional callback(index, stage, percent)
            enable_spacy: Enable spaCy NLP enrichment
            spacy_require_gpu: Require GPU for spaCy
            pdf_max_pages: Max pages to process (None = all)
            pdf_enable_tables: Extract tables
            pdf_enable_lists: Extract lists

        Returns:
            Dict with processed results
        """
        from services.pdf_processor import process_pdf_parallel

        print(f"\n[PDF-ROUTER] Starting PDF processing for {len(pdf_results)} PDFs")
        print(f"[PDF-ROUTER] spaCy: {'ENABLED' if enable_spacy else 'DISABLED'}")
        if enable_spacy:
            print(f"[PDF-ROUTER] GPU requirement: {'YES' if spacy_require_gpu else 'NO'}")

        # Submit all PDF processing tasks
        futures_map = {}

        for pdf_result in pdf_results:
            # Extract filepath and URL from download result
            pdf_filepath = pdf_result.get('pdf_filepath')
            url = pdf_result.get('url')
            index = pdf_result.get('index', 0)

            if not pdf_filepath:
                print(f"[PDF-ROUTER] Skipping {url} - no filepath")
                continue

            print(f"[PDF-ROUTER] [START] SUBMITTING PDF processing #{index}: {pdf_filepath}")

            future = self.executor.submit(
                process_pdf_parallel,
                pdf_path=pdf_filepath,
                url=url,
                index=index,
                progress_callback=progress_callback,
                enable_spacy=enable_spacy,
                spacy_require_gpu=spacy_require_gpu
            )

            futures_map[future] = {
                'index': index,
                'url': url,
                'pdf_filepath': pdf_filepath
            }

        print(f"[PDF-ROUTER] [OK] Submitted {len(futures_map)} PDF processing tasks")
        print(f"[PDF-ROUTER] [START] ALL {len(futures_map)} tasks running in PARALLEL now!")

        # Collect results
        results = []
        completed = 0

        for future in as_completed(futures_map):
            task = futures_map[future]
            completed += 1

            try:
                result = future.result()
                results.append(result)
                status = result.get('status', 'unknown')
                score = result.get('quality_score', 0)
                print(f"[PDF-ROUTER] [OK] Completed {completed}/{len(futures_map)}: {status} (score={score})")
            except Exception as e:
                print(f"[PDF-ROUTER] [ERROR] Error processing {task['url']}: {e}")
                results.append({
                    'status': 'error',
                    'error': str(e),
                    'url': task['url'],
                    'index': task['index'],
                    'pdf_filepath': task['pdf_filepath']
                })

        # Sort by index
        results.sort(key=lambda x: x.get('index', 0))

        # Calculate stats
        successful = sum(1 for r in results if r.get('status') == 'success')
        filtered = sum(1 for r in results if r.get('status') == 'filtered')
        duplicates = sum(1 for r in results if r.get('status') == 'duplicate')
        errors = sum(1 for r in results if r.get('status') == 'error')

        print(f"[PDF-ROUTER] All done! Success: {successful}, Filtered: {filtered}, Duplicates: {duplicates}, Errors: {errors}")

        return {
            'total': len(pdf_results),
            'successful': successful,
            'filtered': filtered,
            'duplicates': duplicates,
            'errors': errors,
            'results': results
        }

    def shutdown(self):
        """
        Clean up executor(s) - non-blocking for fast response

        Note: Global persistent executors (html_executor, pdf_executor) are NOT shut down here.
        They stay alive for reuse across requests. Only non-persistent executors are shut down.
        """
        # Only shutdown non-persistent executor (backward compatibility mode)
        if self.executor:
            self.executor.shutdown(wait=False)
            print("[ROUTER] Executor shutdown initiated (non-blocking)")

        # Do NOT shutdown global persistent executors - they're reused across requests
        # They will be cleaned up on program exit via atexit.register(_cleanup_executors)


# Async wrapper for FastAPI streaming
async def route_urls_async(
    urls: List[str],
    max_workers: int = 10,
    progress_callback: Optional[Callable] = None
):
    """
    Async wrapper that yields results as they complete

    Yields:
        Result dicts as they finish
    """
    router = ContentRouter(max_workers=max_workers, use_processes=False)

    try:
        # Run router in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            router.route_urls,
            urls,
            progress_callback
        )

        return result
    finally:
        router.shutdown()
