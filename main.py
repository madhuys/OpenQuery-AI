"""
FastAPI Backend with TRUE PARALLEL Architecture
Clean separation: Serper → Router → Pipelines
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Literal, List
from typing import Dict
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import subprocess
import sys
import platform
import uuid

# Service imports - clean architecture
from services.search_factory import get_search_provider, search_and_extract
from services.serper_service import SerperClient
from services.router_service import ContentRouter
from services.cache_service import CacheService
from config.settings import AppSettings, SETTINGS_FILE

app = FastAPI(title="OpenQuery AI API", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
cache = CacheService()
serper_client = SerperClient()

# Global shared router for /api/analyze-url endpoint
# Reusing the same router prevents spawning new workers per request
# 61-worker pool (Windows ThreadPoolExecutor max) handles most batches
# Larger batches use temporary dynamic executors (also capped at 61 on Windows)
# This dramatically improves performance for auto-analysis (20+ parallel requests)
_global_router = None

def get_global_router() -> ContentRouter:
    """Get or create global shared ContentRouter instance"""
    global _global_router
    if _global_router is None:
        # Create router with optimal worker count for auto-analysis
        # 61 workers (Windows ThreadPoolExecutor max limit) handles most batches
        # For larger batches, router will create temporary dynamic executors
        _global_router = ContentRouter(max_workers=61, use_processes=True)
        print("[ROUTER] Created global shared router with 61 workers (Windows max)")
    return _global_router

# Load app settings
def get_app_settings() -> AppSettings:
    """Load current app settings from file"""
    return AppSettings.load(SETTINGS_FILE)


# Request models
class SearchRequest(BaseModel):
    q: str
    search_type: Optional[Literal["search", "news", "videos", "scholar"]] = "search"
    provider: Optional[str] = "serper"
    gl: Optional[str] = None
    hl: Optional[str] = None
    location: Optional[str] = None
    num: Optional[int] = 10
    page: Optional[int] = 1
    tbs: Optional[str] = None
    autocorrect: Optional[bool] = None
    nfpr: Optional[bool] = None
    safe: Optional[Literal["active", "off"]] = None
    # Fuzzy cache matching (session-only overrides from UI)
    disable_cache: Optional[bool] = False  # Fully disable cache for this request
    fuzzy_match_threshold: Optional[int] = None  # Override fuzzy threshold (50-100)
    enable_fuzzy_matching: Optional[bool] = None  # Override fuzzy matching enable/disable


class AnalyzeRequest(BaseModel):
    urls: List[str]
    timeout: Optional[int] = 10
    max_workers: Optional[int] = 10
    query_id: Optional[int] = None  # If provided, cache analysis results for this query
    # Additional settings from UI/Settings page
    max_download_workers: Optional[int] = None
    html_timeout: Optional[int] = None
    pdf_timeout: Optional[int] = None
    url_timeout: Optional[int] = None
    max_retry_attempts: Optional[int] = None
    retry_delay: Optional[int] = None
    rate_limit_per_domain: Optional[int] = None
    rate_limit_delay: Optional[float] = None


class ProcessPDFsRequest(BaseModel):
    pdf_results: List[Dict]  # List of PDF download results
    enable_spacy: Optional[bool] = False
    spacy_require_gpu: Optional[bool] = True
    pdf_max_pages: Optional[int] = None
    pdf_enable_tables: Optional[bool] = True
    pdf_enable_lists: Optional[bool] = True


class AnalyzeURLRequest(BaseModel):
    """Single URL analysis request for Search V2 Part 2"""
    url: str
    index: Optional[int] = 0


class SemanticSearchRequest(BaseModel):
    """Semantic search request for Search V3"""
    query: str
    urls: List[str]  # Filter to these URLs only
    limit: Optional[int] = 20
    threshold: Optional[float] = 0.7


class LiveSearchRequest(BaseModel):
    """Live Search API Request with semantic search capabilities"""
    query: str
    search_type: Optional[Literal["search", "news", "videos", "scholar"]] = "search"
    provider: Optional[str] = "serper"
    enable_document_search: Optional[bool] = False
    num_results: Optional[int] = 20
    country: Optional[str] = None  # gl parameter
    language: Optional[str] = "en"  # hl parameter
    location: Optional[str] = None
    time_filter: Optional[str] = None  # tbs parameter
    date_range: Optional[Dict[str, str]] = None  # {start: "YYYY-MM-DD", end: "YYYY-MM-DD"}
    safe_search: Optional[Literal["active", "off"]] = "off"
    autocorrect: Optional[bool] = True
    sources: Optional[Dict[str, bool]] = {"videos": False, "scholar": False}
    cache: Optional[Dict[str, bool]] = {"bypass": False}

    # Semantic search settings
    similarity_threshold: Optional[float] = 0.5
    max_search_results: Optional[int] = 20


class LiveSearchResult(BaseModel):
    """Individual search result with semantic matching"""
    id: str  # canonical URL or UUID
    title: str
    url: str
    author: str = ""
    text: str = ""  # backward compatibility
    texturl: str = ""  # URL to fetch full text
    highlights: List[str] = []  # matched chunks
    highlightScores: List[float] = []  # similarity scores for each highlight
    image: str = ""
    result_type: str = "html"  # 'html' or 'pdf'


class LiveSearchResponse(BaseModel):
    """Live Search API Response"""
    success: bool
    data: Dict[str, List[LiveSearchResult]]


class MatchHighlightRequest(BaseModel):
    """Request to match and highlight a chunk in source document"""
    url: str  # Document URL (texturl from live-search)
    highlight_text: str  # The text to highlight
    doc_type: Optional[str] = "html"  # 'html' or 'pdf'


class MatchHighlightResponse(BaseModel):
    """Response with full text and highlighted match"""
    success: bool
    url: str
    full_text: str  # Full document with <highlight>...</highlight> tags
    match_found: bool
    match_type: Optional[str] = None  # 'exact' or 'fuzzy'
    match_position: Optional[Dict[str, int]] = None  # {start: int, end: int}


@app.get("/")
def root():
    return {
        "app": "OpenQuery AI API",
        "version": "2.0.0",
        "architecture": "Services-based with TRUE PARALLEL execution",
        "endpoints": ["/query", "/analyze-stream", "/live-search", "/match-highlight"],
        "docs": "/docs"
    }


@app.post("/query")
async def unified_search(request: SearchRequest):
    """
    Serper API → Extract URLs
    With intelligent caching to avoid redundant API calls
    """
    try:
        # Load current app settings
        app_settings = get_app_settings()

        # Build settings dict for cache lookup
        settings = {
            "search_type": request.search_type or "search",
            "gl": request.gl,
            "hl": request.hl,
            "location": request.location,
            "num": request.num,
            "page": request.page,
            "tbs": request.tbs,
            "autocorrect": request.autocorrect,
            "nfpr": request.nfpr,
            "safe": request.safe
        }

        # Remove None values for cleaner cache matching
        settings = {k: v for k, v in settings.items() if v is not None}

        # Check cache first (only if enabled and not disabled by request)
        cached = None
        if app_settings.cache.enable_serper_cache and not request.disable_cache:
            # Get freshness TTL based on search type
            search_type = request.search_type or "search"
            freshness_by_type = app_settings.cache.serper_freshness_by_type
            max_age_hours = freshness_by_type.get(search_type, 24)

            # Use request-specific fuzzy matching settings if provided, otherwise use config
            cached = cache.get_cached_search(
                request.q,
                settings,
                max_age_hours=max_age_hours,
                fuzzy_match_threshold=request.fuzzy_match_threshold,
                enable_fuzzy_matching=request.enable_fuzzy_matching
            )
        else:
            print(f"[SERPER] ⚠️  Serper cache DISABLED - skipping cache check")

        if cached:
            # Extract cache match information
            cache_match_info = {
                "match_type": cached.get("match_type"),
                "matched_query": cached.get("matched_query"),
                "similarity_score": cached.get("similarity_score"),
                "original_query": cached.get("original_query"),
                "normalized_query": cached.get("normalized_query")
            }

            # Check if we have complete analysis results
            if 'analysis_results' in cached:
                print(f"[SERPER] ✅✅ FULL CACHE HIT (query + analysis) for: '{request.q}'")
                print(f"[SERPER] Match type: {cache_match_info['match_type']}, similarity: {cache_match_info['similarity_score']}%")
                print(f"[SERPER] Returning {len(cached['analysis_results'])} analyzed results instantly")
                return {
                    "status": "success",
                    "search_type": request.search_type,
                    "cached": True,
                    "cached_at": cached['cached_at'],
                    "analysis_cached": True,
                    "analysis_completed_at": cached['analysis_completed_at'],
                    "query_id": cached['query_id'],
                    "analysis_results": cached['analysis_results'],
                    "total_results": len(cached['analysis_results']),
                    "serper_api_time": 0.0,  # Cached, no API call
                    "cache_match_info": cache_match_info  # Include match information
                }
            else:
                # Serper cached but analysis not done yet
                print(f"[SERPER] ✅ CACHE HIT for query: '{request.q}' (cached_at: {cached['cached_at']})")
                print(f"[SERPER] Match type: {cache_match_info['match_type']}, similarity: {cache_match_info['similarity_score']}%")
                print(f"[SERPER] ⚠️  Analysis not cached - will need to process")
                urls = cached['results']
                return {
                    "status": "success",
                    "search_type": request.search_type,
                    "total_results": len(urls),
                    "urls": [item['url'] for item in urls],
                    "url_details": urls,
                    "cached": True,
                    "cached_at": cached['cached_at'],
                    "analysis_cached": False,
                    "query_id": cached['query_id'],
                    "serper_api_time": 0.0,  # Cached, no API call
                    "cache_match_info": cache_match_info  # Include match information
                }

        print(f"[SEARCH_PROVIDER] 🆕 NO CACHE - calling {request.provider or 'serper'} API for: '{request.q}'")

        # Measure search API call time
        import time
        serper_start = time.time()

        # Call search provider API
        provider_client = get_search_provider(request.provider)
        results = provider_client.search(
            query=request.q,
            search_type=request.search_type or "search",
            gl=request.gl,
            hl=request.hl,
            location=request.location,
            num=request.num or 10,
            page=request.page or 1,
            tbs=request.tbs,
            autocorrect=request.autocorrect,
            nfpr=request.nfpr,
            safe=request.safe
        )

        serper_elapsed = time.time() - serper_start
        print(f"[SEARCH_PROVIDER] ⏱️  API call took {serper_elapsed:.3f}s")

        # Extract URLs
        urls = provider_client.extract_urls(results, request.search_type or "search")

        # Cache the search for future use
        query_id = cache.start_search(request.q, settings)
        cache.record_results_batch(query_id, urls, engine=request.provider or "serper")
        print(f"[SEARCH_PROVIDER] 💾 Cached query_id={query_id} with {len(urls)} results")

        return {
            "status": "success",
            "search_type": request.search_type,
            "total_results": len(urls),
            "urls": [item['url'] for item in urls],
            "url_details": urls,
            "raw_results": results,
            "cached": False,
            "query_id": query_id,
            "serper_api_time": serper_elapsed  # Add timing
        }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n❌ ERROR in /query endpoint:")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{error_details}")


@app.post("/analyze-stream")
async def analyze_urls_stream(request: AnalyzeRequest):
    """
    Content Router with TRUE PARALLEL execution
    Uses ThreadPoolExecutor - ALL files process simultaneously!
    """
    # Generate unique request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    print(f"\n[REQUEST-{request_id}] 📥 New analyze request: {len(request.urls)} URLs, max_workers={request.max_workers}")

    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    # Allow up to 50 URLs (to support document search which can add extra results)
    if len(request.urls) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 URLs allowed")

    async def generate():
        try:
            # Load app settings
            app_settings = get_app_settings()

            # Use max_workers from request, or fall back to settings, or default to 10
            # Cap at 16 for ProcessPoolExecutor (1 process per file)
            default_max_workers = app_settings.analysis.max_workers
            max_workers = min(request.max_workers or default_max_workers, len(request.urls), 32)

            print(f"\n[REQUEST-{request_id}][MAIN] 🎯 Creating ContentRouter with max_workers={max_workers} for {len(request.urls)} URLs")
            print(f"[REQUEST-{request_id}][MAIN] Settings: max_workers={default_max_workers}, timeout={app_settings.analysis.html_timeout}s, quality_threshold={app_settings.analysis.html_quality_threshold}")

            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'total_urls': len(request.urls), 'actual_workers_used': max_workers, 'max_workers_requested': request.max_workers or default_max_workers})}\n\n"

            # Progress tracking
            progress_events = asyncio.Queue()

            # Capture event loop BEFORE creating callback (important for thread-safety)
            loop = asyncio.get_event_loop()

            def progress_callback(index: int, stage: str, percent: int):
                """Thread-safe progress callback"""
                try:
                    # Put in queue (will be consumed by async loop)
                    # Use captured 'loop' variable instead of asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        progress_events.put({
                            'type': 'progress',
                            'index': index,
                            'stage': stage,
                            'percent': percent
                        }),
                        loop  # Use captured loop from outer scope
                    )
                except Exception as e:
                    print(f"[PROGRESS] ⚠️ Callback error: {e}")

            # Create router (app_settings already loaded above)
            # use_processes=True: Use ProcessPoolExecutor for true parallel processing (1 process per file)
            router = ContentRouter(max_workers=max_workers, use_processes=True)

            # Run routing in thread pool (non-blocking)
            executor = ThreadPoolExecutor(max_workers=app_settings.analysis.router_max_workers, thread_name_prefix="RouterThread")

            # Submit routing task with HTML cache and analysis settings
            # Note: progress_callback is None for ProcessPoolExecutor (can't pickle closures)
            # Use settings from request if provided, otherwise fall back to app_settings
            future = executor.submit(
                router.route_urls,
                request.urls,
                None,  # progress_callback - can't pickle with ProcessPoolExecutor
                cache_enabled=app_settings.cache.enable_html_cache,
                revalidation_threshold_days=app_settings.cache.revalidation_threshold_days,
                error_cache_days=app_settings.cache.error_cache_days,
                filtered_cache_days=app_settings.cache.filtered_cache_days,
                html_timeout=request.html_timeout or app_settings.analysis.html_timeout,
                html_quality_threshold=app_settings.analysis.html_quality_threshold,
                max_retry_attempts=request.max_retry_attempts or app_settings.analysis.max_retry_attempts,
                retry_delay=request.retry_delay or app_settings.analysis.retry_delay,
                staleness_schedule=app_settings.cache.html_staleness_by_type,
                # New settings from request
                pdf_timeout=request.pdf_timeout or app_settings.analysis.pdf_timeout,
                url_timeout=request.url_timeout or app_settings.analysis.url_timeout,
                max_download_workers=request.max_download_workers or app_settings.analysis.max_download_workers,
                rate_limit_per_domain=request.rate_limit_per_domain or app_settings.analysis.rate_limit_per_domain,
                rate_limit_delay=request.rate_limit_delay or app_settings.analysis.rate_limit_delay
            )

            # Stream progress events and results
            completed_indices = set()

            while not future.done() or not progress_events.empty():
                # Check for progress events
                try:
                    event = await asyncio.wait_for(progress_events.get(), timeout=0.1)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    pass

                # Small sleep to not hammer CPU
                await asyncio.sleep(0.05)

            # Get final results
            result = future.result()
            print(f"[REQUEST-{request_id}] 📊 Got {len(result['results'])} results from router")

            # Debug: Print result statuses
            for idx, res in enumerate(result['results']):
                status = res.get('status', 'unknown')
                url_snippet = res.get('url', 'no-url')[:60]
                print(f"[REQUEST-{request_id}]   Result {idx}: {status} - {url_snippet}")

            # Send results
            for idx, res in enumerate(result['results']):
                try:
                    # Remove non-serializable fields before sending
                    res_copy = res.copy()

                    # Remove large/complex fields that frontend doesn't need
                    if 'full_extraction' in res_copy:
                        del res_copy['full_extraction']
                    if 'document' in res_copy:
                        del res_copy['document']
                    if 'pages' in res_copy:
                        del res_copy['pages']
                    if 'chunks' in res_copy:
                        del res_copy['chunks']

                    result_event = {'type': 'result', 'index': idx, 'data': res_copy}
                    json_str = json.dumps(result_event)
                    yield f"data: {json_str}\n\n"
                    print(f"[REQUEST-{request_id}] 📤 Sent result {idx+1}/{len(result['results'])}: {res.get('status', 'unknown')}")
                except Exception as e:
                    print(f"[REQUEST-{request_id}] ❌ Failed to send result {idx}: {e}")
                    # Send minimal error result
                    error_result = {
                        'type': 'result',
                        'index': idx,
                        'data': {
                            'status': 'error',
                            'error': f'Serialization error: {str(e)}',
                            'url': res.get('url', 'unknown')
                        }
                    }
                    yield f"data: {json.dumps(error_result)}\n\n"
            print(f"[REQUEST-{request_id}] ✅ Sent all {len(result['results'])} result events")

            # Calculate success/filtered/failed counts
            successful = sum(1 for r in result['results'] if r.get('status') == 'success')
            filtered = sum(1 for r in result['results'] if r.get('status') == 'filtered')
            failed = sum(1 for r in result['results'] if r.get('status') in ['error', 'failed'])
            print(f"[REQUEST-{request_id}] 📈 Counts: {successful} success, {filtered} filtered, {failed} failed")

            # Save analysis results to cache if query_id provided
            if request.query_id:
                try:
                    cache.save_analysis_results(request.query_id, result['results'])
                    print(f"[REQUEST-{request_id}] 💾 Saved analysis results to cache (query_id={request.query_id})")
                except Exception as e:
                    print(f"[REQUEST-{request_id}] ⚠️  Failed to cache analysis results: {e}")
            else:
                print(f"[REQUEST-{request_id}] ⚠️  No query_id provided - skipping analysis cache")

            # Send completion (matching what app.py expects)
            print(f"[REQUEST-{request_id}] 🏁 Sending completion event...")
            yield f"data: {json.dumps({'type': 'complete', 'total': result['total'], 'successful': successful, 'filtered': filtered, 'failed': failed})}\n\n"
            print(f"[REQUEST-{request_id}] ✅ Completion event sent")

            # Cleanup
            router.shutdown()
            executor.shutdown(wait=False)
            print(f"\n[REQUEST-{request_id}] ✅ Request complete and cleaned up")

        except Exception as e:
            print(f"\n[REQUEST-{request_id}] ❌ Request failed: {str(e)}")
            error_msg = {
                'type': 'error',
                'error': str(e)
            }
            yield f"data: {json.dumps(error_msg)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/live-search")
async def live_search(request: LiveSearchRequest):
    """
    Live Search with Semantic Matching

    Complete end-to-end search with:
    1. Serper API search (with optional document search)
    2. Content extraction & processing
    3. Semantic embedding generation
    4. Similarity matching against query
    5. Structured results with highlights

    Returns results in standardized format with matched chunks and scores.
    """
    request_id = str(uuid.uuid4())[:8]
    print(f"\n[LIVE-SEARCH-{request_id}] 📥 New live search request: '{request.query}'")
    print(f"[LIVE-SEARCH-{request_id}] Settings: doc_search={request.enable_document_search}, num={request.num_results}, threshold={request.similarity_threshold}")

    try:
        from services.semantic_search_service import SemanticSearchService
        import numpy as np

        # Load app settings
        app_settings = get_app_settings()

        # Initialize semantic search service
        search_service = SemanticSearchService(app_settings)

        # Step 1: Search via Serper API (multi-page + document search)
        print(f"[LIVE-SEARCH-{request_id}] 🔍 Step 1: Calling Serper API...")

        # Calculate pages needed (Serper returns 10 results per page)
        pages_needed = max(1, (request.num_results + 9) // 10)
        print(f"[LIVE-SEARCH-{request_id}] Will fetch {pages_needed} page(s) for {request.num_results} results")

        # Build search requests for parallel execution
        search_tasks = []

        # Main search - multiple pages
        for page_num in range(1, pages_needed + 1):
            main_search = SearchRequest(
                q=request.query,
                search_type=request.search_type,
                provider=request.provider or "serper",
                gl=request.country,
                hl=request.language,
                location=request.location,
                num=10,  # Limit per page
                page=page_num,
                tbs=request.time_filter,
                autocorrect=request.autocorrect,
                safe=request.safe_search,
                disable_cache=request.cache.get("bypass", False) if request.cache else False
            )
            search_tasks.append(("main", page_num, main_search))
            print(f"[LIVE-SEARCH-{request_id}]   Created main search task: page {page_num}")

        # Document search if enabled (page 1 only, 10 results)
        if request.enable_document_search:
            print(f"[LIVE-SEARCH-{request_id}]   Document search ENABLED - appending ' pdf' to query")
            doc_search = SearchRequest(
                q=f"{request.query} pdf",
                search_type="search",
                provider=request.provider or "serper",
                gl=request.country,
                hl=request.language,
                location=request.location,
                num=10,  # Fixed 10 for document search
                page=1,
                tbs=request.time_filter,
                autocorrect=request.autocorrect,
                safe=request.safe_search,
                disable_cache=request.cache.get("bypass", False) if request.cache else False
            )
            search_tasks.append(("document", 1, doc_search))
            print(f"[LIVE-SEARCH-{request_id}]   Created document search task with query: '{request.query} pdf'")
        else:
            print(f"[LIVE-SEARCH-{request_id}]   Document search DISABLED")

        # Execute searches in parallel
        import asyncio
        async def execute_search(task_name, page_num, search_req):
            result = await unified_search(search_req)
            urls = result.get("urls", [])
            print(f"[LIVE-SEARCH-{request_id}]   {task_name} page {page_num}: {len(urls)} URLs")
            return urls

        # Run all searches in parallel
        print(f"[LIVE-SEARCH-{request_id}] Executing {len(search_tasks)} search tasks in parallel...")
        search_results = await asyncio.gather(*[
            execute_search(task_name, page_num, search_req)
            for task_name, page_num, search_req in search_tasks
        ])

        # Flatten and deduplicate URLs
        all_urls = []
        for urls in search_results:
            all_urls.extend(urls)

        print(f"[LIVE-SEARCH-{request_id}] Total URLs collected (before dedup): {len(all_urls)}")

        # Deduplicate while preserving order
        unique_urls = list(dict.fromkeys(all_urls))

        print(f"[LIVE-SEARCH-{request_id}] Unique URLs after dedup: {len(unique_urls)}")

        # Limit to requested number
        unique_urls = unique_urls[:request.num_results]

        print(f"[LIVE-SEARCH-{request_id}] URLs after limit: {len(unique_urls)} (requested: {request.num_results})")

        # Step 2: Analyze & Extract Content
        print(f"[LIVE-SEARCH-{request_id}] 📄 Step 2: Analyzing {len(unique_urls)} URLs...")

        analyze_req = AnalyzeRequest(
            urls=unique_urls,
            timeout=app_settings.analysis.html_timeout,
            max_workers=app_settings.analysis.max_workers,
            max_download_workers=app_settings.analysis.max_download_workers,
            html_timeout=app_settings.analysis.html_timeout,
            pdf_timeout=app_settings.analysis.pdf_timeout
        )

        # Use the existing analyze endpoint logic (synchronous for now)
        router = ContentRouter(max_workers=app_settings.analysis.max_workers, use_processes=False)

        analysis_result = router.route_urls(
            unique_urls,
            None,  # no progress callback
            cache_enabled=app_settings.cache.enable_html_cache,
            html_timeout=app_settings.analysis.html_timeout,
            html_quality_threshold=app_settings.analysis.html_quality_threshold,
            max_retry_attempts=app_settings.analysis.max_retry_attempts,
            retry_delay=app_settings.analysis.retry_delay,
            staleness_schedule=app_settings.cache.html_staleness_by_type
        )

        successful_results = [r for r in analysis_result['results'] if r.get('status') == 'success']
        print(f"[LIVE-SEARCH-{request_id}] Successfully extracted: {len(successful_results)} documents")

        # Collect URLs for filtering
        successful_urls = [r.get('url') for r in successful_results]

        # Step 3: Semantic Search
        print(f"[LIVE-SEARCH-{request_id}] 🧠 Step 3: Performing semantic search...")

        # Use the semantic search service
        # Request more chunks than needed since we'll group by URL later
        # Each URL might have multiple matching chunks, so request 3x the document limit
        semantic_limit = (request.max_search_results or 20) * 3

        top_matches = search_service.search(
            query=request.query,
            limit=semantic_limit,
            score_threshold=request.similarity_threshold,
            url_filter=successful_urls  # Only search in successfully extracted URLs
        )

        print(f"[LIVE-SEARCH-{request_id}] Found {len(top_matches)} semantic matches (requested limit: {semantic_limit})")

        # Enrich matches with metadata from analysis results
        url_metadata = {r['url']: r for r in successful_results}
        for match in top_matches:
            url = match['url']
            if url in url_metadata:
                match['title'] = url_metadata[url].get('title', '')
                match['author'] = url_metadata[url].get('author', '')

        # Step 4: Format Response
        print(f"[LIVE-SEARCH-{request_id}] 📦 Step 4: Formatting response...")

        # Group highlights by URL
        results_by_url = {}
        for match in top_matches:
            url = match['url']
            if url not in results_by_url:
                # Determine result_type from URL or doc_type
                doc_type = match.get('doc_type', 'html')
                if doc_type == 'pdf' or url.lower().endswith('.pdf'):
                    result_type = 'pdf'
                else:
                    result_type = 'html'

                results_by_url[url] = {
                    'id': url,
                    'title': match.get('title', ''),
                    'url': url,
                    'author': match.get('author', ''),
                    'text': '',  # backward compatibility
                    'texturl': url,  # Database URL - same as url since it's the key to fetch from DB
                    'highlights': [],
                    'highlightScores': [],
                    'image': '',
                    'result_type': result_type
                }

            results_by_url[url]['highlights'].append(match['chunk_text'])
            results_by_url[url]['highlightScores'].append(match['similarity_score'])

        # Convert to list
        results = list(results_by_url.values())

        print(f"[LIVE-SEARCH-{request_id}] ✅ Returning {len(results)} results")

        # Cleanup
        router.shutdown()

        return {
            "success": True,
            "data": {
                "results": results
            }
        }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n[LIVE-SEARCH-{request_id}] ❌ Error: {str(e)}")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{error_details}")


@app.post("/match-highlight")
async def match_highlight(request: MatchHighlightRequest):
    """
    Match and Highlight Text in Source Document

    Takes a highlight text and URL, finds the exact match in the source document,
    and returns the full document text with the matched section wrapped in
    <highlight>...</highlight> tags.

    Use this endpoint to:
    1. Get the full document context for a search result highlight
    2. Display the matched chunk with surrounding text
    3. Show users where their search terms appear in the document

    Args:
        request: MatchHighlightRequest with url, highlight_text, and doc_type

    Returns:
        MatchHighlightResponse with full_text containing <highlight> tags
    """
    request_id = str(uuid.uuid4())[:8]
    print(f"\n[MATCH-HIGHLIGHT-{request_id}] 📥 New match request")
    print(f"[MATCH-HIGHLIGHT-{request_id}] URL: {request.url[:80]}...")
    print(f"[MATCH-HIGHLIGHT-{request_id}] Highlight: {request.highlight_text[:100]}...")

    try:
        from services.chunk_matcher_service import ChunkMatcherService

        # Initialize matcher service
        matcher = ChunkMatcherService()

        # Perform matching
        print(f"[MATCH-HIGHLIGHT-{request_id}] 🔍 Matching chunk to source...")
        match_result = matcher.match_chunk_to_source(
            url=request.url,
            chunk_text=request.highlight_text,
            doc_type=request.doc_type
        )

        # Check if match was found
        if not match_result:
            print(f"[MATCH-HIGHLIGHT-{request_id}] ❌ No match found")
            return {
                "success": False,
                "url": request.url,
                "full_text": "",
                "match_found": False,
                "match_type": None,
                "match_position": None
            }

        # Check for errors
        if 'error' in match_result:
            print(f"[MATCH-HIGHLIGHT-{request_id}] ❌ Error: {match_result['error']}")
            return {
                "success": False,
                "url": request.url,
                "full_text": "",
                "match_found": False,
                "match_type": None,
                "match_position": None
            }

        # Extract match information
        full_text = match_result.get('full_text', '')
        start_char = match_result.get('start_char', 0)
        end_char = match_result.get('end_char', 0)
        match_type = match_result.get('match_type', 'unknown')

        print(f"[MATCH-HIGHLIGHT-{request_id}] ✅ Match found: {match_type}, position {start_char}-{end_char}")

        # Split text and insert highlight tags
        text_before = full_text[:start_char]
        text_match = full_text[start_char:end_char]
        text_after = full_text[end_char:]

        # Construct full text with highlight tags
        highlighted_full_text = f"{text_before}<highlight>{text_match}</highlight>{text_after}"

        print(f"[MATCH-HIGHLIGHT-{request_id}] 📦 Returning highlighted text ({len(highlighted_full_text)} chars)")

        return {
            "success": True,
            "url": request.url,
            "full_text": highlighted_full_text,
            "match_found": True,
            "match_type": match_type,
            "match_position": {
                "start": start_char,
                "end": end_char
            }
        }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n[MATCH-HIGHLIGHT-{request_id}] ❌ Error: {str(e)}")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{error_details}")


@app.post("/process-pdfs")
async def process_pdfs(request: ProcessPDFsRequest):
    """
    Process downloaded PDFs (extraction + NLP + scoring)

    This endpoint processes PDFs that have already been downloaded.
    Use /analyze-stream to download PDFs first, then call this to process them.

    Args:
        request: ProcessPDFsRequest with pdf_results and settings

    Returns:
        JSON with processed results
    """
    # Generate unique request ID
    request_id = str(uuid.uuid4())[:8]
    print(f"\n[PDF-REQUEST-{request_id}] 📥 New PDF processing request: {len(request.pdf_results)} PDFs")

    if not request.pdf_results:
        raise HTTPException(status_code=400, detail="No PDF results provided")

    if len(request.pdf_results) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 PDFs allowed per request")

    try:
        # Load app settings
        app_settings = get_app_settings()

        # Use settings or request parameters
        enable_spacy = request.enable_spacy if request.enable_spacy is not None else app_settings.pdf.spacy_enabled
        spacy_require_gpu = request.spacy_require_gpu if request.spacy_require_gpu is not None else app_settings.pdf.spacy_require_gpu
        pdf_max_pages = request.pdf_max_pages if request.pdf_max_pages is not None else app_settings.pdf.pdf_max_pages
        pdf_enable_tables = request.pdf_enable_tables if request.pdf_enable_tables is not None else app_settings.pdf.pdf_enable_tables
        pdf_enable_lists = request.pdf_enable_lists if request.pdf_enable_lists is not None else app_settings.pdf.pdf_enable_lists

        print(f"[PDF-REQUEST-{request_id}] Settings: spacy={enable_spacy}, gpu={spacy_require_gpu}, max_pages={pdf_max_pages}")

        # Create router - DYNAMIC: Use as many workers as PDFs
        max_workers = len(request.pdf_results)
        router = ContentRouter(max_workers=max_workers, use_processes=False)

        # Process PDFs
        result = router.process_pdfs(
            pdf_results=request.pdf_results,
            enable_spacy=enable_spacy,
            spacy_require_gpu=spacy_require_gpu,
            pdf_max_pages=pdf_max_pages,
            pdf_enable_tables=pdf_enable_tables,
            pdf_enable_lists=pdf_enable_lists
        )

        # Cleanup
        router.shutdown()

        print(f"[PDF-REQUEST-{request_id}] ✅ Processing complete: {result['successful']} successful, {result['filtered']} filtered, {result['duplicates']} duplicates, {result['errors']} errors")

        return {
            "status": "success",
            "request_id": request_id,
            "total": result['total'],
            "successful": result['successful'],
            "filtered": result['filtered'],
            "duplicates": result['duplicates'],
            "errors": result['errors'],
            "results": result['results']
        }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"\n[PDF-REQUEST-{request_id}] ❌ Processing failed: {str(e)}")
        print(error_details)
        raise HTTPException(status_code=500, detail=f"{str(e)}\n\n{error_details}")


def kill_process_on_port(port: int = 8000):
    """Kill any process using the specified port"""
    is_windows = platform.system() == "Windows"

    try:
        if is_windows:
            # Find process using port
            result = subprocess.run(
                f'netstat -ano | findstr :{port}',
                shell=True,
                capture_output=True,
                text=True
            )

            if result.stdout:
                lines = result.stdout.strip().split('\n')
                pids = set()
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids.add(pid)

                for pid in pids:
                    print(f"🔪 Killing process {pid} on port {port}...")
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)

                if pids:
                    time.sleep(1)  # Wait for processes to terminate
                    print(f"✅ Port {port} cleared")
                    return True
        else:
            # Unix-like systems
            result = subprocess.run(
                f"lsof -ti:{port}",
                shell=True,
                capture_output=True,
                text=True
            )

            if result.stdout:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        print(f"🔪 Killing process {pid} on port {port}...")
                        subprocess.run(f"kill -9 {pid}", shell=True)

                if pids:
                    time.sleep(1)
                    print(f"✅ Port {port} cleared")
                    return True

    except Exception as e:
        print(f"⚠️  Could not check/kill port {port}: {e}")

    return False


@app.post("/api/search-v2")
async def search_v2(request: SearchRequest):
    """
    Search V2 Endpoint - Serper API call with fuzzy cache matching
    Part 1: Check cache → Query Serper API if needed → Return raw results
    Does NOT process/analyze URLs - just returns Serper response
    """
    try:
        # Load current app settings
        app_settings = get_app_settings()

        # Build settings dict for cache lookup
        settings = {
            "search_type": request.search_type or "search",
            "gl": request.gl,
            "hl": request.hl,
            "location": request.location,
            "num": request.num,
            "page": request.page,
            "tbs": request.tbs,
            "autocorrect": request.autocorrect,
            "nfpr": request.nfpr,
            "safe": request.safe
        }

        # Remove None values for cleaner cache matching
        settings = {k: v for k, v in settings.items() if v is not None}

        # Step 1: Check cache with fuzzy matching (98% threshold by default)
        cached = None
        if not request.disable_cache:
            cached = cache.get_cached_search(
                query_text=request.q,
                settings=settings,
                max_age_hours=24,
                fuzzy_match_threshold=98,  # Default from config
                enable_fuzzy_matching=True
            )

        # Step 2: If cached and has full Serper response, return it
        if cached and cached.get('analysis_results'):
            print(f"[CACHE HIT] Query: '{request.q}' | Match: {cached.get('match_type')} | Similarity: {cached.get('similarity_score')}%")
            return {
                "success": True,
                "from_cache": True,
                "serper_response": cached['analysis_results'],  # Full Serper response stored here
                "query": request.q,
                "settings": settings,
                "cache_match_type": cached.get('match_type'),
                "cache_similarity": cached.get('similarity_score')
            }

        # Step 3: Cache miss - call Search Provider API
        provider_name = getattr(request, 'provider', 'serper') or 'serper'
        print(f"[CACHE MISS] Query: '{request.q}' | Calling {provider_name} API")
        provider_client = get_search_provider(provider_name)
        results = provider_client.search(
            query=request.q,
            search_type=settings["search_type"],
            gl=request.gl,
            hl=request.hl,
            location=request.location,
            num=request.num or 10,
            page=request.page or 1,
            tbs=request.tbs,
            autocorrect=request.autocorrect,
            nfpr=request.nfpr,
            safe=request.safe
        )

        # Step 4: Save to cache with full search response
        query_id = cache.start_search(request.q, settings)

        # Save full search response in analysis_results_json
        cache.save_analysis_results(query_id, results)

        # Also save URLs for deduplication tracking
        urls = provider_client.extract_urls(results, settings["search_type"])
        cache.record_results_batch(query_id, urls, engine=provider_name)

        print(f"[CACHE SAVED] Query ID: {query_id} | Results: {len(results.get('organic', []))}")

        return {
            "success": True,
            "from_cache": False,
            "serper_response": results,
            "query": request.q,
            "settings": settings
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-url")
async def analyze_url(request: AnalyzeURLRequest):
    """
    Analyze Single URL Endpoint - Part 2 of Search V2
    Called when user clicks "View Analysis" button on a search result

    Flow:
    1. Route URL to HTML or PDF pipeline
    2. Download content
    3. Extract text
    4. Score quality
    5. Cache result
    6. Return analysis

    Request:
        {
            "url": "https://example.com/article",
            "index": 0
        }

    Response:
        {
            "status": "success|filtered|error",
            "url": "...",
            "title": "...",
            "content": "...",
            "heuristic_score": 75,
            "nlp_score": 68,
            "final_score": 73,
            "quality_class": "legit",
            "word_count": 1250,
            ...
        }
    """
    try:
        # Load current app settings
        app_settings = get_app_settings()

        print(f"[ANALYZE-URL] Starting analysis for: {request.url}")

        # Use global shared router instead of creating a new one
        # This prevents spawning 32 workers per request (massive performance gain!)
        router = get_global_router()

        # Route single URL to appropriate pipeline
        # Use run_in_executor to avoid blocking FastAPI event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,  # Use default executor
            lambda: router.route_urls(
                urls=[request.url],
                progress_callback=None,  # No progress callback for single URL
                cache_enabled=True,
                revalidation_threshold_days=app_settings.cache.revalidation_threshold_days,
                error_cache_days=app_settings.cache.error_cache_days,
                filtered_cache_days=app_settings.cache.filtered_cache_days,
                html_timeout=app_settings.analysis.html_timeout,
                html_quality_threshold=app_settings.analysis.html_quality_threshold,
                max_retry_attempts=app_settings.analysis.max_retry_attempts,
                retry_delay=app_settings.analysis.retry_delay,
                pdf_timeout=app_settings.analysis.pdf_timeout,
                url_timeout=app_settings.analysis.url_timeout,
                max_download_workers=app_settings.analysis.max_download_workers,
                rate_limit_per_domain=app_settings.analysis.rate_limit_per_domain,
                rate_limit_delay=app_settings.analysis.rate_limit_delay
            )
        )

        # Extract first (and only) result
        if result and result.get('results') and len(result['results']) > 0:
            analysis_result = result['results'][0]

            # Add index to result
            analysis_result['index'] = request.index

            status = analysis_result.get('status', 'unknown')
            print(f"[ANALYZE-URL] Completed: {request.url} | Status: {status}")

            return analysis_result
        else:
            print(f"[ANALYZE-URL] No result returned for: {request.url}")
            return {
                "status": "error",
                "error": "No result returned from router",
                "url": request.url,
                "index": request.index
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ANALYZE-URL] Error analyzing {request.url}: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "url": request.url,
            "index": request.index
        }


@app.post("/api/semantic-search")
async def semantic_search(request: SemanticSearchRequest):
    """
    Semantic Search Endpoint - Part 3 of Search V3
    Performs semantic search using embeddings across analyzed documents

    Flow:
    1. Embed user query
    2. Load document embeddings (filtered by URLs)
    3. Calculate cosine similarity
    4. Return ranked results by relevance

    Request:
        {
            "query": "machine learning trends 2025",
            "urls": ["https://example.com/doc1", "https://example.com/doc2"],
            "limit": 20,
            "threshold": 0.7
        }

    Response:
        {
            "success": true,
            "query": "...",
            "results": [
                {
                    "url": "...",
                    "doc_type": "html|pdf",
                    "chunk_id": 23,
                    "chunk_text": "...",
                    "similarity_score": 0.95
                }
            ],
            "stats": {
                "total_results": 15,
                "threshold_used": 0.7,
                "documents_searched": 20,
                "chunks_searched": 450
            }
        }
    """
    try:
        from services.semantic_search_service import SemanticSearchService

        print(f"[SEMANTIC-SEARCH] Query: '{request.query}', URLs: {len(request.urls)}, Threshold: {request.threshold}")

        # Load current app settings
        app_settings = get_app_settings()

        # Check if embeddings are enabled
        if not app_settings.embedding.enabled:
            return {
                "success": False,
                "error": "Embeddings are disabled in settings. Enable embeddings to use semantic search.",
                "query": request.query,
                "results": [],
                "stats": {
                    "total_results": 0,
                    "threshold_used": request.threshold,
                    "documents_searched": 0,
                    "chunks_searched": 0
                }
            }

        # Initialize semantic search service
        search_service = SemanticSearchService(app_settings)

        # Perform search
        results = search_service.search(
            query=request.query,
            limit=request.limit,
            score_threshold=request.threshold,
            url_filter=request.urls
        )

        # Get statistics
        stats = search_service.get_statistics()

        print(f"[SEMANTIC-SEARCH] Found {len(results)} results above threshold {request.threshold}")

        return {
            "success": True,
            "query": request.query,
            "results": results,
            "stats": {
                "total_results": len(results),
                "threshold_used": request.threshold,
                "documents_searched": len(request.urls),
                "chunks_searched": stats.get('total_embeddings', 0)
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SEMANTIC-SEARCH] Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "query": request.query,
            "results": [],
            "stats": {
                "total_results": 0,
                "threshold_used": request.threshold,
                "documents_searched": 0,
                "chunks_searched": 0
            }
        }


if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*60)
    print("🚀 Starting OpenQuery AI API")
    print("="*60)

    # Kill any existing process on port 8000
    print("\n🔍 Checking port 8000...")
    kill_process_on_port(8000)

    print("\n📊 Architecture: Services-based TRUE PARALLEL")
    print("  services/search_factory.py (Multi-Provider Search: Google & DuckDuckGo)")
    print("  services/router_service.py (Parallel Orchestrator)")
    print("  services/html_service.py (HTML processor)")
    print("  services/pdf_service.py (PDF downloader)")
    print("  services/helpers/* (Scoring, NLP, etc.)")
    print("="*60)
    print("🔗 Access:")
    print("  API: http://localhost:8000")
    print("  Docs: http://localhost:8000/docs")
    print("="*60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
