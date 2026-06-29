"""
Serper Results V2 Component
Simple card view with collapsible accordions for search results
"""
import streamlit as st
import json


def render_result_card(result, index, allow_expander=True, group_id=""):
    """
    Render a single result card with accordion for details

    Args:
        result: dict with keys: title, link, snippet, position, etc.
        index: result position
        allow_expander: bool - if False, shows details inline (for nested contexts)
        group_id: unique identifier for the group (to avoid duplicate widget keys)
    """
    # Extract result data
    title = result.get("title", "No Title")
    link = result.get("link", "")
    snippet = result.get("snippet", "")
    position = result.get("position", index + 1)

    # Additional metadata
    date = result.get("date", "")
    source = result.get("source", "")
    image_url = result.get("imageUrl", "")

    # Check if this URL has been auto-analyzed
    auto_analyzed = False
    analysis_status = ""
    if 'auto_analysis_results' in st.session_state and link in st.session_state['auto_analysis_results']:
        auto_analyzed = True
        auto_result = st.session_state['auto_analysis_results'][link]
        status = auto_result.get('status', 'unknown')
        if status == 'success':
            score = auto_result.get('final_score', 0)
            quality_class = auto_result.get('final_class', 'unknown')
            if quality_class == 'legit':
                analysis_status = f'<span style="background: #22c55e; color: white; padding: 0.2rem 0.5rem; border-radius: 8px; font-size: 0.75rem; margin-left: 0.5rem;">✓ Score: {score}</span>'
            elif quality_class == 'maybe':
                analysis_status = f'<span style="background: #f59e0b; color: white; padding: 0.2rem 0.5rem; border-radius: 8px; font-size: 0.75rem; margin-left: 0.5rem;">? Score: {score}</span>'
            else:
                analysis_status = f'<span style="background: #ef4444; color: white; padding: 0.2rem 0.5rem; border-radius: 8px; font-size: 0.75rem; margin-left: 0.5rem;">✗ Score: {score}</span>'
        elif status == 'filtered':
            analysis_status = '<span style="background: #ef4444; color: white; padding: 0.2rem 0.5rem; border-radius: 8px; font-size: 0.75rem; margin-left: 0.5rem;">✗ Filtered</span>'
        else:
            analysis_status = '<span style="background: #6b7280; color: white; padding: 0.2rem 0.5rem; border-radius: 8px; font-size: 0.75rem; margin-left: 0.5rem;">⚠ Error</span>'

    # Card container
    with st.container():
        # Card styling with title, link, snippet
        st.markdown(f"""
            <div style="
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 1.5rem;
                margin-bottom: 0.5rem;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
                    <div style="flex: 1;">
                        <span style="
                            background: #667eea;
                            color: white;
                            padding: 0.2rem 0.6rem;
                            border-radius: 12px;
                            font-size: 0.8rem;
                            font-weight: 600;
                        ">#{position}</span>{analysis_status}
                        <h3 style="
                            font-size: 1.2rem;
                            font-weight: 600;
                            color: #1a1a1a;
                            margin: 0.5rem 0;
                        ">{title}</h3>
                        <a href="{link}" target="_blank" style="
                            color: #667eea;
                            font-size: 0.9rem;
                            text-decoration: none;
                            word-break: break-all;
                        ">{link}</a>
                    </div>
                </div>
                <p style="
                    color: #666;
                    font-size: 0.95rem;
                    line-height: 1.6;
                    margin-bottom: 0;
                ">{snippet}</p>
            </div>
        """, unsafe_allow_html=True)

        # View Analysis button - OUTSIDE the HTML card for Streamlit to process it
        def on_click():
            """Callback executed BEFORE rerun"""
            # Check if already auto-analyzed
            if 'auto_analysis_results' in st.session_state and link in st.session_state['auto_analysis_results']:
                # Use cached auto-analysis result
                print(f"[DEBUG] Loading auto-analysis result for: {link}")
                st.session_state['show_analysis'] = True
                st.session_state['analysis_result'] = st.session_state['auto_analysis_results'][link]
                st.session_state['analysis_url'] = link
            else:
                # Trigger fresh analysis
                print(f"[DEBUG] Button callback! URL: {link}, Index: {index}")
                st.session_state['analyze_url'] = link
                st.session_state['analyze_index'] = index
                print(f"[DEBUG] Session state set in callback")

        # Button label changes based on auto-analysis status
        button_label = "📊 View Analysis" if auto_analyzed else "🔍 View Analysis"
        button_type = "primary" if auto_analyzed else "secondary"

        col1, col2 = st.columns([1, 5])
        with col1:
            st.button(
                button_label,
                key=f"analyze_btn_{group_id}_{index}",
                type=button_type,
                use_container_width=True,
                on_click=on_click
            )
        with col2:
            st.write("")  # Spacer

        # Details section (inline when inside accordion, expander when not)
        if allow_expander:
            with st.expander("📄 View Full Details", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    if date:
                        st.markdown(f"**📅 Date:** {date}")
                    if source:
                        st.markdown(f"**🔗 Source:** {source}")

                with col2:
                    st.markdown(f"**🔢 Position:** {position}")
                    if link.endswith('.pdf'):
                        st.markdown("**📄 Type:** PDF Document")
                    else:
                        st.markdown("**🌐 Type:** Web Page")

                # Show image if available
                if image_url:
                    st.image(image_url, caption="Preview Image", use_container_width=True)

                # Raw JSON view
                st.markdown("**Raw JSON:**")
                st.json(result)
        else:
            # Show details inline (no expander for nested context)
            with st.container():
                st.markdown("---")
                col1, col2 = st.columns(2)

                with col1:
                    if date:
                        st.markdown(f"**📅 Date:** {date}")
                    if source:
                        st.markdown(f"**🔗 Source:** {source}")

                with col2:
                    st.markdown(f"**🔢 Position:** {position}")
                    if link.endswith('.pdf'):
                        st.markdown("**📄 Type:** PDF Document")
                    else:
                        st.markdown("**🌐 Type:** Web Page")

        st.markdown("---")


def render_serper_results_v2(serper_response, query_info=None, results_by_query=None):
    """
    Render Serper API results in card format with accordions

    Args:
        serper_response: dict with Serper API response
        query_info: dict with query and settings info (optional)
        results_by_query: list of dicts grouping results by query (optional)
    """

    if not serper_response:
        st.info("No results to display. Try running a search first.")
        return

    # Query info banner (compact)
    if query_info:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**Query:** {query_info.get('query', '')}")
        with col2:
            cache_status = '✅ Cached' if query_info.get('from_cache') else '🔄 Live'
            st.markdown(f"**Status:** {cache_status}")

    # Extract results from different result types
    organic_results = serper_response.get("organic", [])
    news_results = serper_response.get("news", [])
    video_results = serper_response.get("videos", [])
    scholar_results = serper_response.get("scholar", [])

    # Count total results
    total_results = len(organic_results) + len(news_results) + len(video_results) + len(scholar_results)

    if total_results == 0:
        st.warning("No results found for this query.")
        return

    # Statistics summary
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Results", total_results)
    with col2:
        st.metric("Organic", len(organic_results))
    with col3:
        st.metric("News", len(news_results))
    with col4:
        st.metric("Videos/Scholar", len(video_results) + len(scholar_results))

    st.markdown("---")

    # If we have results grouped by query, show them in accordions
    if results_by_query:
        st.markdown("### 📊 Results by Query")
        for group_idx, group in enumerate(results_by_query):
            query_label = group.get("label", "Unknown")
            query_text = group.get("query", "")
            result_count = group.get("count", 0)
            results = group.get("results", [])

            # Count errors/status for this group if auto-analyzed
            error_count = 0
            filtered_count = 0
            bg_count = 0
            if 'auto_analysis_results' in st.session_state:
                for result in results:
                    url = result.get("link", "")
                    if url in st.session_state['auto_analysis_results']:
                        status = st.session_state['auto_analysis_results'][url].get('status', '')
                        if status == 'error':
                            error_count += 1
                        elif status == 'filtered':
                            filtered_count += 1
                        elif status == 'background_queued':
                            bg_count += 1

            # Build expander label with counts
            label_parts = [f"🔍 {query_label}: \"{query_text}\" ({result_count} results)"]
            if error_count > 0:
                label_parts.append(f"❌ {error_count} errors")
            if filtered_count > 0:
                label_parts.append(f"🔽 {filtered_count} filtered")
            if bg_count > 0:
                label_parts.append(f"⏳ {bg_count} bg queue")

            # Accordion for each query
            with st.expander(" | ".join(label_parts), expanded=True):
                if results:
                    for idx, result in enumerate(results):
                        # Disable nested expander when inside query accordion
                        # Pass group_idx as unique identifier to avoid duplicate keys
                        render_result_card(result, idx, allow_expander=False, group_id=f"g{group_idx}")
                else:
                    st.info("No results for this query.")

    # Collapsible raw response at the bottom
    st.markdown("---")
    with st.expander("🔧 Raw Serper Response (JSON)", expanded=False):
        st.json(serper_response)
