"""
Semantic Results Tab Component
Displays semantic search results with similarity scores and chunk-level matches
"""
import streamlit as st
import requests
from typing import List, Dict, Optional


# API configuration
API_BASE_URL = "http://127.0.0.1:8000"


def render_semantic_results_tab(
    query: str,
    analyzed_urls: List[str],
    api_base_url: str = API_BASE_URL
):
    """
    Render semantic search results tab

    Args:
        query: Original search query
        analyzed_urls: List of URLs that have been analyzed and embedded
        api_base_url: Base URL for API calls
    """

    st.markdown("### 🎯 Semantic Search Results")
    st.caption("AI-powered relevance ranking using embeddings - finds the most relevant content chunks for your query")

    # Settings section
    with st.expander("⚙️ Semantic Search Settings", expanded=False):
        col1, col2 = st.columns(2)

        # Get defaults from search_params_v2 if available
        default_threshold = st.session_state.get('search_params_v2', {}).get('semantic_similarity_threshold', 0.7)
        default_max_results = st.session_state.get('search_params_v2', {}).get('semantic_max_results', 20)

        with col1:
            similarity_threshold = st.slider(
                "Similarity Threshold",
                min_value=0.5,
                max_value=1.0,
                value=st.session_state.get('semantic_threshold', default_threshold),
                step=0.05,
                help="Minimum similarity score (0-1) to include in results. Higher = more strict matching."
            )
            st.session_state['semantic_threshold'] = similarity_threshold

        with col2:
            max_results = st.number_input(
                "Max Results",
                min_value=5,
                max_value=100,
                value=st.session_state.get('semantic_max_results', default_max_results),
                step=5,
                help="Maximum number of semantic matches to return"
            )
            st.session_state['semantic_max_results'] = max_results

    # Check if we have analyzed URLs
    if not analyzed_urls:
        st.info("""
            💡 **No analyzed documents available**

            Please run auto-analysis first to enable semantic search.
            The "Auto Analysis" checkbox is enabled by default when you search.
        """)
        return

    # Initialize or check semantic results in session state
    if 'semantic_results' not in st.session_state:
        st.session_state['semantic_results'] = None

    # Track if we need to perform automatic search
    # Create a unique key for this query + URLs combination
    current_search_key = f"{query}_{len(analyzed_urls)}_{similarity_threshold}_{max_results}"
    last_search_key = st.session_state.get('last_semantic_search_key', '')

    # Auto-trigger semantic search when:
    # 1. We have analyzed URLs
    # 2. Query/settings changed OR no results yet
    should_search = (current_search_key != last_search_key) or (st.session_state['semantic_results'] is None)

    if should_search:
        with st.spinner(f"🔍 Searching across {len(analyzed_urls)} documents..."):
            try:
                # Call semantic search API
                response = requests.post(
                    f"{api_base_url}/api/semantic-search",
                    json={
                        "query": query,
                        "urls": analyzed_urls,
                        "limit": max_results,
                        "threshold": similarity_threshold
                    },
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    st.session_state['semantic_results'] = result
                    st.session_state['last_semantic_search_key'] = current_search_key
                    st.success(f"✅ Found {len(result.get('results', []))} semantic matches automatically")
                else:
                    st.error(f"❌ Search failed: {result.get('error', 'Unknown error')}")
                    st.session_state['semantic_results'] = None

            except requests.Timeout:
                st.error("⏱️ Semantic search timed out. Please try again.")
                st.session_state['semantic_results'] = None
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state['semantic_results'] = None

    # Display results if available
    if st.session_state.get('semantic_results'):
        result = st.session_state['semantic_results']
        results = result.get('results', [])
        stats = result.get('stats', {})

        if not results:
            st.warning(f"""
                ⚠️ **No results found above threshold {similarity_threshold}**

                Try lowering the similarity threshold or check that embeddings have been generated.
                Embedding generation happens in the background after auto-analysis completes.
            """)
            return

        # Display stats
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Matches Found", len(results))

        with col2:
            st.metric("Documents Searched", stats.get('documents_searched', len(analyzed_urls)))

        with col3:
            st.metric("Chunks Searched", stats.get('chunks_searched', 0))

        with col4:
            st.metric("Threshold Used", f"{stats.get('threshold_used', similarity_threshold):.2f}")

        st.markdown("---")

        # Display results
        st.markdown(f"#### Top {len(results)} Semantic Matches")

        for idx, match in enumerate(results, 1):
            render_semantic_match_card(match, idx)

    else:
        # Show waiting message (shouldn't normally be seen due to auto-search)
        st.info(f"""
            ⏳ **Preparing semantic search...**

            Semantic search will run automatically once embeddings are ready.

            **How it works:**
            - Your query is converted to a vector embedding
            - Each document chunk is compared using cosine similarity
            - Results are ranked by relevance (not just quality)
        """)


def render_semantic_match_card(match: Dict, index: int):
    """
    Render a single semantic match card

    Args:
        match: Match data with url, chunk_text, similarity_score, etc.
        index: Match position (1-based)
    """
    url = match.get('url', 'Unknown')
    chunk_text = match.get('chunk_text', '')
    similarity_score = match.get('similarity_score', 0.0)
    chunk_id = match.get('chunk_id', 0)
    doc_type = match.get('doc_type', 'unknown')

    # Determine score color
    if similarity_score >= 0.9:
        score_color = "#10b981"  # green
        score_label = "Excellent"
    elif similarity_score >= 0.8:
        score_color = "#3b82f6"  # blue
        score_label = "Very Good"
    elif similarity_score >= 0.7:
        score_color = "#8b5cf6"  # purple
        score_label = "Good"
    else:
        score_color = "#6b7280"  # gray
        score_label = "Fair"

    # Extract title from URL or use domain
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        path_parts = parsed.path.split('/')
        title = path_parts[-1] if path_parts[-1] else domain
    except:
        title = url[:50] + "..." if len(url) > 50 else url

    # Card container
    with st.container():
        st.markdown(f"""
            <div style="
                background: white;
                border: 1px solid #e5e7eb;
                border-left: 4px solid {score_color};
                border-radius: 8px;
                padding: 1.5rem;
                margin-bottom: 1rem;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <div style="flex: 1;">
                        <div style="font-size: 0.875rem; color: #6b7280; margin-bottom: 0.25rem;">
                            #{index} • {doc_type.upper()} • Chunk {chunk_id}
                        </div>
                        <div style="font-size: 1.1rem; font-weight: 600; color: #1f2937;">
                            {title}
                        </div>
                    </div>
                    <div style="text-align: right; margin-left: 1rem;">
                        <div style="
                            background: {score_color};
                            color: white;
                            padding: 0.375rem 0.75rem;
                            border-radius: 20px;
                            font-size: 0.875rem;
                            font-weight: 600;
                            white-space: nowrap;
                        ">
                            🎯 {similarity_score:.3f}
                        </div>
                        <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem;">
                            {score_label}
                        </div>
                    </div>
                </div>
                <div style="
                    background: #f9fafb;
                    padding: 1rem;
                    border-radius: 6px;
                    border-left: 3px solid {score_color};
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 0.9rem;
                    line-height: 1.6;
                    color: #374151;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    max-width: 100%;
                ">
{chunk_text[:500]}{"..." if len(chunk_text) > 500 else ""}
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 3])

        with col1:
            if st.button("🔗 View Source", key=f"view_source_{index}", use_container_width=True):
                st.session_state['selected_url_for_analysis'] = url
                st.info(f"Navigate to 'Search Results' tab to view full document analysis")

        with col2:
            with st.expander("📋 Full Chunk"):
                st.markdown(f"**Full Text (Chunk {chunk_id}):**")
                st.text(chunk_text)
                st.markdown(f"**Source:** `{url}`")

        st.markdown("<br>", unsafe_allow_html=True)


def get_embedding_stats(api_base_url: str = API_BASE_URL) -> Optional[Dict]:
    """
    Get embedding statistics from the API

    Args:
        api_base_url: Base URL for API calls

    Returns:
        Dict with embedding stats or None if failed
    """
    try:
        response = requests.get(
            f"{api_base_url}/api/embedding-stats",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[SEMANTIC] Failed to get embedding stats: {e}")
        return None
