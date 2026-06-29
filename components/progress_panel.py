"""
Progress Panel - Right Pane
Progress display and streaming analysis execution
"""
import streamlit as st
import json
import time
from typing import Dict, Any, List
from components import api_client
from services.cache_service import CacheService
from config.settings import AppSettings, SETTINGS_FILE


def render_progress_panel(cache: CacheService, app_settings: AppSettings,
                          search_clicked: bool, search_params: dict):
    """Render progress panel for search and analysis execution"""

    # Load fresh settings from file for API calls (bypass cache)
    with open(SETTINGS_FILE, 'r') as f:
        settings_dict = json.load(f)

    # Handle PDF Processing
    _handle_pdf_processing(app_settings, settings_dict)

    # Handle Search Click
    if search_clicked:
        _execute_search_and_analysis(cache, search_params, app_settings, settings_dict)

    # Show raw JSON at bottom if results available
    if "search_results" in st.session_state:
        _display_raw_json()
    else:
        st.info("👈 Configure your search and click '🚀 Search & Analyze Now'")


def _handle_pdf_processing(app_settings: AppSettings, settings_dict: dict):
    """Handle PDF processing trigger"""
    if not st.session_state.get('trigger_pdf_processing', False):
        return

    st.session_state['trigger_pdf_processing'] = False
    pdf_results_to_process = st.session_state.get('pdf_results_to_process', [])

    if not pdf_results_to_process:
        return

    with st.spinner(f"Processing {len(pdf_results_to_process)} PDF{'s' if len(pdf_results_to_process) > 1 else ''}..."):
        try:
            # Use latest settings from JSON file
            spacy_enabled = settings_dict.get('pdf', {}).get('spacy_enabled', False)
            spacy_require_gpu = settings_dict.get('pdf', {}).get('spacy_require_gpu', True)

            response = api_client.process_pdfs(
                pdf_results_to_process,
                enable_spacy=spacy_enabled,
                spacy_require_gpu=spacy_require_gpu
            )

            if response.status_code == 200:
                pdf_processing_results = response.json()
                st.session_state['pdf_processing_results'] = pdf_processing_results
                st.success(f"✅ Processed {pdf_processing_results.get('successful', 0)} PDFs successfully!")
                st.rerun()
            else:
                st.error(f"❌ PDF processing failed: {response.status_code} - {response.text}")

        except Exception as e:
            st.error(f"❌ PDF processing error: {str(e)}")


def _execute_search_and_analysis(cache: CacheService, search_params: Dict, app_settings: AppSettings, settings_dict: dict):
    """Execute search and analysis workflow"""
    # Check if already processing
    if st.session_state.get('processing', False):
        st.warning("⚠️ Analysis already in progress. Please wait...")
        st.stop()

    # Mark as processing
    st.session_state['processing'] = True

    # Start timer
    start_time = time.time()
    st.session_state["start_time"] = start_time

    # Extract search parameters
    query = search_params['query']
    search_type = search_params['search_type']
    num_results = search_params['num_results']
    safe = search_params['safe']
    autocorrect = search_params['autocorrect']
    parallel_workers = search_params['parallel_workers']
    timeout_setting = search_params['timeout_setting']
    disable_cache = search_params['disable_cache']
    document_search = search_params.get('document_search', False)

    # Calculate pages needed
    pages_needed = (num_results + 9) // 10

    # Build base payload
    base_payload = {
        "q": query,
        "search_type": search_type,
        "num": 10,
        "safe": safe,
        "autocorrect": autocorrect
    }

    # Record search in cache
    query_id = cache.start_search(query, base_payload)
    st.session_state["current_query_id"] = query_id

    # Add optional parameters
    if search_params['gl']:
        base_payload["gl"] = search_params['gl']
    if search_params['hl']:
        base_payload["hl"] = search_params['hl']
    if search_params['location']:
        base_payload["location"] = search_params['location']
    if search_params['tbs_value']:
        base_payload["tbs"] = search_params['tbs_value']

    # Store in session state
    st.session_state["last_search"] = base_payload
    st.session_state["parallel_workers"] = parallel_workers
    st.session_state["timeout_setting"] = timeout_setting

    # Execute search
    _perform_search(base_payload, pages_needed, disable_cache, cache, app_settings,
                    start_time, query_id, parallel_workers, timeout_setting, num_results,
                    document_search=document_search, settings_dict=settings_dict)


def _perform_search(base_payload: Dict, pages_needed: int, disable_cache: bool,
                    cache: CacheService, app_settings: AppSettings, start_time: float,
                    query_id: str, parallel_workers: int, timeout_setting: int, num_results: int,
                    document_search: bool = False, settings_dict: dict = None):
    """Perform search and handle results, with optional parallel document search"""

    all_results = []
    all_urls = []
    all_cache_batches = []
    total_serper_time = 0.0
    cache_hit = False
    current_query_id = query_id

    search_count = 2 if document_search else 1
    spinner_text = f"🔍 Searching ({pages_needed} page{'s' if pages_needed > 1 else ''}" + \
                   (f" + document search" if document_search else "") + ")..."

    with st.spinner(spinner_text):
        try:
            # Main search (original query)
            for page_num in range(1, pages_needed + 1):
                page_payload = base_payload.copy()
                page_payload["page"] = page_num
                page_payload["disable_cache"] = disable_cache

                response = api_client.search_query(page_payload)

                if response.status_code == 200:
                    page_results = response.json()

                    # Check for full cache hit
                    if page_results.get('analysis_cached', False):
                        _handle_full_cache_hit(page_results, start_time)
                        return

                    # Store cache match info from first page (for partial cache hits)
                    if page_num == 1 and 'cache_match_info' in page_results:
                        st.session_state['cache_match_info'] = page_results['cache_match_info']

                    # Check for Serper cache hit
                    if page_results.get('cached', False):
                        cache_hit = True

                    # Extract query_id
                    if 'query_id' in page_results and not current_query_id:
                        current_query_id = page_results.get('query_id')

                    # Extract timing
                    if 'serper_api_time' in page_results:
                        total_serper_time += page_results.get('serper_api_time', 0)

                    # Extract URLs and prepare cache batch
                    page_urls, cache_batch = _extract_urls_from_results(page_results, page_num)

                    if cache_batch:
                        all_cache_batches.append(cache_batch)

                    all_urls.extend(page_urls)
                    all_results.append(page_results)

                    if page_num < pages_needed:
                        st.info(f"📄 Fetched page {page_num}/{pages_needed} ({len(page_urls)} URLs)")
                else:
                    st.error(f"Search failed on page {page_num}: {response.status_code}")
                    break

            # PARALLEL DOCUMENT SEARCH (if enabled)
            if document_search:
                st.info("📄 Fetching document search results (with ' pdf' appended)...")

                # Create document search payload with " pdf" appended
                doc_payload = base_payload.copy()
                doc_payload["q"] = base_payload["q"] + " pdf"
                doc_payload["page"] = 1  # Only page 1 for document search
                doc_payload["disable_cache"] = disable_cache

                response = api_client.search_query(doc_payload)

                if response.status_code == 200:
                    doc_results = response.json()

                    # Check for Serper cache hit
                    if doc_results.get('cached', False):
                        cache_hit = True

                    # Extract timing
                    if 'serper_api_time' in doc_results:
                        total_serper_time += doc_results.get('serper_api_time', 0)

                    # Extract URLs from document search
                    doc_urls, doc_cache_batch = _extract_urls_from_results(doc_results, 1)

                    if doc_cache_batch:
                        all_cache_batches.append(doc_cache_batch)

                    # Merge document search URLs (deduplicate)
                    existing_urls = set(all_urls)
                    new_doc_urls = [url for url in doc_urls if url not in existing_urls]

                    all_urls.extend(new_doc_urls)
                    st.success(f"✅ Document search: +{len(new_doc_urls)} new URLs ({len(doc_urls) - len(new_doc_urls)} duplicates filtered)")
                else:
                    st.warning(f"⚠️ Document search failed: {response.status_code}")

            # Process combined results
            if all_results:
                _handle_search_results(all_results, all_urls[:num_results + (10 if document_search else 0)], start_time,
                                      total_serper_time, cache_hit, current_query_id,
                                      parallel_workers, timeout_setting, app_settings,
                                      all_cache_batches, cache, settings_dict)

        except Exception as e:
            st.error(f"Search failed: {str(e)}")
            st.session_state['processing'] = False


def _handle_full_cache_hit(page_results: Dict, start_time: float):
    """Handle full cache hit (query + analysis cached)"""
    search_elapsed = time.time() - start_time
    cached_results = page_results.get('analysis_results', [])

    # Store cache match info in session state
    if 'cache_match_info' in page_results:
        st.session_state['cache_match_info'] = page_results['cache_match_info']

    successful_count = sum(1 for r in cached_results if r.get('status') == 'success')
    filtered_count = sum(1 for r in cached_results if r.get('status') == 'filtered')
    failed_count = sum(1 for r in cached_results if r.get('status') in ['error', 'failed'])

    st.success(f"✅ Search: 0.000s Serper (CACHED) + 0.000s Process (CACHED) = {search_elapsed:.3f}s total")
    st.info(f"📊 Displaying {len(cached_results)} cached results ({successful_count} success, {filtered_count} filtered, {failed_count} failed)")

    formatted_results = {
        "results": cached_results,
        "successful": successful_count,
        "filtered": filtered_count,
        "failed": failed_count,
        "total": len(cached_results)
    }

    st.session_state.update({
        "extracted_urls": [r.get('url', '') for r in cached_results],
        "search_results": page_results,
        "search_time": search_elapsed,
        "serper_api_time": 0.0,
        "processing_time": 0.0,
        "total_time": search_elapsed,
        "cache_hit": True,
        "analysis_cached": True,
        "analysis_status": "success",
        "analysis_results": formatted_results,
        "processing_complete": True
    })

    st.session_state['processing'] = False
    st.rerun()
    st.stop()


def _extract_urls_from_results(page_results: Dict, page_num: int) -> tuple:
    """Extract URLs from search results and prepare cache batch
    
    Returns:
        tuple: (page_urls list, cache_batch list)
    """
    page_urls = []
    cache_batch = []

    if "url_details" in page_results:
        for idx, item in enumerate(page_results.get("url_details", [])):
            url = item.get("url")
            if url:
                page_urls.append(url)
                cache_batch.append({
                    'url': url,
                    'serp_position': (page_num - 1) * 10 + idx + 1,
                    'title': item.get("title", ""),
                    'snippet': item.get("snippet", "")
                })

    return page_urls, cache_batch


def _handle_search_results(all_results: list, urls: list, start_time: float,
                          total_serper_time: float, cache_hit: bool, query_id: str,
                          parallel_workers: int, timeout_setting: int,
                          app_settings: AppSettings, all_cache_batches: list,
                          cache: CacheService, settings_dict: dict = None):
    """Handle search results and start analysis"""

    if not urls:
        st.warning("No URLs found in search results")
        return

    combined_results = all_results[0]
    search_elapsed = time.time() - start_time

    st.session_state.update({
        "extracted_urls": urls,
        "search_results": combined_results,
        "search_time": search_elapsed,
        "serper_api_time": total_serper_time,
        "cache_hit": cache_hit
    })

    # Start analysis
    _start_streaming_analysis(urls, search_elapsed, total_serper_time, cache_hit,
                             query_id, parallel_workers, timeout_setting,
                             app_settings, all_cache_batches, cache, start_time, settings_dict)


def _start_streaming_analysis(urls: list, search_elapsed: float, total_serper_time: float,
                              cache_hit: bool, query_id: str, parallel_workers: int,
                              timeout_setting: int, app_settings: AppSettings,
                              all_cache_batches: list, cache: CacheService, start_time: float,
                              settings_dict: dict = None):
    """Start streaming analysis of URLs"""
    
    try:
        status_placeholder = st.empty()
        progress_placeholder = st.empty()
        progress_container = st.container()

        # Show search complete message
        overhead_time = search_elapsed - total_serper_time
        if cache_hit or total_serper_time == 0.0:
            status_placeholder.success(f"✅ Search: 0.000s Serper (CACHED) + {overhead_time:.3f}s overhead = {search_elapsed:.3f}s total | {len(urls)} URLs")
        else:
            status_placeholder.success(f"✅ Search: {total_serper_time:.3f}s Serper + {overhead_time:.3f}s overhead = {search_elapsed:.3f}s total | {len(urls)} URLs")

        analyze_start = time.time()
        completed = 0
        successful = 0
        filtered = 0
        failed = 0
        all_results = []

        status_placeholder.info(f"🔍 Starting analysis of {len(urls)} URLs...")

        # Create progress bars
        url_progress_bars = {}
        url_status_text = {}

        with progress_container:
            for idx, url in enumerate(urls):
                url_col, status_col = st.columns([3, 1])
                with url_col:
                    # Show full URL so we can see which ones hang
                    st.caption(f"**{idx + 1}.** {url}")
                with status_col:
                    url_status_text[idx] = st.empty()

                url_progress_bars[idx] = st.progress(0, text="⏳ Waiting...")

        # Set timeout
        stream_timeout = max(300, timeout_setting * len(urls) + 120)

        # Prepare analyze payload - use latest settings from JSON file
        # If settings_dict not provided, load from file
        if settings_dict is None:
            with open(SETTINGS_FILE, 'r') as f:
                settings_dict = json.load(f)

        analysis_settings = settings_dict.get('analysis', {})

        analyze_payload = {
            "urls": urls,
            "timeout": timeout_setting,
            "max_workers": parallel_workers,
            "max_download_workers": analysis_settings.get('max_download_workers', 5),
            "html_timeout": analysis_settings.get('html_timeout', 4),
            "pdf_timeout": analysis_settings.get('pdf_timeout', 8),
            "url_timeout": analysis_settings.get('url_timeout', 3),
            "max_retry_attempts": analysis_settings.get('max_retry_attempts', 1),
            "retry_delay": analysis_settings.get('retry_delay', 1),
            "rate_limit_per_domain": analysis_settings.get('rate_limit_per_domain', 4),
            "rate_limit_delay": analysis_settings.get('rate_limit_delay', 0.1)
        }
        
        if query_id:
            analyze_payload["query_id"] = query_id

        # Stream analysis results
        with api_client.analyze_stream(analyze_payload, stream_timeout) as response:
            if response.status_code == 200:
                for line in response.iter_lines(decode_unicode=False):
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            try:
                                data = json.loads(data_str)
                                event_type = data.get('type')

                                if event_type == 'start':
                                    actual_workers = data.get('actual_workers_used', parallel_workers)
                                    status_placeholder.info(f"🔍 Processing {len(urls)} URLs with {actual_workers} parallel workers...")

                                elif event_type == 'progress':
                                    idx = data.get('index')
                                    stage = data.get('stage', 'processing')
                                    percent = data.get('percent', 0)
                                    if idx in url_progress_bars:
                                        _update_progress_bar(url_progress_bars[idx], stage, percent)

                                elif event_type == 'result':
                                    result = data.get('data', {})
                                    idx = data.get('index', completed)
                                    all_results.append(result)
                                    completed += 1

                                    status = result.get('status', 'unknown')
                                    if status == 'success':
                                        successful += 1
                                    elif status == 'filtered':
                                        filtered += 1
                                    else:
                                        failed += 1

                                    # Update progress bar
                                    if idx in url_progress_bars:
                                        _update_result_progress(url_progress_bars, url_status_text, idx, result, status)

                                    # Update overall progress
                                    progress_percent = completed / len(urls)
                                    progress_placeholder.progress(
                                        progress_percent,
                                        text=f"⏳ {completed}/{len(urls)} | ✅ {successful} | 🚫 {filtered} | ❌ {failed}"
                                    )

                                elif event_type == 'error':
                                    st.error(f"❌ Streaming error: {data.get('message', 'Unknown error')}")
                                    st.session_state["analysis_status"] = "error"
                                    break

                                elif event_type == 'complete':
                                    _handle_analysis_complete(data, all_results, analyze_start, start_time,
                                                             total_serper_time, status_placeholder, 
                                                             progress_placeholder, progress_container,
                                                             all_cache_batches, cache, query_id, urls)
                                    break

                            except json.JSONDecodeError:
                                continue

                # Rerun if analysis complete
                if st.session_state.get('analysis_status') == 'success':
                    st.rerun()
            else:
                st.error(f"Analysis failed: HTTP {response.status_code}")
                st.session_state["analysis_status"] = "error"

    except Exception as e:
        st.error(f"❌ Analysis failed: {str(e)}")
        st.session_state["analysis_status"] = "error"
        st.session_state['processing'] = False


def _update_progress_bar(progress_bar, stage: str, percent: int):
    """Update individual URL progress bar"""
    stage_info = {
        'download': ('⬇️', 'Downloading'),
        'extract': ('📄', 'Extracting'),
        'clean': ('🧹', 'Cleaning'),
        'complete': ('✅', 'Complete')
    }
    emoji, text = stage_info.get(stage, ('⏳', 'Processing'))
    progress_val = min(1.0, max(0.0, percent / 100.0))
    progress_bar.progress(progress_val, text=f"{emoji} {text}: {percent}%")


def _update_result_progress(url_progress_bars, url_status_text, idx, result, status):
    """Update progress bar and status text for completed result"""
    if status == 'success':
        score = result.get('final_score', result.get('quality_score', 0))
        url_progress_bars[idx].progress(1.0, text="✅ Done")
        url_status_text[idx].success(f"Score: {score}/100")
    elif status == 'filtered':
        url_progress_bars[idx].progress(1.0, text="🚫 Filtered")
        url_status_text[idx].warning("Filtered")
    else:
        url_progress_bars[idx].progress(1.0, text="❌ Error")
        url_status_text[idx].error("Failed")


def _handle_analysis_complete(data, all_results, analyze_start, start_time,
                              total_serper_time, status_placeholder, 
                              progress_placeholder, progress_container,
                              all_cache_batches, cache, query_id, urls):
    """Handle analysis completion"""
    processing_time = time.time() - analyze_start
    total_time = time.time() - start_time

    st.session_state["analysis_results"] = {
        "status": "success",
        "total_urls": len(urls),
        "successful": data.get('successful', 0),
        "filtered": data.get('filtered', 0),
        "failed": data.get('failed', 0),
        "results": all_results
    }
    st.session_state["analysis_status"] = "success"
    st.session_state["processing_time"] = processing_time
    st.session_state["total_time"] = total_time
    st.session_state["serper_api_time"] = total_serper_time

    # Clear placeholders
    status_placeholder.empty()
    progress_placeholder.empty()
    progress_container.empty()

    st.balloons()

    # Write cache batches
    for cache_batch in all_cache_batches:
        cache.record_results_batch(query_id, cache_batch, engine="serper")

    st.session_state['processing'] = False


def _display_raw_json():
    """Display raw JSON response"""
    results_data = st.session_state["search_results"]
    
    st.markdown("---")

    with st.expander("🔍 Raw JSON Response", expanded=False):
        st.json(results_data)

    json_str = json.dumps(results_data, indent=2)
    st.download_button(
        label="📥 Download Search Results",
        data=json_str,
        file_name="search_results.json",
        mime="application/json",
        use_container_width=True
    )
