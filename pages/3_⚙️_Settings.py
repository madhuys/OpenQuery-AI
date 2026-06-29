"""
Settings Page for OpenQuery AI
Comprehensive settings management with all configurable parameters
"""
import streamlit as st
import json
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.settings import (
    AppSettings,
    SUPPORTED_COUNTRIES,
    SUPPORTED_LANGUAGES,
    EXAMPLE_LOCATIONS,
    SETTINGS_FILE
)

# Page config
st.set_page_config(
    page_title="Settings - OpenQuery AI",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Application Settings")

st.markdown("Configure all parameters for search, analysis, and caching.")

# Always reload settings from file on each page load
# This ensures the UI always shows the current saved values
if os.path.exists(SETTINGS_FILE):
    settings = AppSettings.load(SETTINGS_FILE)
    # DEBUG: Show what was loaded
    st.caption(f"🔧 Loaded fuzzy_match_threshold: {settings.cache.fuzzy_match_threshold}")
else:
    settings = AppSettings()
    st.info("ℹ️ Using default settings (will be saved on first change)")

# Create tabs for different setting sections
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🔍 Search",
    "🌍 Geographic & Language",
    "📊 Results",
    "⏰ Time & Safety",
    "⚡ Analysis",
    "💾 Cache",
    "🧠 Embeddings",
    "💬 About"
])

# ===== TAB 1: SEARCH SETTINGS =====
with tab1:
    st.header("🔍 Search Engine & Query Settings")

    col1, col2, col3 = st.columns(3)

    with col1:
        default_provider = st.selectbox(
            "Default Search Engine",
            options=["Google (Serper)", "DuckDuckGo"],
            index=1 if getattr(settings.search, "default_provider", "serper") == "ddg" else 0,
            help="The default search engine provider when starting the application"
        )
        settings.search.default_provider = "ddg" if "DuckDuckGo" in default_provider else "serper"

    with col2:
        search_type = st.selectbox(
            "Default Search Type",
            options=["search", "news", "videos", "scholar"],
            index=["search", "news", "videos", "scholar"].index(settings.search.search_type),
            help="The default search type when starting the application"
        )
        settings.search.search_type = search_type

    with col3:
        default_query = st.text_input(
            "Default Query",
            value=settings.search.default_query,
            help="The default search query when starting the application"
        )
        settings.search.default_query = default_query

    st.markdown("---")
    st.caption("💡 These settings control the default search behavior when you open the app.")

    # Save button for Tab 1
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab1", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 2: GEOGRAPHIC & LANGUAGE SETTINGS =====
with tab2:
    st.header("🌍 Geographic & Language Settings")

    st.subheader("Country (gl)")
    st.caption("ISO 3166-1 alpha-2 country code. Affects search results regionalization.")

    # Country selection
    country_options = [""] + list(SUPPORTED_COUNTRIES.keys())
    country_labels = ["(None)"] + [f"{code} - {name}" for code, name in SUPPORTED_COUNTRIES.items()]

    current_country_index = country_options.index(settings.geographic.country) if settings.geographic.country in country_options else 0

    selected_country_label = st.selectbox(
        "Select Country",
        options=country_labels,
        index=current_country_index,
        help="Select country for search regionalization"
    )

    # Extract country code from label
    if selected_country_label == "(None)":
        settings.geographic.country = ""
    else:
        settings.geographic.country = selected_country_label.split(" - ")[0]

    st.markdown("---")

    st.subheader("Language (hl)")
    st.caption("ISO 639-1 language code. Affects UI language and result preferences.")

    # Language selection
    language_options = [""] + list(SUPPORTED_LANGUAGES.keys())
    language_labels = ["(None)"] + [f"{code} - {name}" for code, name in SUPPORTED_LANGUAGES.items()]

    current_language_index = language_options.index(settings.geographic.language) if settings.geographic.language in language_options else 0

    selected_language_label = st.selectbox(
        "Select Language",
        options=language_labels,
        index=current_language_index,
        help="Select language for search interface"
    )

    # Extract language code from label
    if selected_language_label == "(None)":
        settings.geographic.language = ""
    else:
        settings.geographic.language = selected_language_label.split(" - ")[0]

    st.markdown("---")

    st.subheader("Location")
    st.caption("Human-readable location string. Optional, provides more precise geolocation.")

    location = st.text_input(
        "Location (free text)",
        value=settings.geographic.location,
        placeholder="e.g., New York, United States",
        help="Enter any location in human-readable format"
    )
    settings.geographic.location = location

    # Show examples
    with st.expander("📍 Example Locations", expanded=False):
        st.markdown("**Common locations you can use:**")
        for loc in EXAMPLE_LOCATIONS[:10]:
            st.code(loc, language=None)
        st.caption(f"...and {len(EXAMPLE_LOCATIONS) - 10} more")

    # Save button for Tab 2
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab2", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 3: RESULT SETTINGS =====
with tab3:
    st.header("📊 Result Settings")

    st.subheader("Number of Results")
    num_results = st.slider(
        "Results per search type",
        min_value=1,
        max_value=100,
        value=settings.results.num_results,
        help="Number of results to fetch per search type (max 100)"
    )
    settings.results.num_results = num_results

    # Calculate pages needed
    pages_needed = (num_results + 9) // 10
    if pages_needed > 1:
        st.info(f"ℹ️ Will fetch **{pages_needed} pages** ({num_results} results total)")

    st.markdown("---")

    st.subheader("Expanded Search")
    st.caption("Automatically search additional sources beyond the main search type")

    col1, col2, col3 = st.columns(3)

    with col1:
        enable_videos = st.checkbox(
            "Enable Videos Search",
            value=settings.results.enable_videos,
            help="Also search for videos when performing a search"
        )
        settings.results.enable_videos = enable_videos

    with col2:
        enable_scholar = st.checkbox(
            "Enable Scholar Search",
            value=settings.results.enable_scholar,
            help="Also search Google Scholar when performing a search"
        )
        settings.results.enable_scholar = enable_scholar

    with col3:
        enable_document_search = st.checkbox(
            "Enable Document Search",
            value=settings.results.enable_document_search,
            help="Add parallel search with ' pdf' appended to find documents (page 1 only, 10 results)"
        )
        settings.results.enable_document_search = enable_document_search

    # Total results calculation
    total_results = settings.results.total_results
    st.success(f"📊 **Total results across all searches:** {total_results}")

    if enable_videos or enable_scholar or enable_document_search:
        search_types_count = 1 + (1 if enable_videos else 0) + (1 if enable_scholar else 0) + (1 if enable_document_search else 0)
        st.warning(f"⚠️ Will perform **{search_types_count} separate searches** per query (main + expanded)")

    # Save button for Tab 3
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab3", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 4: TIME & SAFETY FILTERS =====
with tab4:
    st.header("⏰ Time Filters & Safety")

    st.subheader("Time Filter (tbs)")
    st.caption("Filter results by publication date")

    time_filter_options = ["None", "day", "week", "month", "year", "custom"]
    time_filter_labels = {
        "None": "No time filter",
        "day": "Past day (qdr:d)",
        "week": "Past week (qdr:w)",
        "month": "Past month (qdr:m)",
        "year": "Past year (qdr:y)",
        "custom": "Custom date range"
    }

    current_time_filter = settings.time_filter.time_filter or "None"
    selected_time_filter = st.selectbox(
        "Time filter",
        options=time_filter_options,
        index=time_filter_options.index(current_time_filter) if current_time_filter in time_filter_options else 0,
        format_func=lambda x: time_filter_labels[x],
        help="Filter results by time period"
    )
    settings.time_filter.time_filter = selected_time_filter if selected_time_filter != "None" else None

    # Custom date range (if selected)
    if selected_time_filter == "custom":
        col1, col2 = st.columns(2)

        with col1:
            start_date = st.date_input(
                "Start Date",
                value=datetime.strptime(settings.time_filter.custom_start_date, "%Y-%m-%d") if settings.time_filter.custom_start_date else datetime.now() - timedelta(days=30),
                help="Start date for custom range"
            )
            settings.time_filter.custom_start_date = start_date.strftime("%Y-%m-%d")

        with col2:
            end_date = st.date_input(
                "End Date",
                value=datetime.strptime(settings.time_filter.custom_end_date, "%Y-%m-%d") if settings.time_filter.custom_end_date else datetime.now(),
                help="End date for custom range"
            )
            settings.time_filter.custom_end_date = end_date.strftime("%Y-%m-%d")

        # Show the tbs value that will be used
        tbs_value = settings.time_filter.get_tbs_value()
        if tbs_value:
            st.code(f"tbs parameter: {tbs_value}", language=None)

    st.markdown("---")

    st.subheader("Safety & Autocorrect")

    col1, col2 = st.columns(2)

    with col1:
        safe_search = st.selectbox(
            "Safe Search",
            options=["off", "active"],
            index=0 if settings.time_filter.safe_search == "off" else 1,
            help="Enable or disable safe search filtering"
        )
        settings.time_filter.safe_search = safe_search

    with col2:
        enable_autocorrect = st.checkbox(
            "Enable Autocorrect",
            value=settings.time_filter.enable_autocorrect,
            help="Automatically correct spelling in search queries"
        )
        settings.time_filter.enable_autocorrect = enable_autocorrect

    # Save button for Tab 4
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab4", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 5: ANALYSIS SETTINGS =====
with tab5:
    st.header("⚡ Analysis & Processing Settings")

    st.subheader("Worker Settings")
    st.caption("Control parallelization and concurrency")

    col1, col2 = st.columns(2)

    with col1:
        max_workers = st.slider(
            "Total Max Workers",
            min_value=1,
            max_value=32,
            value=settings.analysis.max_workers,
            help="Maximum number of parallel workers for all processing tasks"
        )
        settings.analysis.max_workers = max_workers

    with col2:
        max_download_workers = st.slider(
            "PDF Download Workers",
            min_value=1,
            max_value=max_workers,
            value=min(settings.analysis.max_download_workers, max_workers),
            help="Maximum concurrent PDF downloads (limited by total workers)"
        )
        settings.analysis.max_download_workers = max_download_workers

    st.markdown("---")

    st.subheader("Timeout Settings (seconds)")
    st.caption("Maximum time to wait for different types of requests")

    col1, col2, col3 = st.columns(3)

    with col1:
        html_timeout = st.number_input(
            "HTML Timeout",
            min_value=1,
            max_value=60,
            value=settings.analysis.html_timeout,
            help="Timeout for HTML downloads (seconds)"
        )
        settings.analysis.html_timeout = html_timeout

    with col2:
        pdf_timeout = st.number_input(
            "PDF Timeout",
            min_value=1,
            max_value=120,
            value=settings.analysis.pdf_timeout,
            help="Timeout for PDF downloads (seconds)"
        )
        settings.analysis.pdf_timeout = pdf_timeout

    with col3:
        url_timeout = st.number_input(
            "URL Timeout",
            min_value=1,
            max_value=60,
            value=settings.analysis.url_timeout,
            help="General URL request timeout (seconds)"
        )
        settings.analysis.url_timeout = url_timeout

    # Advanced timeout settings
    with st.expander("⏱️ Advanced Timeout Settings", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            api_health_timeout = st.number_input(
                "API Health Check Timeout",
                min_value=1,
                max_value=30,
                value=settings.analysis.api_health_timeout,
                help="Timeout for API health/status checks (seconds)"
            )
            settings.analysis.api_health_timeout = api_health_timeout

            thread_join_timeout = st.number_input(
                "Thread Join Timeout",
                min_value=60,
                max_value=600,
                value=settings.analysis.thread_join_timeout,
                help="Background worker thread join timeout (seconds)"
            )
            settings.analysis.thread_join_timeout = thread_join_timeout

        with col2:
            api_stream_timeout = st.number_input(
                "API Streaming Timeout",
                min_value=60,
                max_value=600,
                value=settings.analysis.api_stream_timeout,
                help="Timeout for streaming API analysis (seconds)"
            )
            settings.analysis.api_stream_timeout = api_stream_timeout

            router_max_workers = st.number_input(
                "Router Max Workers",
                min_value=1,
                max_value=4,
                value=settings.analysis.router_max_workers,
                help="Router thread pool workers (usually 1 is sufficient)"
            )
            settings.analysis.router_max_workers = router_max_workers

        with col3:
            database_busy_timeout = st.number_input(
                "Database Busy Timeout",
                min_value=5,
                max_value=120,
                value=settings.analysis.database_busy_timeout,
                help="SQLite busy timeout (seconds)"
            )
            settings.analysis.database_busy_timeout = database_busy_timeout

            default_cache_freshness_days = st.number_input(
                "Default Cache Freshness (days)",
                min_value=1,
                max_value=90,
                value=settings.analysis.default_cache_freshness_days,
                help="Default cache freshness when not specified by content type"
            )
            settings.analysis.default_cache_freshness_days = default_cache_freshness_days

    st.markdown("---")

    st.subheader("Retry & Rate Limiting")

    col1, col2 = st.columns(2)

    with col1:
        max_retry_attempts = st.number_input(
            "Max Retry Attempts",
            min_value=0,
            max_value=5,
            value=settings.analysis.max_retry_attempts,
            help="Maximum retry attempts for failed requests"
        )
        settings.analysis.max_retry_attempts = max_retry_attempts

        retry_delay = st.number_input(
            "Retry Delay (seconds)",
            min_value=1,
            max_value=10,
            value=settings.analysis.retry_delay,
            help="Delay between retry attempts"
        )
        settings.analysis.retry_delay = retry_delay

    with col2:
        rate_limit_per_domain = st.number_input(
            "Rate Limit per Domain",
            min_value=1,
            max_value=10,
            value=settings.analysis.rate_limit_per_domain,
            help="Maximum concurrent requests to same domain"
        )
        settings.analysis.rate_limit_per_domain = rate_limit_per_domain

        rate_limit_delay = st.number_input(
            "Rate Limit Delay (seconds)",
            min_value=0.0,
            max_value=5.0,
            value=settings.analysis.rate_limit_delay,
            step=0.1,
            format="%.1f",
            help="Delay between requests to same domain"
        )
        settings.analysis.rate_limit_delay = rate_limit_delay

    st.markdown("---")

    st.subheader("Quality Filtering Thresholds")
    st.caption("Minimum quality scores to include content (0-100 scale)")

    col1, col2 = st.columns(2)

    with col1:
        html_quality_threshold = st.slider(
            "HTML Quality Threshold",
            min_value=0,
            max_value=100,
            value=settings.analysis.html_quality_threshold,
            help="Minimum quality score for HTML content (0-100)"
        )
        settings.analysis.html_quality_threshold = html_quality_threshold

    with col2:
        pdf_quality_threshold = st.slider(
            "PDF Quality Threshold",
            min_value=0,
            max_value=100,
            value=settings.analysis.pdf_quality_threshold,
            help="Minimum quality score for PDF content (0-100)"
        )
        settings.analysis.pdf_quality_threshold = pdf_quality_threshold

    st.markdown("---")

    st.subheader("PDF Specific Settings")

    col1, col2 = st.columns(2)

    with col1:
        pdf_max_size_mb = st.slider(
            "PDF Max Size (MB)",
            min_value=10,
            max_value=500,
            value=settings.analysis.pdf_max_size_mb,
            help="Maximum PDF file size to download"
        )
        settings.analysis.pdf_max_size_mb = pdf_max_size_mb

    with col2:
        pdf_max_pages = st.slider(
            "PDF Max Pages",
            min_value=10,
            max_value=2000,
            value=settings.analysis.pdf_max_pages,
            help="Maximum pages to extract from PDF"
        )
        settings.analysis.pdf_max_pages = pdf_max_pages

    # Save button for Tab 5
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab5", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 6: CACHE SETTINGS =====
with tab6:
    st.header("💾 Cache & Freshness Settings")
    st.caption("Control end-to-end cache behavior and staleness logic")

    # ========== Cache Enablement ==========
    st.subheader("🔧 Cache Enablement")
    st.caption("Enable or disable caching layers")

    col1, col2 = st.columns(2)

    with col1:
        enable_serper_cache = st.checkbox(
            "Serper API Cache",
            value=settings.cache.enable_serper_cache,
            help="Cache Serper API search results to avoid redundant API calls"
        )
        settings.cache.enable_serper_cache = enable_serper_cache

    with col2:
        enable_html_cache = st.checkbox(
            "HTML Processing Cache",
            value=settings.cache.enable_html_cache,
            help="Cache HTML processing and analysis results"
        )
        settings.cache.enable_html_cache = enable_html_cache

    st.markdown("---")

    # ========== Fuzzy Query Matching ==========
    st.subheader("🔍 Fuzzy Query Matching")
    st.caption("Control similarity-based query matching to reuse cached results for similar queries")

    enable_fuzzy_matching = st.checkbox(
        "Enable Fuzzy Cache Matching",
        value=settings.cache.enable_fuzzy_cache_matching,
        help="When enabled, queries similar to cached queries will reuse cached results (e.g., 'Japan fintech' won't match 'Africa fintech' if threshold is high enough)"
    )
    settings.cache.enable_fuzzy_cache_matching = enable_fuzzy_matching

    if enable_fuzzy_matching:
        fuzzy_match_threshold = st.slider(
            "Fuzzy Match Threshold (%)",
            min_value=50,
            max_value=100,
            value=settings.cache.fuzzy_match_threshold,
            help="Minimum similarity score (0-100) required for fuzzy matching. Higher = more strict. Default: 85. "
                 "At 85%, 'Japan fintech trends' and 'Africa fintech trends' won't match. "
                 "At 50%, they might match (too broad)."
        )
        settings.cache.fuzzy_match_threshold = fuzzy_match_threshold

        # Show threshold guidance
        if fuzzy_match_threshold >= 90:
            st.success(f"✅ **Very Strict** ({fuzzy_match_threshold}%) - Only nearly identical queries will match")
        elif fuzzy_match_threshold >= 80:
            st.info(f"ℹ️ **Strict** ({fuzzy_match_threshold}%) - Similar queries with minor differences will match (recommended)")
        elif fuzzy_match_threshold >= 70:
            st.warning(f"⚠️ **Moderate** ({fuzzy_match_threshold}%) - Somewhat different queries may match")
        else:
            st.error(f"❌ **Loose** ({fuzzy_match_threshold}%) - Very different queries may match (not recommended)")
    else:
        st.info("ℹ️ Fuzzy matching disabled. Only exact query matches will use cached results.")

    st.markdown("---")

    # ========== Serper Cache Freshness ==========
    st.subheader("🔍 Serper Cache Freshness (Hours)")
    st.caption("Individual freshness settings for each search type. No shared default.")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        serper_news_freshness_hours = st.number_input(
            "News",
            min_value=1,
            max_value=48,
            value=settings.cache.serper_news_freshness_hours,
            help="Freshness for news searches (default: 6 hours)"
        )
        settings.cache.serper_news_freshness_hours = serper_news_freshness_hours

    with col2:
        serper_search_freshness_hours = st.number_input(
            "General Search",
            min_value=1,
            max_value=168,
            value=settings.cache.serper_search_freshness_hours,
            help="Freshness for general searches (default: 24 hours)"
        )
        settings.cache.serper_search_freshness_hours = serper_search_freshness_hours

    with col3:
        serper_videos_freshness_hours = st.number_input(
            "Videos",
            min_value=1,
            max_value=168,
            value=settings.cache.serper_videos_freshness_hours,
            help="Freshness for video searches (default: 48 hours)"
        )
        settings.cache.serper_videos_freshness_hours = serper_videos_freshness_hours

    with col4:
        serper_scholar_freshness_hours = st.number_input(
            "Scholar",
            min_value=1,
            max_value=720,  # 30 days
            value=settings.cache.serper_scholar_freshness_hours,
            help="Freshness for scholar searches (default: 168 hours / 7 days)"
        )
        settings.cache.serper_scholar_freshness_hours = serper_scholar_freshness_hours

    st.markdown("---")

    # ========== HTML Cache Freshness ==========
    st.subheader("🌐 HTML Cache Freshness (Days)")
    st.caption("Individual staleness settings for each content type. No shared default.")

    col1, col2, col3 = st.columns(3)

    with col1:
        html_news_staleness_days = st.number_input(
            "News Articles",
            min_value=1,
            max_value=30,
            value=settings.cache.html_news_staleness_days,
            help="Staleness for news articles (default: 7 days)"
        )
        settings.cache.html_news_staleness_days = html_news_staleness_days

        html_blog_staleness_days = st.number_input(
            "Blog Posts",
            min_value=1,
            max_value=30,
            value=settings.cache.html_blog_staleness_days,
            help="Staleness for blog posts (default: 7 days)"
        )
        settings.cache.html_blog_staleness_days = html_blog_staleness_days

    with col2:
        html_product_staleness_days = st.number_input(
            "Product Pages",
            min_value=1,
            max_value=90,
            value=settings.cache.html_product_staleness_days,
            help="Staleness for product pages (default: 30 days)"
        )
        settings.cache.html_product_staleness_days = html_product_staleness_days

        html_docs_staleness_days = st.number_input(
            "Documentation",
            min_value=1,
            max_value=90,
            value=settings.cache.html_docs_staleness_days,
            help="Staleness for documentation (default: 30 days)"
        )
        settings.cache.html_docs_staleness_days = html_docs_staleness_days

    with col3:
        html_evergreen_staleness_days = st.number_input(
            "Evergreen Content",
            min_value=1,
            max_value=365,
            value=settings.cache.html_evergreen_staleness_days,
            help="Staleness for evergreen content (default: 90 days)"
        )
        settings.cache.html_evergreen_staleness_days = html_evergreen_staleness_days

        html_unknown_staleness_days = st.number_input(
            "Unknown Content",
            min_value=1,
            max_value=90,
            value=settings.cache.html_unknown_staleness_days,
            help="Staleness for unknown content type (default: 30 days)"
        )
        settings.cache.html_unknown_staleness_days = html_unknown_staleness_days

    st.markdown("---")

    # ========== URL Revalidation Settings ==========
    st.subheader("🔄 URL Revalidation Threshold")
    st.caption("Automatically revalidate URLs if last fetch exceeds threshold")

    revalidation_threshold_days = st.number_input(
        "Revalidation Threshold (days)",
        min_value=1,
        max_value=90,
        value=settings.cache.revalidation_threshold_days,
        help="Revalidate URLs if last fetch was > N days ago (default: 15 days)"
    )
    settings.cache.revalidation_threshold_days = revalidation_threshold_days

    st.info(f"📌 **Revalidation Logic:** If a URL was last fetched more than {revalidation_threshold_days} days ago, it will be revalidated (checked for freshness) before reusing cached content.")

    st.markdown("---")

    # ========== Error & Filtered Cache ==========
    st.subheader("❌ Error & Filtered Cache (Days)")
    st.caption("How long to remember failed and filtered URLs")

    col1, col2 = st.columns(2)

    with col1:
        error_cache_days = st.number_input(
            "Error Cache TTL (days)",
            min_value=1,
            max_value=90,
            value=settings.cache.error_cache_days,
            help="Days to remember failed URLs to avoid retry spam (default: 15)"
        )
        settings.cache.error_cache_days = error_cache_days

    with col2:
        filtered_cache_days = st.number_input(
            "Filtered Cache TTL (days)",
            min_value=1,
            max_value=90,
            value=settings.cache.filtered_cache_days,
            help="Days to remember filtered URLs (low quality) (default: 15)"
        )
        settings.cache.filtered_cache_days = filtered_cache_days

    st.markdown("---")

    # ========== Cache Size Limits ==========
    st.subheader("📦 Cache Size Limit")

    max_cache_size_gb = st.number_input(
        "Max Cache Size (GB)",
        min_value=1,
        max_value=1000,
        value=settings.cache.max_cache_size_gb,
        help="Maximum cache database size in GB (default: 100 GB)"
    )
    settings.cache.max_cache_size_gb = max_cache_size_gb

    # Cache statistics (if available)
    st.markdown("---")
    st.subheader("📊 Cache Statistics")

    try:
        from services.cache_service import CacheService
        cache_service = CacheService()
        stats = cache_service.get_database_stats()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total URLs", stats.get('total_urls', 0))
        with col2:
            st.metric("Cached HTML", stats.get('cached_analyses', 0))
        with col3:
            # Calculate cache size
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "serper_cache.db")
            if os.path.exists(db_path):
                cache_size_bytes = os.path.getsize(db_path)
                cache_size_gb = cache_size_bytes / (1024 * 1024 * 1024)
                if cache_size_gb >= 1:
                    st.metric("Cache Size", f"{cache_size_gb:.2f} GB")
                else:
                    cache_size_mb = cache_size_bytes / (1024 * 1024)
                    st.metric("Cache Size", f"{cache_size_mb:.1f} MB")
            else:
                st.metric("Cache Size", "0 MB")
    except Exception as e:
        st.warning(f"⚠️ Could not load cache statistics: {e}")

    # Save button for Tab 6
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab6", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 7: EMBEDDING SETTINGS =====
with tab7:
    st.header("🧠 Semantic Search & Embedding Settings")
    st.caption("Configure Azure OpenAI embeddings for semantic search")

    # ========== Feature Toggle ==========
    st.subheader("🔧 Feature Enablement")

    enable_embeddings = st.checkbox(
        "Enable Embeddings & Semantic Search",
        value=settings.embedding.enabled,
        help="Generate embeddings for documents and enable semantic search functionality"
    )
    settings.embedding.enabled = enable_embeddings

    if not enable_embeddings:
        st.warning("⚠️ Embeddings are disabled. Semantic search will not be available.")
        st.info("💡 Enable embeddings to use the Live Search feature with AI-powered semantic ranking")

    st.markdown("---")

    # ========== Azure OpenAI Configuration ==========
    st.subheader("🔑 Azure OpenAI Configuration")
    st.caption("Configure your Azure OpenAI endpoint and API key")

    col1, col2 = st.columns(2)

    with col1:
        azure_endpoint = st.text_input(
            "Azure Endpoint",
            value=settings.embedding.azure_endpoint,
            help="Your Azure OpenAI endpoint URL",
            type="default"
        )
        settings.embedding.azure_endpoint = azure_endpoint

        model_name = st.text_input(
            "Model Name",
            value=settings.embedding.model_name,
            help="Embedding model name (e.g., text-embedding-3-small)"
        )
        settings.embedding.model_name = model_name

    with col2:
        api_key = st.text_input(
            "API Key",
            value=settings.embedding.api_key,
            help="Your Azure OpenAI API key",
            type="password"
        )
        settings.embedding.api_key = api_key

        deployment_name = st.text_input(
            "Deployment Name",
            value=settings.embedding.deployment_name,
            help="Your Azure deployment name"
        )
        settings.embedding.deployment_name = deployment_name

    api_version = st.text_input(
        "API Version",
        value=settings.embedding.api_version,
        help="Azure OpenAI API version"
    )
    settings.embedding.api_version = api_version

    st.markdown("---")

    # ========== Batch Processing ==========
    st.subheader("⚡ Batch Processing")

    max_chunk_batch_size = st.slider(
        "Max Chunks per Batch",
        min_value=1,
        max_value=500,
        value=settings.embedding.max_chunk_batch_size,
        help="Maximum number of chunks to send in one API call (Azure limit: 500)"
    )
    settings.embedding.max_chunk_batch_size = max_chunk_batch_size

    st.markdown("---")

    # ========== Semantic Search Settings ==========
    st.subheader("🔍 Semantic Search Settings")

    col1, col2 = st.columns(2)

    with col1:
        similarity_threshold = st.slider(
            "Similarity Threshold",
            min_value=0.0,
            max_value=1.0,
            value=settings.embedding.similarity_threshold,
            step=0.01,
            help="Minimum cosine similarity score for search results (0-1, higher = more strict)"
        )
        settings.embedding.similarity_threshold = similarity_threshold

    with col2:
        max_search_results = st.number_input(
            "Max Search Results",
            min_value=1,
            max_value=100,
            value=settings.embedding.max_search_results,
            help="Maximum number of results to return from semantic search"
        )
        settings.embedding.max_search_results = max_search_results

    st.markdown("---")

    # ========== Embedding Statistics ==========
    st.subheader("📊 Embedding Statistics")

    try:
        from services.embedding_service import get_embedding_stats
        stats = get_embedding_stats()

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Documents", stats.get('total_documents', 0))
        with col2:
            st.metric("Total Chunks", stats.get('total_chunks', 0))
        with col3:
            st.metric("Total Embeddings", stats.get('total_embeddings', 0))

        # Show embedding database size
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "embeddings.db")
        if os.path.exists(db_path):
            embed_size_bytes = os.path.getsize(db_path)
            embed_size_mb = embed_size_bytes / (1024 * 1024)
            if embed_size_mb >= 1024:
                embed_size_gb = embed_size_mb / 1024
                st.info(f"💾 **Embedding Database Size:** {embed_size_gb:.2f} GB")
            else:
                st.info(f"💾 **Embedding Database Size:** {embed_size_mb:.1f} MB")
        else:
            st.info("💾 **Embedding Database:** Not yet created")
    except Exception as e:
        st.warning(f"⚠️ Could not load embedding statistics: {e}")

    # Save button for Tab 7
    st.markdown("---")
    if st.button("💾 Save Settings", key="save_tab7", type="primary"):
        try:
            settings.save(SETTINGS_FILE)
            st.success("✅ Settings saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving settings: {e}")


# ===== TAB 8: ABOUT & ACTIONS =====
with tab8:
    st.header("💬 About Settings")

    st.markdown("""
    ### Settings Management

    This settings page allows you to configure all parameters for OpenQuery AI:

    - **Search Settings**: Default search type and query
    - **Geographic & Language**: Country, language, and location targeting
    - **Results**: Number of results and expanded search options
    - **Time & Safety**: Time filters, safe search, autocorrect
    - **Analysis**: Worker counts, timeouts, retries, rate limiting, quality thresholds, PDF settings
    - **Cache**: Cache enablement and freshness TTLs
    - **Embeddings**: Azure OpenAI configuration for semantic search

    ### Saving Settings

    Settings are saved manually by clicking the **"💾 Save Settings"** button at the bottom of each tab.
    Settings are stored in:
    ```
    config/user_settings.json
    ```

    **Important**: After changing and saving settings, you may need to restart the Streamlit app and backend server for changes to take effect.

    You can also export/import settings using the buttons below.
    """)

    st.markdown("---")

    st.subheader("🔧 Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 Save Settings", type="primary", use_container_width=True):
            try:
                settings.save(SETTINGS_FILE)
                st.success("✅ Settings saved successfully!")
            except Exception as e:
                st.error(f"❌ Error saving settings: {e}")

    with col2:
        if st.button("🔄 Reset to Defaults", use_container_width=True):
            st.session_state.app_settings = AppSettings()
            st.success("✅ Settings reset to defaults. Refresh page to see changes.")
            st.rerun()

    with col3:
        if st.button("📥 Export Settings", use_container_width=True):
            st.download_button(
                label="Download JSON",
                data=settings.to_json(),
                file_name=f"serper_settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

    st.markdown("---")

    st.subheader("📤 Import Settings")
    uploaded_file = st.file_uploader("Upload settings JSON file", type=["json"])
    if uploaded_file is not None:
        try:
            settings_json = uploaded_file.read().decode('utf-8')
            imported_settings = AppSettings.from_json(settings_json)
            st.session_state.app_settings = imported_settings
            st.success("✅ Settings imported successfully! Refresh page to see changes.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error importing settings: {e}")

    st.markdown("---")

    st.subheader("📊 Current Settings (JSON)")
    with st.expander("View current settings as JSON", expanded=False):
        st.json(settings.to_dict())


# Footer
st.markdown("---")
st.caption("⚙️ OpenQuery AI Settings | Version 2.0")
