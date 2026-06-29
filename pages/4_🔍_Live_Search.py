"""
Live Semantic Search Page
Performs full search pipeline with semantic result ranking
1. Executes Serper API search (with multi-page support)
2. Processes and embeds documents
3. Returns semantically ranked results (with adaptive threshold retry)
"""
import streamlit as st
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from services.semantic_search_service import SemanticSearchService
from components import api_client
from config.settings import AppSettings, SETTINGS_FILE


# Page configuration
st.set_page_config(
    page_title="Live Semantic Search",
    page_icon="🔍",
    layout="wide"
)


@st.cache_resource
def get_app_settings():
    """Load app settings (cached)"""
    return AppSettings.load(SETTINGS_FILE)


def get_search_service():
    """Get search service (not cached due to OpenAI client serialization issues)"""
    return SemanticSearchService()


def render_search_page():
    """Render the semantic search page"""

    # Custom CSS for better styling
    st.markdown("""
        <style>
        .search-header {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            color: white;
        }
        .search-header h1 {
            color: white;
            margin-bottom: 0.5rem;
        }
        .search-header p {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1.1rem;
        }
        .result-card {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .result-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        .result-title {
            font-size: 1.2rem;
            font-weight: 600;
            color: #1a1a1a;
        }
        .score-badge {
            background: #667eea;
            color: white;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        .result-meta {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
        .result-content {
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 6px;
            border-left: 3px solid #667eea;
            margin-top: 1rem;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.6;

            /* Enable word wrapping - no more horizontal scroll */
            white-space: pre-wrap;      /* Preserve line breaks but allow wrapping */
            word-wrap: break-word;       /* Break long words if needed */
            overflow-wrap: break-word;   /* Modern CSS word breaking */
            overflow-x: auto;            /* Fallback scrollbar for very long unbreakable strings */
            max-width: 100%;             /* Ensure content stays within card */
        }
        .stats-container {
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-box {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1rem;
            flex: 1;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: #667eea;
        }
        .stat-label {
            color: #666;
            font-size: 0.9rem;
            margin-top: 0.5rem;
        }
        </style>
    """, unsafe_allow_html=True)

    # Header
    st.markdown("""
        <div class="search-header">
            <h1>🔍 Live Semantic Search</h1>
            <p>Intelligent search powered by AI embeddings - finds the most relevant content for your query</p>
        </div>
    """, unsafe_allow_html=True)

    # Get services
    search_service = get_search_service()
    settings = get_app_settings()

    # Check if embeddings are enabled
    if not settings.embedding.enabled:
        st.error("❌ Embeddings are disabled in settings. Please enable embeddings to use this feature.")
        return

    # Read latest settings from file for defaults (bypass cache)
    import json
    with open(SETTINGS_FILE, 'r') as f:
        settings_dict = json.load(f)

    default_document_search = settings_dict.get('results', {}).get('enable_document_search', False)
    default_num_results = settings_dict.get('results', {}).get('num_results', 10)
    default_similarity_threshold = settings_dict.get('embedding', {}).get('similarity_threshold', 0.5)
    default_max_results = settings_dict.get('embedding', {}).get('max_search_results', 10)

    # Search input in a container
    with st.container():
        query = st.text_input(
            "Search Query",
            placeholder="e.g., What are the latest developments in artificial intelligence?",
            help="Enter a natural language query",
            label_visibility="collapsed"
        )

        # Document Search checkbox (below query) - use latest saved setting
        document_search = st.checkbox(
            "📄 Include Document Search",
            value=default_document_search,
            help="Add parallel search with ' pdf' appended to find documents/PDFs (page 1 only, 10 additional results)"
        )

    # Advanced options in an expander
    with st.expander("⚙️ Advanced Options", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            num_results = st.number_input(
                "Web Results to Fetch",
                min_value=5,
                max_value=30,
                value=default_num_results,
                help="Number of documents to fetch from Serper API"
            )

        with col2:
            similarity_threshold = st.slider(
                "Similarity Threshold",
                min_value=0.0,
                max_value=1.0,
                value=default_similarity_threshold,
                step=0.01,
                help="Minimum similarity score (lower = more results)"
            )

        with col3:
            max_results = st.number_input(
                "Max Results",
                min_value=1,
                max_value=100,
                value=default_max_results,
                help="Maximum number of results to display"
            )

        # Time Filters
        st.markdown("---")
        st.markdown("**⏰ Time Filters**")

        # Get default time filter from settings
        default_time_filter = settings_dict.get('time_filter', {}).get('time_filter', None)
        default_custom_start = settings_dict.get('time_filter', {}).get('custom_start_date', None)
        default_custom_end = settings_dict.get('time_filter', {}).get('custom_end_date', None)

        time_filter_options = ["None", "day", "week", "month", "year", "custom"]
        time_filter_labels = {
            "None": "No time filter",
            "day": "Past day",
            "week": "Past week",
            "month": "Past month",
            "year": "Past year",
            "custom": "Custom date range"
        }

        # Find default index
        if default_time_filter and default_time_filter in time_filter_options:
            default_time_idx = time_filter_options.index(default_time_filter)
        else:
            default_time_idx = 0

        time_filter = st.selectbox(
            "Time Filter",
            time_filter_options,
            index=default_time_idx,
            format_func=lambda x: time_filter_labels[x],
            help="Filter results by publication date"
        )

        # Custom date range if selected
        tbs_value = None
        if time_filter == "custom":
            from datetime import datetime, timedelta
            col_start, col_end = st.columns(2)
            with col_start:
                start_date = st.date_input(
                    "Start Date",
                    value=datetime.strptime(default_custom_start, "%Y-%m-%d") if default_custom_start else datetime.now() - timedelta(days=30),
                    help="Start date for custom range"
                )
            with col_end:
                end_date = st.date_input(
                    "End Date",
                    value=datetime.strptime(default_custom_end, "%Y-%m-%d") if default_custom_end else datetime.now(),
                    help="End date for custom range"
                )
            # Format: cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY
            tbs_value = f"cd_min:{start_date.strftime('%m/%d/%Y')},cd_max:{end_date.strftime('%m/%d/%Y')}"
        elif time_filter == "day":
            tbs_value = "qdr:d"
        elif time_filter == "week":
            tbs_value = "qdr:w"
        elif time_filter == "month":
            tbs_value = "qdr:m"
        elif time_filter == "year":
            tbs_value = "qdr:y"

        # Display current fuzzy cache matching settings (from Settings page)
        # Force reload from file (bypass Streamlit cache)
        st.markdown("---")
        st.markdown("**🔍 Cache Fuzzy Matching Settings**")

        # Read directly from file to get latest saved values
        import json
        with open(SETTINGS_FILE, 'r') as f:
            settings_dict = json.load(f)

        fuzzy_enabled = settings_dict.get('cache', {}).get('enable_fuzzy_cache_matching', True)
        fuzzy_threshold = settings_dict.get('cache', {}).get('fuzzy_match_threshold', 85)

        if fuzzy_enabled:
            if fuzzy_threshold >= 90:
                status = "Very Strict"
                color = "🟢"
            elif fuzzy_threshold >= 80:
                status = "Strict"
                color = "🔵"
            else:
                status = "Moderate"
                color = "🟡"

            st.info(
                f"{color} **Fuzzy Matching: Enabled**\n\n"
                f"• Threshold: **{fuzzy_threshold}%** ({status})\n\n"
                f"• Queries with ≥{fuzzy_threshold}% similarity will use cached results\n\n"
                f"_To change these settings, go to [Settings → Cache](/Settings)_"
            )
        else:
            st.warning(
                f"⚪ **Fuzzy Matching: Disabled**\n\n"
                f"• Only exact query matches will use cached results\n\n"
                f"_To enable, go to [Settings → Cache](/Settings)_"
            )

    # Show document search query if enabled
    if document_search:
        st.info(f"📄 **Document search enabled** - Will also search for: `{query} pdf`")

    # Search button
    if st.button("🔍 Search", type="primary", use_container_width=True):
        if not query:
            st.warning("⚠️ Please enter a search query")
            return

        # Clear previous cache info before starting new search
        if "live_search_cache_info" in st.session_state:
            del st.session_state["live_search_cache_info"]

        # Read settings directly from file (bypass cache) to get latest values
        import json
        with open(SETTINGS_FILE, 'r') as f:
            settings_dict = json.load(f)

        current_fuzzy_enabled = settings_dict.get('cache', {}).get('enable_fuzzy_cache_matching', True)
        current_fuzzy_threshold = settings_dict.get('cache', {}).get('fuzzy_match_threshold', 85)

        # Step 1: Execute Serper API search (multi-page if needed)
        with st.spinner("🔄 Searching the web..."):

            # Calculate pages needed (Serper API limit: 10 results per page)
            pages_needed = max(1, (num_results + 9) // 10)

            # Update info message to show document search status
            search_info = f"📄 Fetching {num_results} results ({pages_needed} page{'s' if pages_needed > 1 else ''})"
            if document_search:
                search_info += " + document search"
            st.info(search_info + "...")

            # Execute parallel page requests
            try:
                urls = []
                cache_match_info = None  # Store cache match info

                def fetch_page(page_num, query_text=None):
                    """Fetch a single page of results"""
                    search_payload = {
                        "q": query_text if query_text else query,
                        "search_type": "search",
                        "num": 10,  # Serper API limit per page
                        "safe": "off",
                        "autocorrect": True,
                        "page": page_num,
                        "disable_cache": False,
                        # Pass session-specific fuzzy matching settings (captured at search time)
                        "enable_fuzzy_matching": current_fuzzy_enabled,
                        "fuzzy_match_threshold": current_fuzzy_threshold
                    }
                    # Add time filter if set
                    if tbs_value:
                        search_payload["tbs"] = tbs_value
                    response = api_client.search_query(search_payload)
                    if response.status_code == 200:
                        results = response.json()

                        # Capture cache match info from first page
                        if "cache_match_info" in results and page_num == 1 and not query_text:
                            nonlocal cache_match_info
                            cache_match_info = results.get("cache_match_info")

                        if "url_details" in results:
                            return [item.get("url") for item in results.get("url_details", [])
                                   if item.get("url")]
                    return []

                # Build list of search tasks
                search_tasks = []

                # Main search - multiple pages
                for page in range(1, pages_needed + 1):
                    search_tasks.append(("main", page, None))

                # Document search if enabled (page 1 only with " pdf" appended)
                if document_search:
                    search_tasks.append(("document", 1, f"{query} pdf"))

                # Execute all searches in parallel
                # Track which URLs came from which source
                main_urls = []
                document_urls = []

                with ThreadPoolExecutor(max_workers=min(len(search_tasks), 5)) as executor:
                    futures = {}
                    for task_type, page, custom_query in search_tasks:
                        future = executor.submit(fetch_page, page, custom_query)
                        futures[future] = (task_type, page)

                    for future in as_completed(futures):
                        task_type, page = futures[future]
                        page_urls = future.result()

                        if task_type == "document":
                            document_urls.extend(page_urls)
                        else:
                            main_urls.extend(page_urls)

                        urls.extend(page_urls)

                # Store cache info in session state (captured from page 1)
                if cache_match_info:
                    st.session_state["live_search_cache_info"] = cache_match_info

                # Store URL counts before deduplication
                total_main_urls = len(main_urls)
                total_doc_urls = len(document_urls)
                total_before_dedup = len(urls)

                # Deduplicate URLs while preserving order
                seen = set()
                unique_urls = []
                for url in urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)
                urls = unique_urls

                total_after_dedup = len(urls)

                # Limit to requested number of results
                urls = urls[:num_results]

                if not urls:
                    st.warning("⚠️ No URLs found in search results")
                    return

                # Build success message with breakdown
                success_msg = f"✅ Found {len(urls)} URLs"
                st.success(success_msg)

                # Show detailed breakdown
                if document_search:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Main Search", total_main_urls, help=f"From {pages_needed} page(s)")
                    with col2:
                        st.metric("Document Search", total_doc_urls, help="PDFs and documents")
                    with col3:
                        duplicates_removed = total_before_dedup - total_after_dedup
                        st.metric("After Dedup", total_after_dedup, delta=f"-{duplicates_removed}" if duplicates_removed > 0 else None, help=f"Duplicates removed, then limited to {len(urls)}")

                # Display cache match info immediately after search completes
                if cache_match_info:
                    match_type = cache_match_info.get("match_type")
                    if match_type == "exact":
                        st.success(
                            f"✅ **Exact Cache Match Found**\n\n"
                            f"Cached query: `{cache_match_info.get('matched_query')}`"
                        )
                    elif match_type == "fuzzy":
                        similarity = cache_match_info.get('similarity_score', 0)
                        # Determine if match is acceptable
                        if similarity >= current_fuzzy_threshold:
                            status_icon = "✅"
                            status_text = f"Similarity ({similarity}%) ≥ Threshold ({current_fuzzy_threshold}%)"
                        else:
                            status_icon = "⚠️"
                            status_text = f"Similarity ({similarity}%) < Threshold ({current_fuzzy_threshold}%)"

                        st.info(
                            f"🔍 **Similar Cache Match Found**\n\n"
                            f"• Your query: `{query}`\n\n"
                            f"• Matched cached query: `{cache_match_info.get('matched_query')}`\n\n"
                            f"{status_icon} {status_text}"
                        )
                else:
                    # No cache match - show settings used
                    if current_fuzzy_enabled:
                        st.info(
                            f"🆕 **No Cache Match** - Fresh search executed\n\n"
                            f"• Fuzzy matching: Enabled\n\n"
                            f"• Threshold: {current_fuzzy_threshold}%"
                        )
                    else:
                        st.info(
                            f"🆕 **No Cache Match** - Fresh search executed\n\n"
                            f"• Fuzzy matching: Disabled (exact matches only)"
                        )

            except Exception as e:
                st.error(f"❌ Search error: {str(e)}")
                return

        # Step 2: Process and embed documents
        with st.spinner(f"🔄 Processing and analyzing {len(urls)} documents..."):
            # Get app settings for proper configuration
            app_settings = get_app_settings()

            # Prepare analyze payload - use settings from config
            analyze_payload = {
                "urls": urls,
                "timeout": app_settings.analysis.html_timeout,
                "max_workers": app_settings.analysis.max_workers,
                "max_download_workers": app_settings.analysis.max_download_workers,
                "html_timeout": app_settings.analysis.html_timeout,
                "pdf_timeout": app_settings.analysis.pdf_timeout,
                "url_timeout": app_settings.analysis.url_timeout,
                "max_retry_attempts": app_settings.analysis.max_retry_attempts,
                "retry_delay": app_settings.analysis.retry_delay,
                "rate_limit_per_domain": app_settings.analysis.rate_limit_per_domain,
                "rate_limit_delay": app_settings.analysis.rate_limit_delay
            }

            # Stream analysis results
            all_results = []
            success_count = 0
            background_queued_count = 0

            try:
                with api_client.analyze_stream(analyze_payload, timeout=app_settings.analysis.api_stream_timeout) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines(decode_unicode=False):
                            if line:
                                line_str = line.decode('utf-8')
                                if line_str.startswith('data: '):
                                    data_str = line_str[6:]
                                    try:
                                        data = json.loads(data_str)
                                        event_type = data.get('type')

                                        if event_type == 'result':
                                            result = data.get('data', {})
                                            all_results.append(result)
                                            if result.get('status') == 'success':
                                                success_count += 1
                                            elif result.get('status') == 'background_queued':
                                                background_queued_count += 1
                                    except json.JSONDecodeError:
                                        pass
                    else:
                        st.error(f"❌ Analysis failed: {response.status_code}")
                        return

                # Warn if PDFs were queued to background
                if background_queued_count > 0:
                    st.warning(f"⚠️ {background_queued_count} PDF(s) are still processing in the background and won't appear in results yet. They will be available after processing completes.")

                # Debug: Show what was actually processed
                success_results = [r for r in all_results if r.get('status') == 'success']
                queued_results = [r for r in all_results if r.get('status') == 'background_queued']
                failed_results = [r for r in all_results if r.get('status') == 'error']

                pdf_processed = sum(1 for r in success_results if r.get('url', '').lower().endswith('.pdf'))
                html_processed = sum(1 for r in success_results if not r.get('url', '').lower().endswith('.pdf'))

                pdf_queued = sum(1 for r in queued_results if r.get('url', '').lower().endswith('.pdf'))
                pdf_failed = sum(1 for r in failed_results if r.get('url', '').lower().endswith('.pdf'))

                st.info(f"✅ Successfully Processed: {html_processed} HTML pages, {pdf_processed} PDFs")
                if pdf_queued > 0:
                    st.warning(f"⏳ Background Queued: {pdf_queued} PDFs (will be available in future searches)")
                if pdf_failed > 0:
                    st.error(f"❌ Failed: {pdf_failed} PDFs")

            except Exception as e:
                st.error(f"❌ Processing error: {str(e)}")
                return

        # Step 3: Perform semantic search ONLY on documents from this search session
        # With adaptive threshold retry (if zero results, reduce threshold by 5% up to 3 times, min 0.3)
        with st.spinner("🔄 Finding the most relevant results..."):
            # Normalize URLs to match embedding storage format (removes trailing slashes, etc.)
            from services.helpers.url_utils import normalize_url
            normalized_urls = [normalize_url(url) for url in urls]

            # Debug: Show what we're searching for
            st.info(f"🔍 Searching embeddings for {len(normalized_urls)} URLs (from {success_count} successfully processed documents)")

            # Show first few URLs for debugging
            if normalized_urls:
                st.caption(f"Sample URLs: {', '.join(normalized_urls[:3])}{'...' if len(normalized_urls) > 3 else ''}")

            # Adaptive threshold retry logic
            current_threshold = similarity_threshold
            results = []
            retry_count = 0
            max_retries = 3
            threshold_step = 0.05  # 5% reduction
            min_threshold = 0.3

            # Only use adaptive retry if starting threshold > 0.3
            use_adaptive_retry = current_threshold > min_threshold

            while retry_count <= max_retries:
                results = search_service.search(
                    query=query,
                    limit=int(max_results),
                    doc_type_filter=None,  # Search all types
                    score_threshold=current_threshold,
                    url_filter=normalized_urls  # ONLY search embeddings from this search session
                )

                # Debug: Show what we found
                if results:
                    html_found = sum(1 for r in results if isinstance(r, dict) and r.get('doc_type') == 'html')
                    pdf_found = sum(1 for r in results if isinstance(r, dict) and r.get('doc_type') == 'pdf')
                    st.success(f"✅ Found {len(results)} chunks: {html_found} HTML, {pdf_found} PDF")

                if results or not use_adaptive_retry:
                    # Found results OR adaptive retry disabled (threshold already <= 0.3)
                    break

                # No results and threshold > 0.3 - try lowering threshold
                if retry_count < max_retries:
                    new_threshold = max(min_threshold, current_threshold - threshold_step)

                    # Stop if we've reached the minimum
                    if new_threshold <= min_threshold:
                        st.info(f"🔄 No results with threshold {current_threshold:.2f}, trying minimum threshold {min_threshold:.2f}...")
                        current_threshold = min_threshold
                        retry_count += 1
                        # One final try at minimum threshold
                        if retry_count > max_retries:
                            break
                    elif new_threshold < current_threshold:
                        st.info(f"🔄 No results with threshold {current_threshold:.2f}, retrying with {new_threshold:.2f}...")
                        current_threshold = new_threshold
                        retry_count += 1
                    else:
                        # Can't reduce further
                        break
                else:
                    # Max retries reached
                    break

            if not results:
                st.warning("⚠️ No semantically similar results found even after adaptive threshold adjustment.")
                st.info(f"💡 Tip: Processed {success_count} documents but none matched your query with similarity >= {current_threshold:.2f}")
                st.info(f"🔧 Tried thresholds: {similarity_threshold:.2f} → {current_threshold:.2f} ({retry_count} adjustment{'s' if retry_count != 1 else ''})")

                # Show debugging info
                st.caption(f"📊 Processing breakdown: {html_processed} HTML (successfully processed), {pdf_processed} PDFs (successfully processed), {pdf_queued} PDFs (queued to background)")
                st.caption(f"🔍 Searched {len(normalized_urls)} URLs for embeddings")

                return

            # Show threshold adjustment info if it was changed
            if current_threshold != similarity_threshold:
                st.success(f"✅ Found {len(results)} results after lowering threshold from {similarity_threshold:.2f} to {current_threshold:.2f}")

            # Update threshold for stats display
            similarity_threshold = current_threshold

            # Store results in session state so they persist across reruns
            st.session_state['search_results'] = results
            st.session_state['success_count'] = success_count
            st.session_state['similarity_threshold'] = similarity_threshold

    # Check if we have cached search results (from previous search or after button click)
    if 'search_results' in st.session_state and st.session_state['search_results']:
        results = st.session_state['search_results']
        success_count = st.session_state.get('success_count', 0)
        similarity_threshold = st.session_state.get('similarity_threshold', 0.5)

        # Count HTML vs PDF results (filter out non-dict items)
        html_count = sum(1 for r in results if isinstance(r, dict) and r.get('doc_type', '').lower() == 'html')
        pdf_count = sum(1 for r in results if isinstance(r, dict) and r.get('doc_type', '').lower() == 'pdf')

        # Stats display
        st.markdown(f"""
            <div class="stats-container">
                <div class="stat-box">
                    <div class="stat-value">{len(results)}</div>
                    <div class="stat-label">Results Found</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{html_count}</div>
                    <div class="stat-label">HTML Pages</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{pdf_count}</div>
                    <div class="stat-label">PDF Documents</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{similarity_threshold:.2f}</div>
                    <div class="stat-label">Min Similarity</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Split layout: Left (results) | Right (source viewer)
        col_results, col_viewer = st.columns([1, 1])

        # Display results in left column
        with col_results:
            st.markdown("### 📄 Search Results")

        for idx, result in enumerate(results, 1):
            # Skip invalid results
            if not isinstance(result, dict):
                st.warning(f"⚠️ Result #{idx} has invalid format (expected dict, got {type(result).__name__})")
                continue

            if 'url' not in result or 'chunk_text' not in result:
                st.warning(f"⚠️ Result #{idx} is missing required fields")
                continue

            with col_results:
                # Get a clean domain name from URL
                from urllib.parse import urlparse
                try:
                    domain = urlparse(result['url']).netloc.replace('www.', '')
                except Exception as e:
                    domain = "unknown"
                    st.warning(f"⚠️ Could not parse URL for result #{idx}: {e}")

                # Score color based on value
                score = result.get('similarity_score', 0.0)
                if score >= 0.8:
                    score_color = "#10b981"  # green
                elif score >= 0.6:
                    score_color = "#3b82f6"  # blue
                elif score >= 0.4:
                    score_color = "#f59e0b"  # orange
                else:
                    score_color = "#6b7280"  # gray

                # Show full chunk text (no truncation - testing page)
                chunk_preview = result.get('chunk_text', '')

                # Get safe field values
                doc_type = result.get('doc_type', 'unknown')
                chunk_id = result.get('chunk_id', 'N/A')
                url = result.get('url', '')

                # Create card
                st.markdown(f"""
                    <div class="result-card">
                        <div class="result-header">
                            <div>
                                <div class="result-title">Result #{idx}</div>
                                <div class="result-meta">
                                    <span style="color: {score_color};">●</span> {domain} •
                                    {doc_type.upper()} •
                                    Chunk {chunk_id}
                                </div>
                            </div>
                            <div class="score-badge" style="background: {score_color};">
                                {score:.1%} Match
                            </div>
                        </div>
                        <div class="result-content">
                            {chunk_preview}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # Expandable details
                with st.expander(f"🔍 View Full Content & Actions", expanded=False):
                    st.markdown(f"**🔗 Source URL:**")
                    st.markdown(f"[{url}]({url})")

                    st.markdown("**📝 Full Content:**")
                    st.code(chunk_preview, language=None)

                    st.markdown(f"**📊 Metadata:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Similarity Score", f"{score:.4f}")
                    with col2:
                        st.metric("Document Type", doc_type.upper())
                    with col3:
                        st.metric("Chunk ID", chunk_id)

                    # Match Chunk to Source button
                    st.markdown("---")
                    match_btn_key = f"match_btn_{idx}_{url[:20]}"  # Unique key
                    if st.button(f"🎯 Match Chunk to Source", key=match_btn_key, use_container_width=True):
                        # Import the chunk matcher service
                        from services.chunk_matcher_service import ChunkMatcherService

                        # Create matcher instance
                        matcher = ChunkMatcherService()

                        # Perform matching
                        match_result = matcher.match_chunk_to_source(
                            url=url,
                            chunk_text=chunk_preview,
                            doc_type=doc_type
                        )

                        # Store in session state for viewer
                        st.session_state['source_viewer_match'] = match_result
                        st.session_state['viewer_updated'] = True

                        # Force rerun to update right pane
                        st.rerun()

        # Render source viewer in right column (after all results are processed)
        with col_viewer:
            from components.source_viewer import render_source_viewer
            match_result = st.session_state.get('source_viewer_match', None)
            render_source_viewer(match_result)


if __name__ == "__main__":
    render_search_page()
