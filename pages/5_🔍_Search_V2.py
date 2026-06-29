"""
Search V2 Page
Part 1: Query → Serper API → Display Results (fast)
Part 2: User clicks "View Analysis" → Download & Analyze URL (on-demand)
"""
import streamlit as st
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from components.search_panel_v2 import render_search_panel_v2
from components.serper_results_v2 import render_serper_results_v2
from components.analysis_results_panel import render_analysis_results_panel

# Page configuration
st.set_page_config(
    page_title="Search V2",
    page_icon="🔍",
    layout="wide"
)

# API configuration - Use 127.0.0.1 instead of localhost for WSL performance
API_BASE_URL = "http://127.0.0.1:8000"


def build_payload(query, params, page=1):
    """Build API request payload"""
    payload = {
        "q": query,
        "search_type": params["search_type"],
        "num": 10,  # Serper returns max 10 per page
        "page": page,
        "disable_cache": not params["enable_serper_cache"]
    }

    # Add optional parameters
    if params.get("country"):
        payload["gl"] = params["country"]
    if params.get("language"):
        payload["hl"] = params["language"]
    if params.get("location"):
        payload["location"] = params["location"]

    # Safe search
    if params.get("safe_search") and params["safe_search"] != "off":
        payload["safe"] = params["safe_search"]

    # Autocorrect
    if not params.get("enable_autocorrect"):
        payload["nfpr"] = True

    # Time filter - convert to tbs parameter
    if params.get("time_filter") and params["time_filter"] != "None":
        time_filter = params["time_filter"]
        if time_filter == "day":
            payload["tbs"] = "qdr:d"
        elif time_filter == "week":
            payload["tbs"] = "qdr:w"
        elif time_filter == "month":
            payload["tbs"] = "qdr:m"
        elif time_filter == "year":
            payload["tbs"] = "qdr:y"
        elif time_filter == "custom" and params.get("custom_start_date") and params.get("custom_end_date"):
            from datetime import datetime
            start = datetime.strptime(params["custom_start_date"], "%Y-%m-%d").strftime("%m/%d/%Y")
            end = datetime.strptime(params["custom_end_date"], "%Y-%m-%d").strftime("%m/%d/%Y")
            payload["tbs"] = f"cd_min:{start},cd_max:{end}"

    # Fuzzy cache matching
    if params.get("enable_fuzzy_cache_matching"):
        payload["enable_fuzzy_matching"] = True
        payload["fuzzy_match_threshold"] = params.get("fuzzy_match_threshold", 98)

    return payload


def call_single_search(payload):
    """Make a single API call"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/search-v2",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_search_v2_api(params):
    """
    Call Search V2 API with parallel multi-page queries

    Args:
        params: dict with search parameters

    Returns:
        dict with combined API response
    """
    try:
        # Calculate how many queries needed
        num_results = params["num_results"]
        num_pages = (num_results + 9) // 10  # Round up, max 10 results per page

        # If document search enabled, total results = num_results + 10
        total_results_needed = num_results + 10 if params.get("enable_document_search") else num_results

        queries = []

        # Regular search queries (multi-page)
        for page in range(1, num_pages + 1):
            queries.append({
                "type": "regular",
                "payload": build_payload(params["query"], params, page)
            })

        # Document search query (if enabled) - adds 10 more results
        if params.get("enable_document_search"):
            doc_query = f"{params['query']} pdf"
            queries.append({
                "type": "document",
                "payload": build_payload(doc_query, params, 1)
            })
            print(f"[DEBUG] Document search enabled! Adding PDF query: '{doc_query}'")
            print(f"[DEBUG] Total results needed: {total_results_needed} (base: {num_results} + PDF: 10)")
        else:
            print(f"[DEBUG] Document search disabled. enable_document_search={params.get('enable_document_search')}")
            print(f"[DEBUG] Total results needed: {total_results_needed}")

        print(f"[DEBUG] Total queries to execute: {len(queries)}")
        for i, q in enumerate(queries):
            print(f"[DEBUG] Query {i+1}: type={q['type']}, q={q['payload']['q']}, page={q['payload']['page']}")

        # Execute queries in parallel
        results = []
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_query = {executor.submit(call_single_search, q["payload"]): q for q in queries}

            for future in as_completed(future_to_query):
                query_info = future_to_query[future]
                result = future.result()
                if result.get("success"):
                    results.append({
                        "type": query_info["type"],
                        "query": query_info["payload"]["q"],
                        "page": query_info["payload"]["page"],
                        "data": result
                    })

        # Combine results
        if not results:
            return None

        # Sort results to ensure consistent ordering: regular queries by page, then document search
        results.sort(key=lambda x: (x["type"] != "regular", x["page"]))

        print(f"[DEBUG] Sorted results order:")
        for i, r in enumerate(results):
            print(f"  {i+1}. {r['type']} - page {r['page']} - query: {r['query']}")

        # Group results by query for accordion display
        results_by_query = []
        seen_urls_global = set()
        all_organic = []
        from_cache = False

        for r in results:
            query_type = r["type"]
            query_text = r["query"]
            page_num = r["page"]
            data = r["data"]
            serper_resp = data.get("serper_response", {})
            organic = serper_resp.get("organic", [])

            # Track cache status
            if data.get("from_cache"):
                from_cache = True

            # Deduplicate within this query's results AND globally
            seen_urls_local = set()
            unique_results_for_group = []  # Results for this group (after global dedup)

            for item in organic:
                url = item.get("link", "")
                if url and url not in seen_urls_local:
                    seen_urls_local.add(url)

                    # Only add to group if not already seen globally
                    if url not in seen_urls_global:
                        seen_urls_global.add(url)
                        all_organic.append(item)
                        unique_results_for_group.append(item)

            # Add to grouped results with accurate count (after global dedup)
            query_label = f"Page {page_num}" if query_type == "regular" else "PDF Search"
            results_by_query.append({
                "label": query_label,
                "type": query_type,
                "query": query_text,
                "page": page_num,
                "results": unique_results_for_group,
                "count": len(unique_results_for_group)  # Count after global dedup
            })

        # Count results before limiting
        total_before_limit = len(all_organic)

        # Limit total results to what's needed
        all_organic = all_organic[:total_results_needed]

        print(f"[DEBUG] Results before dedup/limit: {sum(len(r['data'].get('serper_response', {}).get('organic', [])) for r in results)}")
        print(f"[DEBUG] Results after deduplication: {total_before_limit}")
        print(f"[DEBUG] Results after limiting to {total_results_needed}: {len(all_organic)}")
        print(f"[DEBUG] Grouped results: {[(g['label'], g['count']) for g in results_by_query]}")

        # Return combined response with grouped results
        return {
            "success": True,
            "from_cache": from_cache,
            "serper_response": {
                "organic": all_organic,
                "searchParameters": params
            },
            "results_by_query": results_by_query,  # New: grouped by query
            "query": params["query"],
            "settings": params,
            "queries_made": len(queries),
            "results_combined": total_before_limit,  # Show count before limiting
            "results_unique": len(all_organic)  # Show count after limiting
        }

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        return None


def call_analyze_url_api(url, index=0):
    """
    Call /api/analyze-url to analyze a single URL

    Args:
        url: URL to analyze
        index: Result index

    Returns:
        dict with analysis result
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/analyze-url",
            json={"url": url, "index": index},
            timeout=120  # 2 minutes timeout for analysis
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": url,
            "index": index
        }


def render_search_v2_page():
    """Main page render function"""

    # Initialize analysis state if not exists
    if 'show_analysis' not in st.session_state:
        st.session_state['show_analysis'] = False
        st.session_state['analysis_result'] = None
        st.session_state['analysis_url'] = None

    # Initialize search results state
    if 'search_results_data' not in st.session_state:
        st.session_state['search_results_data'] = None

    # Check if user clicked "View Analysis" button
    if 'analyze_url' in st.session_state and 'analyze_index' in st.session_state:
        url = st.session_state['analyze_url']
        index = st.session_state['analyze_index']

        # Clear the trigger
        del st.session_state['analyze_url']
        del st.session_state['analyze_index']

        # Fetch analysis
        with st.spinner(f"Analyzing URL..."):
            analysis_result = call_analyze_url_api(url, index)

        # Store in persistent state
        st.session_state['show_analysis'] = True
        st.session_state['analysis_result'] = analysis_result
        st.session_state['analysis_url'] = url

    # Search panel at top
    search_data = render_search_panel_v2()

    st.markdown("---")

    # Handle new search - clear old analysis and store new results
    if search_data["search_clicked"]:
        # Clear analysis when new search is performed
        st.session_state['show_analysis'] = False
        st.session_state['analysis_result'] = None
        st.session_state['analysis_url'] = None

        params = search_data["params"]

        # Validate query
        if not params["query"].strip():
            st.warning("⚠️ Please enter a search query.")
            st.session_state['search_results_data'] = None
        else:
            # Show loading state
            with st.spinner(f"🔍 Searching for: **{params['query']}**"):
                # Call API
                result = call_search_v2_api(params)

                # Store results in session state
                if result and result.get("success"):
                    st.session_state['search_results_data'] = {
                        'result': result,
                        'params': params
                    }

                    # AUTO ANALYSIS: If enabled, trigger analysis for all results IN PARALLEL
                    if params.get("enable_auto_analysis", False):
                        # Extract all URLs from results
                        organic_results = result.get("serper_response", {}).get("organic", [])
                        total_urls = len(organic_results)

                        if total_urls > 0:
                            # Initialize auto analysis state
                            if 'auto_analysis_results' not in st.session_state:
                                st.session_state['auto_analysis_results'] = {}

                            # Show auto analysis progress
                            st.info(f"🤖 **Auto Analysis Enabled:** Analyzing {total_urls} results in parallel...")

                            # Create progress bar
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            # Analyze ALL URLs in parallel using ThreadPoolExecutor
                            import time
                            from concurrent.futures import ThreadPoolExecutor, as_completed

                            start_time = time.time()
                            completed_count = 0

                            # Create list of URLs to analyze
                            urls_to_analyze = [(idx, result_item.get("link", ""))
                                             for idx, result_item in enumerate(organic_results)
                                             if result_item.get("link", "")]

                            # Use ThreadPoolExecutor to make parallel API calls
                            # Process ALL results concurrently (up to 32 workers max)
                            max_workers = min(32, total_urls)
                            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                                # Submit all analysis tasks at once
                                future_to_url = {
                                    executor.submit(call_analyze_url_api, url, idx): (idx, url)
                                    for idx, url in urls_to_analyze
                                }

                                # Process results as they complete
                                for future in as_completed(future_to_url):
                                    idx, url = future_to_url[future]
                                    try:
                                        analysis_result = future.result()
                                        st.session_state['auto_analysis_results'][url] = analysis_result
                                    except Exception as e:
                                        st.session_state['auto_analysis_results'][url] = {
                                            'status': 'error',
                                            'error': str(e),
                                            'url': url
                                        }

                                    # Update progress
                                    completed_count += 1
                                    progress = completed_count / total_urls
                                    progress_bar.progress(progress)
                                    elapsed = time.time() - start_time
                                    status_text.text(f"Analyzing {completed_count}/{total_urls} ({elapsed:.1f}s elapsed)")

                            # Complete
                            total_time = time.time() - start_time
                            progress_bar.progress(1.0)

                            # Show summary with error and background counts
                            success_count = sum(1 for r in st.session_state['auto_analysis_results'].values() if r.get('status') == 'success')
                            error_count = sum(1 for r in st.session_state['auto_analysis_results'].values() if r.get('status') == 'error')
                            filtered_count = sum(1 for r in st.session_state['auto_analysis_results'].values() if r.get('status') == 'filtered')
                            bg_count = sum(1 for r in st.session_state['auto_analysis_results'].values() if r.get('status') == 'background_queued')
                            avg_time = total_time / total_urls if total_urls > 0 else 0

                            # Build summary message
                            summary_parts = [f"✅ **Auto Analysis Complete:** {success_count}/{total_urls} successful"]
                            if error_count > 0:
                                summary_parts.append(f"{error_count} errors")
                            if filtered_count > 0:
                                summary_parts.append(f"{filtered_count} filtered")
                            if bg_count > 0:
                                summary_parts.append(f"{bg_count} queued for background")
                            summary_parts.append(f"({total_time:.1f}s total, {avg_time:.1f}s avg)")

                            st.success(", ".join(summary_parts))

                else:
                    st.session_state['search_results_data'] = {
                        'error': result.get('detail', 'Unknown error') if result else 'No response'
                    }

    # Two-pane layout: Search results (left/center) + Analysis (right)
    if st.session_state.get('show_analysis', False):
        # Split into two columns when analysis is shown
        col_results, col_analysis = st.columns([2, 3])
    else:
        # Full width for results when no analysis
        col_results = st.container()
        col_analysis = None

    # Results area (left/center pane)
    with col_results:
        # Display stored search results
        if st.session_state['search_results_data'] is not None:
            search_data_stored = st.session_state['search_results_data']

            if 'error' in search_data_stored:
                st.error(f"❌ Search failed: {search_data_stored['error']}")
            else:
                result = search_data_stored['result']
                params = search_data_stored['params']

                # Show query stats
                st.success(f"✅ Found {result.get('results_unique', 0)} unique results from {result.get('queries_made', 1)} parallel queries")

                # Show API payload sent
                with st.expander("📤 API Request Payload", expanded=False):
                    st.json(params)

                # Prepare query info
                query_info = {
                    "query": params["query"],
                    "from_cache": result.get("from_cache", False),
                    "settings": result.get("settings", {})
                }

                # Render results
                render_serper_results_v2(
                    serper_response=result.get("serper_response"),
                    query_info=query_info,
                    results_by_query=result.get("results_by_query")  # Pass grouped results
                )

    # Analysis area (right pane)
    if col_analysis is not None:
        with col_analysis:
            st.markdown("### 📊 URL Analysis")

            # Render analysis panel
            render_analysis_results_panel(
                st.session_state['analysis_result'],
                st.session_state['analysis_url']
            )

            # Close button
            if st.button("✖️ Close Analysis", type="secondary", key="close_analysis"):
                st.session_state['show_analysis'] = False
                st.session_state['analysis_result'] = None
                st.session_state['analysis_url'] = None
                st.rerun()


# Render the page
if __name__ == "__main__":
    render_search_v2_page()
else:
    render_search_v2_page()
