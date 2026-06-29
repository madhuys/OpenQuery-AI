"""
Search Panel - Left Pane
Search settings and analysis configuration
"""
import streamlit as st
import multiprocessing
import json
from config.settings import AppSettings, SETTINGS_FILE


def render_search_panel(app_settings: AppSettings) -> tuple:
    """Render search settings panel (left pane)

    Returns:
        tuple: (search_clicked, search_params_dict)
    """
    st.header("🎯 Search Settings")

    # Initialize session state from latest saved settings (read from JSON file)
    # This allows temporary overrides while preserving saved defaults
    if 'session_initialized' not in st.session_state:
        # Read directly from JSON file to get latest saved values (bypass cache)
        with open(SETTINGS_FILE, 'r') as f:
            settings_dict = json.load(f)

        st.session_state.session_search_type = settings_dict.get('search', {}).get('search_type', 'search')
        st.session_state.session_query = settings_dict.get('search', {}).get('default_query', '')
        st.session_state.session_country = settings_dict.get('geographic', {}).get('country', '')
        st.session_state.session_language = settings_dict.get('geographic', {}).get('language', 'en')
        st.session_state.session_location = settings_dict.get('geographic', {}).get('location', '')
        st.session_state.session_num_results = settings_dict.get('results', {}).get('num_results', 10)
        st.session_state.session_safe_search = settings_dict.get('time_filter', {}).get('safe_search', 'off')
        st.session_state.session_autocorrect = settings_dict.get('time_filter', {}).get('enable_autocorrect', True)
        st.session_state.session_max_workers = settings_dict.get('analysis', {}).get('max_workers', 10)
        st.session_state.session_download_workers = settings_dict.get('analysis', {}).get('max_download_workers', 5)
        st.session_state.session_initialized = True

    # Add info box explaining settings behavior
    st.info("""
💡 **Settings Mode**: Changes here are **temporary** (current session only).
To save permanently, go to ⚙️ Settings page.
    """)

    # Add Reset button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("↺ Reset", use_container_width=True, help="Reset to saved settings"):
            # Clear all session state - will reload from app_settings
            keys_to_clear = [k for k in st.session_state.keys() if k.startswith('session_')]
            for key in keys_to_clear:
                del st.session_state[key]
            st.rerun()

    # Search type selection (with session state)
    search_types = ["search", "news", "videos", "scholar"]
    default_search_idx = search_types.index(st.session_state.session_search_type) if st.session_state.session_search_type in search_types else 0
    search_type = st.selectbox(
        "Search Type",
        search_types,
        index=default_search_idx,
        help="Select the type of search you want to perform"
    )
    # Update session state if changed
    if search_type != st.session_state.session_search_type:
        st.session_state.session_search_type = search_type

    # Query input (with session state)
    query = st.text_input(
        "Query",
        value=st.session_state.session_query,
        help="The search query string"
    )
    # Update session state if changed
    if query != st.session_state.session_query:
        st.session_state.session_query = query

    # Document Search checkbox (below query) - read latest setting from file
    if 'session_document_search' not in st.session_state:
        # Read directly from file to get latest saved value (bypass cache)
        with open(SETTINGS_FILE, 'r') as f:
            settings_dict = json.load(f)
        default_document_search = settings_dict.get('results', {}).get('enable_document_search', False)
        st.session_state.session_document_search = default_document_search

    document_search = st.checkbox(
        "📄 Include Document Search",
        value=st.session_state.session_document_search,
        help="Add parallel search with ' pdf' appended to find documents/PDFs (page 1 only, 10 additional results)"
    )
    if document_search != st.session_state.session_document_search:
        st.session_state.session_document_search = document_search

    # Geographic & Language Settings
    with st.expander("Geographic & Language Settings", expanded=False):
        gl = st.text_input(
            "Country (gl)",
            value=st.session_state.session_country,
            placeholder="e.g., us, uk, in",
            help="Country code for search results"
        )
        if gl != st.session_state.session_country:
            st.session_state.session_country = gl

        hl = st.text_input(
            "Language (hl)",
            value=st.session_state.session_language,
            placeholder="e.g., en, es, fr",
            help="UI language for search results"
        )
        if hl != st.session_state.session_language:
            st.session_state.session_language = hl

        location = st.text_input(
            "Location",
            value=st.session_state.session_location,
            placeholder="e.g., New York, United States",
            help="Human-readable geographic location"
        )
        if location != st.session_state.session_location:
            st.session_state.session_location = location

    # Result Settings
    with st.expander("Result Settings", expanded=False):
        num_results = st.number_input(
            "Number of Results",
            min_value=1,
            max_value=50,
            value=st.session_state.session_num_results,
            help="Total number of results to fetch. Serper returns 10 per page, so requesting 20 will make 2 API calls."
        )
        if num_results != st.session_state.session_num_results:
            st.session_state.session_num_results = num_results

        # Calculate pages needed
        pages_needed = (num_results + 9) // 10  # Ceiling division
        if pages_needed > 1:
            st.info(f"ℹ️ Will fetch {pages_needed} pages ({num_results} results total)")

    # Time Filters & Safety
    with st.expander("Time Filters & Safety", expanded=False):
        tbs_option = st.selectbox(
            "Time Filter (tbs)",
            ["None", "Past day", "Past week", "Past month", "Past year"],
            help="Filter results by time period"
        )

        tbs_value = ""
        if tbs_option == "Past day":
            tbs_value = "qdr:d"
        elif tbs_option == "Past week":
            tbs_value = "qdr:w"
        elif tbs_option == "Past month":
            tbs_value = "qdr:m"
        elif tbs_option == "Past year":
            tbs_value = "qdr:y"

        safe_options = ["off", "active"]
        default_safe_idx = safe_options.index(st.session_state.session_safe_search) if st.session_state.session_safe_search in safe_options else 0
        safe = st.selectbox(
            "Safe Search",
            safe_options,
            index=default_safe_idx,
            help="Enable or disable safe search"
        )
        if safe != st.session_state.session_safe_search:
            st.session_state.session_safe_search = safe

        autocorrect = st.checkbox("Enable autocorrect", value=st.session_state.session_autocorrect)
        if autocorrect != st.session_state.session_autocorrect:
            st.session_state.session_autocorrect = autocorrect

    st.divider()

    # Analysis Settings
    st.subheader("⚡ Analysis Settings")

    # Get CPU count for max workers
    cpu_count = multiprocessing.cpu_count()
    max_possible_workers = min(cpu_count * 4, 32)  # Cap at 32 to avoid issues

    parallel_workers = st.slider(
        "Parallel Workers",
        min_value=1,
        max_value=max_possible_workers,
        value=min(st.session_state.session_max_workers, max_possible_workers),
        help=f"Number of parallel workers for content extraction. Your system has {cpu_count} CPU cores. I/O-bound tasks benefit from more workers. Recommended: {cpu_count * 4}"
    )
    if parallel_workers != st.session_state.session_max_workers:
        st.session_state.session_max_workers = parallel_workers

    pdf_download_workers = st.slider(
        "PDF Download Workers",
        min_value=1,
        max_value=parallel_workers,
        value=min(st.session_state.session_download_workers, parallel_workers),
        help=f"Number of concurrent PDF downloads (max: {parallel_workers}). Reduce if downloads cause bandwidth bottlenecks."
    )
    if pdf_download_workers != st.session_state.session_download_workers:
        st.session_state.session_download_workers = pdf_download_workers

    timeout_setting = st.slider(
        "Timeout per URL (seconds)",
        min_value=5,
        max_value=30,
        value=10,
        help="Maximum time to wait for each URL"
    )

    disable_cache = st.checkbox(
        "🚫 Disable Serper Cache (measure pure API time)",
        value=False,
        help="Bypass cache to measure actual Serper API performance"
    )

    st.info(f"⚡ Workers: {parallel_workers} parallel | {pdf_download_workers} PDF downloads{' | Cache DISABLED' if disable_cache else ''}")

    # Single analyze button
    search_clicked = st.button("🚀 Search & Analyze Now", type="primary", use_container_width=True)

    # Return search params for use in right pane
    return search_clicked, {
        'search_type': search_type,
        'query': query,
        'gl': gl,
        'hl': hl,
        'location': location,
        'num_results': num_results,
        'tbs_value': tbs_value,
        'safe': safe,
        'autocorrect': autocorrect,
        'parallel_workers': parallel_workers,
        'pdf_download_workers': pdf_download_workers,
        'timeout_setting': timeout_setting,
        'disable_cache': disable_cache,
        'document_search': document_search  # Include document search flag
    }
