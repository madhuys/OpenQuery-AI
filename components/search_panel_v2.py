"""
Search Panel V2 Component
Collapsible search settings panel with tabbed advanced settings
"""
import streamlit as st
from datetime import datetime, timedelta
from config.settings import AppSettings, SETTINGS_FILE


def render_search_panel_v2():
    """
    Render search panel with collapsible tabbed settings
    Returns: dict with all search parameters
    """

    # Load app settings for defaults
    settings = AppSettings.load(SETTINGS_FILE)

    # Initialize session state for search parameters if not exists
    if 'search_params_v2' not in st.session_state:
        st.session_state.search_params_v2 = {
            # Search settings
            "query": settings.search.default_query,
            "search_type": settings.search.search_type,
            "provider": getattr(settings.search, "default_provider", "serper"),
            "enable_document_search": settings.results.enable_document_search,
            "num_results": settings.results.num_results,
            "country": settings.geographic.country,
            "language": settings.geographic.language,
            "location": settings.geographic.location,
            "time_filter": settings.time_filter.time_filter,
            "custom_start_date": settings.time_filter.custom_start_date,
            "custom_end_date": settings.time_filter.custom_end_date,
            "safe_search": settings.time_filter.safe_search,
            "enable_autocorrect": settings.time_filter.enable_autocorrect,
            "enable_serper_cache": settings.cache.enable_serper_cache,
            "enable_html_cache": settings.cache.enable_html_cache,
            "enable_fuzzy_cache_matching": False,  # Disabled by default
            "fuzzy_match_threshold": 98,
            "max_workers": settings.analysis.max_workers,

            # Auto Analysis
            "enable_auto_analysis": True,  # Default enabled

            # HTML Analysis settings
            "html_timeout": settings.analysis.html_timeout,
            "html_quality_threshold": settings.analysis.html_quality_threshold,
            "html_threshold_legit": settings.pdf_scoring.threshold_legit,
            "html_threshold_maybe": settings.pdf_scoring.threshold_maybe,

            # PDF Analysis settings
            "pdf_timeout": settings.analysis.pdf_timeout,
            "pdf_quality_threshold": settings.analysis.pdf_quality_threshold,
            "pdf_max_size_mb": settings.analysis.pdf_max_size_mb,
            "pdf_max_pages": settings.analysis.pdf_max_pages or 2000,
            "pdf_threshold_legit": settings.pdf_scoring.threshold_legit,
            "pdf_threshold_maybe": settings.pdf_scoring.threshold_maybe,
            "fast_lane_timeout": settings.background.fast_lane_timeout,
            "bg_download_timeout": settings.background.download_timeout,
            "bg_processing_timeout": settings.background.processing_timeout,

            # General processing
            "max_download_workers": settings.analysis.max_download_workers,
            "url_timeout": settings.analysis.url_timeout,
            "max_retry_attempts": settings.analysis.max_retry_attempts,
            "retry_delay": settings.analysis.retry_delay,
            "rate_limit_per_domain": settings.analysis.rate_limit_per_domain,
            "rate_limit_delay": settings.analysis.rate_limit_delay,

            # Semantic Search (Search V3)
            "semantic_similarity_threshold": settings.embedding.similarity_threshold,
            "semantic_max_results": settings.embedding.max_search_results,
        }

    # Main search input (always visible)
    query = st.text_input(
        "Search Query",
        value=st.session_state.search_params_v2["query"],
        placeholder="Enter your search query (e.g., latest AI developments)",
        key="v2_query",
        label_visibility="collapsed"
    )
    st.session_state.search_params_v2["query"] = query

    # Search button and Auto Analysis toggle (always visible)
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    with col2:
        clear_clicked = st.button("🔄 Reset", use_container_width=True)
    with col3:
        enable_auto_analysis = st.checkbox(
            "🤖 Auto Analysis (analyze all results)",
            value=st.session_state.search_params_v2["enable_auto_analysis"],
            key="v2_enable_auto_analysis",
            help="Automatically analyze all search results when search completes"
        )
        st.session_state.search_params_v2["enable_auto_analysis"] = enable_auto_analysis

    if clear_clicked:
        # Reset to defaults
        st.session_state.search_params_v2 = {
            # Search settings
            "query": settings.search.default_query,
            "search_type": settings.search.search_type,
            "provider": getattr(settings.search, "default_provider", "serper"),
            "enable_document_search": settings.results.enable_document_search,
            "num_results": settings.results.num_results,
            "country": settings.geographic.country,
            "language": settings.geographic.language,
            "location": settings.geographic.location,
            "time_filter": settings.time_filter.time_filter,
            "custom_start_date": settings.time_filter.custom_start_date,
            "custom_end_date": settings.time_filter.custom_end_date,
            "safe_search": settings.time_filter.safe_search,
            "enable_autocorrect": settings.time_filter.enable_autocorrect,
            "enable_serper_cache": settings.cache.enable_serper_cache,
            "enable_html_cache": settings.cache.enable_html_cache,
            "enable_fuzzy_cache_matching": False,
            "fuzzy_match_threshold": 98,
            "max_workers": settings.analysis.max_workers,

            # Auto Analysis
            "enable_auto_analysis": True,

            # HTML Analysis settings
            "html_timeout": settings.analysis.html_timeout,
            "html_quality_threshold": settings.analysis.html_quality_threshold,
            "html_threshold_legit": settings.pdf_scoring.threshold_legit,
            "html_threshold_maybe": settings.pdf_scoring.threshold_maybe,

            # PDF Analysis settings
            "pdf_timeout": settings.analysis.pdf_timeout,
            "pdf_quality_threshold": settings.analysis.pdf_quality_threshold,
            "pdf_max_size_mb": settings.analysis.pdf_max_size_mb,
            "pdf_max_pages": settings.analysis.pdf_max_pages or 2000,
            "pdf_threshold_legit": settings.pdf_scoring.threshold_legit,
            "pdf_threshold_maybe": settings.pdf_scoring.threshold_maybe,
            "fast_lane_timeout": settings.background.fast_lane_timeout,
            "bg_download_timeout": settings.background.download_timeout,
            "bg_processing_timeout": settings.background.processing_timeout,

            # General processing
            "max_download_workers": settings.analysis.max_download_workers,
            "url_timeout": settings.analysis.url_timeout,
            "max_retry_attempts": settings.analysis.max_retry_attempts,
            "retry_delay": settings.analysis.retry_delay,
            "rate_limit_per_domain": settings.analysis.rate_limit_per_domain,
            "rate_limit_delay": settings.analysis.rate_limit_delay,

            # Semantic Search (Search V3)
            "semantic_similarity_threshold": settings.embedding.similarity_threshold,
            "semantic_max_results": settings.embedding.max_search_results,
        }
        st.rerun()

    # Collapsible advanced settings with TABS
    with st.expander("⚙️ Advanced Settings", expanded=False):

        # Create four tabs: Search, HTML Analysis, PDF Analysis, Semantic Search
        tab1, tab2, tab3, tab4 = st.tabs(["🔍 Search Settings", "🌐 HTML Analysis", "📄 PDF Analysis", "🎯 Semantic Search (V3)"])

        # ========== TAB 1: Search Settings ==========
        with tab1:
            # Search Engine Provider & Type Options
            st.markdown("#### Search Engine & Type")
            col1, col2, col3 = st.columns(3)
            with col1:
                provider_choice = st.selectbox(
                    "Search Engine",
                    options=["Google (Serper)", "DuckDuckGo"],
                    index=1 if st.session_state.search_params_v2.get("provider") == "ddg" else 0,
                    key="v2_provider_choice"
                )
                st.session_state.search_params_v2["provider"] = "ddg" if "DuckDuckGo" in provider_choice else "serper"

            with col2:
                search_type = st.selectbox(
                    "Search Type",
                    options=["search", "news", "videos", "scholar"],
                    index=["search", "news", "videos", "scholar"].index(st.session_state.search_params_v2["search_type"]),
                    key="v2_search_type"
                )
                st.session_state.search_params_v2["search_type"] = search_type

            with col3:
                enable_document_search = st.checkbox(
                    "Enable Document Search (add 'pdf' to query)",
                    value=st.session_state.search_params_v2["enable_document_search"],
                    key="v2_enable_document_search"
                )
                st.session_state.search_params_v2["enable_document_search"] = enable_document_search

            # Results Settings
            st.markdown("#### Results Settings")
            col1, col2 = st.columns(2)
            with col1:
                num_results = st.number_input(
                    "Number of Results",
                    min_value=1,
                    max_value=100,
                    value=st.session_state.search_params_v2["num_results"],
                    key="v2_num_results"
                )
                st.session_state.search_params_v2["num_results"] = num_results

            with col2:
                max_workers = st.number_input(
                    "Max Workers (parallel processing)",
                    min_value=1,
                    max_value=50,
                    value=st.session_state.search_params_v2["max_workers"],
                    key="v2_max_workers"
                )
                st.session_state.search_params_v2["max_workers"] = max_workers

            # Geographic & Language Settings
            st.markdown("#### Geographic & Language")
            col1, col2, col3 = st.columns(3)
            with col1:
                country = st.text_input(
                    "Country Code (gl)",
                    value=st.session_state.search_params_v2["country"],
                    placeholder="e.g., us, uk, in",
                    help="ISO 3166-1 alpha-2 country code. Leave blank for no filter.",
                    key="v2_country"
                )
                st.session_state.search_params_v2["country"] = country

            with col2:
                language = st.text_input(
                    "Language Code (hl)",
                    value=st.session_state.search_params_v2["language"],
                    placeholder="e.g., en, es, fr",
                    help="ISO 639-1 language code",
                    key="v2_language"
                )
                st.session_state.search_params_v2["language"] = language

            with col3:
                location = st.text_input(
                    "Location",
                    value=st.session_state.search_params_v2["location"],
                    placeholder="e.g., New York, USA",
                    help="Human-readable location. Leave blank for no filter.",
                    key="v2_location"
                )
                st.session_state.search_params_v2["location"] = location

            # Time Filters
            st.markdown("#### Time Filters & Safety")
            col1, col2 = st.columns(2)
            with col1:
                time_filter_options = [None, "day", "week", "month", "year", "custom"]
                time_filter_labels = ["None", "Past Day", "Past Week", "Past Month", "Past Year", "Custom Range"]
                current_filter = st.session_state.search_params_v2["time_filter"]
                current_index = time_filter_options.index(current_filter) if current_filter in time_filter_options else 0

                time_filter = st.selectbox(
                    "Time Filter",
                    options=time_filter_options,
                    format_func=lambda x: time_filter_labels[time_filter_options.index(x)],
                    index=current_index,
                    key="v2_time_filter"
                )
                st.session_state.search_params_v2["time_filter"] = time_filter

            with col2:
                safe_search = st.selectbox(
                    "Safe Search",
                    options=["off", "active"],
                    index=["off", "active"].index(st.session_state.search_params_v2["safe_search"]),
                    key="v2_safe_search"
                )
                st.session_state.search_params_v2["safe_search"] = safe_search

            # Custom date range (only if time_filter == custom)
            if time_filter == "custom":
                col1, col2 = st.columns(2)
                with col1:
                    custom_start_date = st.date_input(
                        "Start Date",
                        value=None,
                        key="v2_custom_start_date"
                    )
                    if custom_start_date:
                        st.session_state.search_params_v2["custom_start_date"] = custom_start_date.strftime("%Y-%m-%d")
                    else:
                        st.session_state.search_params_v2["custom_start_date"] = None

                with col2:
                    custom_end_date = st.date_input(
                        "End Date",
                        value=None,
                        key="v2_custom_end_date"
                    )
                    if custom_end_date:
                        st.session_state.search_params_v2["custom_end_date"] = custom_end_date.strftime("%Y-%m-%d")
                    else:
                        st.session_state.search_params_v2["custom_end_date"] = None

            # Autocorrect
            enable_autocorrect = st.checkbox(
                "Enable Autocorrect",
                value=st.session_state.search_params_v2["enable_autocorrect"],
                help="Automatically correct spelling mistakes in query",
                key="v2_enable_autocorrect"
            )
            st.session_state.search_params_v2["enable_autocorrect"] = enable_autocorrect

            # Cache Settings
            st.markdown("#### Cache Settings")
            col1, col2 = st.columns(2)
            with col1:
                enable_serper_cache = st.checkbox(
                    "Enable Serper Cache",
                    value=st.session_state.search_params_v2["enable_serper_cache"],
                    help="Cache Serper API results to reduce API calls",
                    key="v2_enable_serper_cache"
                )
                st.session_state.search_params_v2["enable_serper_cache"] = enable_serper_cache

            with col2:
                enable_html_cache = st.checkbox(
                    "Enable HTML Cache",
                    value=st.session_state.search_params_v2["enable_html_cache"],
                    help="Cache HTML processing results",
                    key="v2_enable_html_cache"
                )
                st.session_state.search_params_v2["enable_html_cache"] = enable_html_cache

            col1, col2 = st.columns(2)
            with col1:
                enable_fuzzy_cache_matching = st.checkbox(
                    "Enable Fuzzy Cache Matching",
                    value=st.session_state.search_params_v2["enable_fuzzy_cache_matching"],
                    help="Use similarity-based matching for cached queries",
                    key="v2_enable_fuzzy_cache_matching"
                )
                st.session_state.search_params_v2["enable_fuzzy_cache_matching"] = enable_fuzzy_cache_matching

            with col2:
                fuzzy_match_threshold = st.slider(
                    "Fuzzy Match Threshold (%)",
                    min_value=50,
                    max_value=100,
                    value=st.session_state.search_params_v2["fuzzy_match_threshold"],
                    help="Minimum similarity score for fuzzy matching (higher = stricter)",
                    key="v2_fuzzy_match_threshold"
                )
                st.session_state.search_params_v2["fuzzy_match_threshold"] = fuzzy_match_threshold

        # ========== TAB 2: HTML Analysis Settings ==========
        with tab2:
            st.markdown("#### Timeouts")
            col1, col2 = st.columns(2)
            with col1:
                html_timeout = st.number_input(
                    "HTML Download Timeout (seconds)",
                    min_value=1,
                    max_value=60,
                    value=st.session_state.search_params_v2["html_timeout"],
                    help="Maximum time to wait for HTML download",
                    key="v2_html_timeout"
                )
                st.session_state.search_params_v2["html_timeout"] = html_timeout

            with col2:
                url_timeout = st.number_input(
                    "URL Timeout (seconds)",
                    min_value=1,
                    max_value=30,
                    value=st.session_state.search_params_v2["url_timeout"],
                    help="General URL request timeout",
                    key="v2_url_timeout"
                )
                st.session_state.search_params_v2["url_timeout"] = url_timeout

            st.markdown("#### Quality Scoring Thresholds")
            st.caption("Score range: 0-100. Results are classified based on final score.")

            col1, col2 = st.columns(2)
            with col1:
                html_threshold_legit = st.number_input(
                    "Legit Threshold (≥ score = PASS)",
                    min_value=0,
                    max_value=100,
                    value=st.session_state.search_params_v2["html_threshold_legit"],
                    help="Scores at or above this are marked as 'legit' (high quality)",
                    key="v2_html_threshold_legit"
                )
                st.session_state.search_params_v2["html_threshold_legit"] = html_threshold_legit

            with col2:
                html_threshold_maybe = st.number_input(
                    "Maybe Threshold (≥ score = MAYBE)",
                    min_value=0,
                    max_value=100,
                    value=st.session_state.search_params_v2["html_threshold_maybe"],
                    help="Scores at or above this but below legit are marked as 'maybe' (medium quality)",
                    key="v2_html_threshold_maybe"
                )
                st.session_state.search_params_v2["html_threshold_maybe"] = html_threshold_maybe

            html_quality_threshold = st.number_input(
                "Minimum Quality Filter (< score = FILTERED)",
                min_value=0,
                max_value=100,
                value=st.session_state.search_params_v2["html_quality_threshold"],
                help="Results below this score are filtered out entirely",
                key="v2_html_quality_threshold"
            )
            st.session_state.search_params_v2["html_quality_threshold"] = html_quality_threshold

            st.markdown("#### Processing Settings")
            col1, col2 = st.columns(2)
            with col1:
                max_retry_attempts = st.number_input(
                    "Max Retry Attempts",
                    min_value=0,
                    max_value=5,
                    value=st.session_state.search_params_v2["max_retry_attempts"],
                    help="Number of times to retry failed downloads",
                    key="v2_max_retry_attempts"
                )
                st.session_state.search_params_v2["max_retry_attempts"] = max_retry_attempts

            with col2:
                retry_delay = st.number_input(
                    "Retry Delay (seconds)",
                    min_value=0,
                    max_value=10,
                    value=st.session_state.search_params_v2["retry_delay"],
                    help="Time to wait between retries",
                    key="v2_retry_delay"
                )
                st.session_state.search_params_v2["retry_delay"] = retry_delay

            col1, col2 = st.columns(2)
            with col1:
                rate_limit_per_domain = st.number_input(
                    "Rate Limit per Domain",
                    min_value=1,
                    max_value=20,
                    value=st.session_state.search_params_v2["rate_limit_per_domain"],
                    help="Max concurrent requests to same domain",
                    key="v2_rate_limit_per_domain"
                )
                st.session_state.search_params_v2["rate_limit_per_domain"] = rate_limit_per_domain

            with col2:
                rate_limit_delay = st.number_input(
                    "Rate Limit Delay (seconds)",
                    min_value=0.0,
                    max_value=5.0,
                    value=st.session_state.search_params_v2["rate_limit_delay"],
                    step=0.1,
                    format="%.1f",
                    help="Delay between requests to same domain",
                    key="v2_rate_limit_delay"
                )
                st.session_state.search_params_v2["rate_limit_delay"] = rate_limit_delay

        # ========== TAB 3: PDF Analysis Settings ==========
        with tab3:
            st.markdown("#### Timeouts")
            col1, col2 = st.columns(2)
            with col1:
                pdf_timeout = st.number_input(
                    "PDF Download Timeout (seconds)",
                    min_value=1,
                    max_value=120,
                    value=st.session_state.search_params_v2["pdf_timeout"],
                    help="Maximum time to wait for PDF download",
                    key="v2_pdf_timeout"
                )
                st.session_state.search_params_v2["pdf_timeout"] = pdf_timeout

            with col2:
                fast_lane_timeout = st.number_input(
                    "Fast Lane Timeout (seconds)",
                    min_value=1,
                    max_value=30,
                    value=st.session_state.search_params_v2["fast_lane_timeout"],
                    help="Fast lane processing timeout before going to background queue",
                    key="v2_fast_lane_timeout"
                )
                st.session_state.search_params_v2["fast_lane_timeout"] = fast_lane_timeout

            st.markdown("#### Background Queue Timeouts")
            st.caption("These timeouts apply to PDFs moved to background queue (don't affect user-facing results)")

            col1, col2 = st.columns(2)
            with col1:
                bg_download_timeout = st.number_input(
                    "Background Download Timeout (seconds)",
                    min_value=1,
                    max_value=300,
                    value=st.session_state.search_params_v2.get("bg_download_timeout", 60),
                    help="Maximum time for background PDF download (can be longer)",
                    key="v2_bg_download_timeout"
                )
                st.session_state.search_params_v2["bg_download_timeout"] = bg_download_timeout

            with col2:
                bg_processing_timeout = st.number_input(
                    "Background Processing Timeout (seconds)",
                    min_value=1,
                    max_value=300,
                    value=st.session_state.search_params_v2.get("bg_processing_timeout", 60),
                    help="Maximum time for background PDF processing (can be longer)",
                    key="v2_bg_processing_timeout"
                )
                st.session_state.search_params_v2["bg_processing_timeout"] = bg_processing_timeout

            st.markdown("#### PDF Limits")
            col1, col2 = st.columns(2)
            with col1:
                pdf_max_size_mb = st.number_input(
                    "Max PDF Size (MB)",
                    min_value=1,
                    max_value=200,
                    value=st.session_state.search_params_v2["pdf_max_size_mb"],
                    help="Maximum PDF file size to download",
                    key="v2_pdf_max_size_mb"
                )
                st.session_state.search_params_v2["pdf_max_size_mb"] = pdf_max_size_mb

            with col2:
                pdf_max_pages = st.number_input(
                    "Max Pages to Process",
                    min_value=1,
                    max_value=5000,
                    value=st.session_state.search_params_v2["pdf_max_pages"],
                    help="Maximum number of pages to extract (limits processing time)",
                    key="v2_pdf_max_pages"
                )
                st.session_state.search_params_v2["pdf_max_pages"] = pdf_max_pages

            st.markdown("#### Quality Scoring Thresholds")
            st.caption("Score range: 0-100. Results are classified based on final score.")

            col1, col2 = st.columns(2)
            with col1:
                pdf_threshold_legit = st.number_input(
                    "Legit Threshold (≥ score = PASS)",
                    min_value=0,
                    max_value=100,
                    value=st.session_state.search_params_v2["pdf_threshold_legit"],
                    help="Scores at or above this are marked as 'legit' (high quality)",
                    key="v2_pdf_threshold_legit"
                )
                st.session_state.search_params_v2["pdf_threshold_legit"] = pdf_threshold_legit

            with col2:
                pdf_threshold_maybe = st.number_input(
                    "Maybe Threshold (≥ score = MAYBE)",
                    min_value=0,
                    max_value=100,
                    value=st.session_state.search_params_v2["pdf_threshold_maybe"],
                    help="Scores at or above this but below legit are marked as 'maybe' (medium quality)",
                    key="v2_pdf_threshold_maybe"
                )
                st.session_state.search_params_v2["pdf_threshold_maybe"] = pdf_threshold_maybe

            pdf_quality_threshold = st.number_input(
                "Minimum Quality Filter (< score = FILTERED)",
                min_value=0,
                max_value=100,
                value=st.session_state.search_params_v2["pdf_quality_threshold"],
                help="Results below this score are filtered out entirely",
                key="v2_pdf_quality_threshold"
            )
            st.session_state.search_params_v2["pdf_quality_threshold"] = pdf_quality_threshold

            st.markdown("#### Download Settings")
            max_download_workers = st.number_input(
                "Max Download Workers (parallel PDF downloads)",
                min_value=1,
                max_value=20,
                value=st.session_state.search_params_v2["max_download_workers"],
                help="Number of concurrent PDF downloads",
                key="v2_max_download_workers"
            )
            st.session_state.search_params_v2["max_download_workers"] = max_download_workers

        # ========== TAB 4: Semantic Search Settings (Search V3 Only) ==========
        with tab4:
            st.markdown("#### 🎯 Semantic Search Settings")
            st.caption("These settings apply to Search V3's semantic search feature. Available in the 'Semantic Matches' tab after auto-analysis completes.")

            col1, col2 = st.columns(2)
            with col1:
                semantic_similarity_threshold = st.slider(
                    "Similarity Threshold",
                    min_value=0.5,
                    max_value=1.0,
                    value=st.session_state.search_params_v2["semantic_similarity_threshold"],
                    step=0.05,
                    help="Minimum cosine similarity score (0-1) to include in results. Higher = more strict matching.",
                    key="v2_semantic_similarity_threshold"
                )
                st.session_state.search_params_v2["semantic_similarity_threshold"] = semantic_similarity_threshold

            with col2:
                semantic_max_results = st.number_input(
                    "Max Results",
                    min_value=5,
                    max_value=100,
                    value=st.session_state.search_params_v2["semantic_max_results"],
                    step=5,
                    help="Maximum number of semantic matches to return from search",
                    key="v2_semantic_max_results"
                )
                st.session_state.search_params_v2["semantic_max_results"] = semantic_max_results

            st.markdown("---")
            st.markdown("#### How Semantic Search Works")
            st.info("""
                **Semantic Search** uses AI embeddings to find the most relevant content chunks:

                1. 🔍 **After auto-analysis completes**, documents are embedded in the background (~30-60s)
                2. 🎯 **Your query is converted** to a vector embedding
                3. 📊 **Cosine similarity** compares your query against all document chunks
                4. ✨ **Results ranked by relevance**, not just quality score

                **Best for:** Finding specific information across many documents, even if the exact keywords aren't used.
            """)

        # ========== SAVE SETTINGS BUTTON ==========
        st.markdown("---")
        st.markdown("#### 💾 Save Settings to File")
        st.caption("Save current settings to `config/user_settings.json` (persists across sessions)")

        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("💾 Save Settings", type="primary", use_container_width=True, key="save_settings_btn"):
                try:
                    # Load current settings from file
                    current_settings = AppSettings.load(SETTINGS_FILE)

                    # Update settings from session state
                    # Search settings
                    current_settings.search.search_type = st.session_state.search_params_v2["search_type"]
                    current_settings.results.enable_document_search = st.session_state.search_params_v2["enable_document_search"]
                    current_settings.results.num_results = st.session_state.search_params_v2["num_results"]
                    current_settings.geographic.country = st.session_state.search_params_v2["country"]
                    current_settings.geographic.language = st.session_state.search_params_v2["language"]
                    current_settings.geographic.location = st.session_state.search_params_v2["location"]
                    current_settings.time_filter.time_filter = st.session_state.search_params_v2["time_filter"]
                    current_settings.time_filter.safe_search = st.session_state.search_params_v2["safe_search"]
                    current_settings.time_filter.enable_autocorrect = st.session_state.search_params_v2["enable_autocorrect"]
                    current_settings.cache.enable_serper_cache = st.session_state.search_params_v2["enable_serper_cache"]
                    current_settings.cache.enable_html_cache = st.session_state.search_params_v2["enable_html_cache"]

                    # HTML Analysis settings
                    current_settings.analysis.html_timeout = st.session_state.search_params_v2["html_timeout"]
                    current_settings.analysis.html_quality_threshold = st.session_state.search_params_v2["html_quality_threshold"]
                    current_settings.pdf_scoring.threshold_legit = st.session_state.search_params_v2["html_threshold_legit"]
                    current_settings.pdf_scoring.threshold_maybe = st.session_state.search_params_v2["html_threshold_maybe"]

                    # PDF Analysis settings
                    current_settings.analysis.pdf_timeout = st.session_state.search_params_v2["pdf_timeout"]
                    current_settings.analysis.pdf_quality_threshold = st.session_state.search_params_v2["pdf_quality_threshold"]
                    current_settings.analysis.pdf_max_size_mb = st.session_state.search_params_v2["pdf_max_size_mb"]
                    current_settings.analysis.pdf_max_pages = st.session_state.search_params_v2["pdf_max_pages"]
                    current_settings.background.fast_lane_timeout = st.session_state.search_params_v2["fast_lane_timeout"]
                    current_settings.background.download_timeout = st.session_state.search_params_v2["bg_download_timeout"]
                    current_settings.background.processing_timeout = st.session_state.search_params_v2["bg_processing_timeout"]

                    # General processing settings
                    current_settings.analysis.max_download_workers = st.session_state.search_params_v2["max_download_workers"]
                    current_settings.analysis.url_timeout = st.session_state.search_params_v2["url_timeout"]
                    current_settings.analysis.max_retry_attempts = st.session_state.search_params_v2["max_retry_attempts"]
                    current_settings.analysis.retry_delay = st.session_state.search_params_v2["retry_delay"]
                    current_settings.analysis.rate_limit_per_domain = st.session_state.search_params_v2["rate_limit_per_domain"]
                    current_settings.analysis.rate_limit_delay = st.session_state.search_params_v2["rate_limit_delay"]

                    # Semantic Search settings (Search V3)
                    current_settings.embedding.similarity_threshold = st.session_state.search_params_v2["semantic_similarity_threshold"]
                    current_settings.embedding.max_search_results = st.session_state.search_params_v2["semantic_max_results"]

                    # Save to file
                    current_settings.save(SETTINGS_FILE)
                    st.success("✅ Settings saved successfully to `config/user_settings.json`!")
                    st.info("⚠️ **Note:** Backend must be restarted to use new settings for analysis endpoints.")

                except Exception as e:
                    st.error(f"❌ Failed to save settings: {str(e)}")

        with col2:
            if st.button("🔄 Reload from File", use_container_width=True, key="reload_settings_btn"):
                try:
                    # Reload settings from file
                    settings = AppSettings.load(SETTINGS_FILE)

                    # Update session state from file
                    st.session_state.search_params_v2.update({
                        # Search settings
                        "search_type": settings.search.search_type,
                        "enable_document_search": settings.results.enable_document_search,
                        "num_results": settings.results.num_results,
                        "country": settings.geographic.country,
                        "language": settings.geographic.language,
                        "location": settings.geographic.location,
                        "time_filter": settings.time_filter.time_filter,
                        "safe_search": settings.time_filter.safe_search,
                        "enable_autocorrect": settings.time_filter.enable_autocorrect,
                        "enable_serper_cache": settings.cache.enable_serper_cache,
                        "enable_html_cache": settings.cache.enable_html_cache,

                        # HTML Analysis settings
                        "html_timeout": settings.analysis.html_timeout,
                        "html_quality_threshold": settings.analysis.html_quality_threshold,
                        "html_threshold_legit": settings.pdf_scoring.threshold_legit,
                        "html_threshold_maybe": settings.pdf_scoring.threshold_maybe,

                        # PDF Analysis settings
                        "pdf_timeout": settings.analysis.pdf_timeout,
                        "pdf_quality_threshold": settings.analysis.pdf_quality_threshold,
                        "pdf_max_size_mb": settings.analysis.pdf_max_size_mb,
                        "pdf_max_pages": settings.analysis.pdf_max_pages or 2000,
                        "pdf_threshold_legit": settings.pdf_scoring.threshold_legit,
                        "pdf_threshold_maybe": settings.pdf_scoring.threshold_maybe,
                        "fast_lane_timeout": settings.background.fast_lane_timeout,
                        "bg_download_timeout": settings.background.download_timeout,
                        "bg_processing_timeout": settings.background.processing_timeout,

                        # General processing
                        "max_download_workers": settings.analysis.max_download_workers,
                        "url_timeout": settings.analysis.url_timeout,
                        "max_retry_attempts": settings.analysis.max_retry_attempts,
                        "retry_delay": settings.analysis.retry_delay,
                        "rate_limit_per_domain": settings.analysis.rate_limit_per_domain,
                        "rate_limit_delay": settings.analysis.rate_limit_delay,

                        # Semantic Search (Search V3)
                        "semantic_similarity_threshold": settings.embedding.similarity_threshold,
                        "semantic_max_results": settings.embedding.max_search_results,
                    })

                    st.success("✅ Settings reloaded from `config/user_settings.json`!")
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Failed to reload settings: {str(e)}")

    return {
        "search_clicked": search_clicked,
        "params": st.session_state.search_params_v2
    }
