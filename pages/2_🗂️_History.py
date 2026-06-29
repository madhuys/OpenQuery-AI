"""
History & Cache Management Page
Browse, query, and manage cached searches, URLs, and analyses
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import json
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from services.cache_service import CacheService

st.set_page_config(
    page_title="Search History & Cache",
    page_icon="🗂️",
    layout="wide"
)

# Initialize cache service
@st.cache_resource
def get_cache_service():
    return CacheService()

cache = get_cache_service()

st.title("🗂️ Search History & Cache Management")

# Tabs for different views
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "🔍 Search History",
    "🌐 URL Cache",
    "📄 Raw Fetches",
    "🧠 Processed Analyses"
])

# ============================================================================
# TAB 1: OVERVIEW - Database Statistics
# ============================================================================
with tab1:
    st.header("Database Statistics")

    stats = cache.get_database_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Domains", stats['domains'])
        st.metric("Total URLs", stats['urls'])

    with col2:
        st.metric("Total Searches", stats['searches'])
        st.metric("Search Results", stats['query_results'])

    with col3:
        st.metric("Raw Fetches", stats['url_raw'])
        st.metric("Processed Analyses", stats['url_processed'])

    # PDF Statistics
    st.subheader("PDF Statistics")

    # Count PDFs in downloaded_pdfs folder
    pdf_dir = Path("downloaded_pdfs")
    json_dir = Path('outputs') / 'pdf_json'

    total_pdfs = 0
    processed_pdfs = 0

    if pdf_dir.exists():
        total_pdfs = len(list(pdf_dir.glob("*.pdf")))

    if json_dir.exists():
        processed_pdfs = len(list(json_dir.glob("*.json")))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total PDFs", total_pdfs)
    with col2:
        st.metric("Processed PDFs", processed_pdfs)
    with col3:
        if total_pdfs > 0:
            processing_rate = (processed_pdfs / total_pdfs) * 100
            st.metric("Processing Rate", f"{processing_rate:.1f}%")
        else:
            st.metric("Processing Rate", "N/A")

    # Cache state distribution
    st.subheader("Cache State Distribution")
    cursor = cache.conn.cursor()
    cursor.execute("""
        SELECT cache_state, COUNT(*) as count
        FROM urls
        GROUP BY cache_state
    """)
    # Don't provide column names - cursor returns dicts with keys already
    cache_states_data = cursor.fetchall()

    if cache_states_data:
        cache_states = pd.DataFrame(cache_states_data)
        # Rename columns to friendly names
        cache_states = cache_states.rename(columns={'cache_state': 'Cache State', 'count': 'Count'})

        # Convert Cache State to string and handle NaN/None
        cache_states['Cache State'] = cache_states['Cache State'].fillna('Unknown').astype(str)
        cache_states['Cache State'] = cache_states['Cache State'].replace('None', 'Unknown')

        # Display as metrics instead of bar chart (avoids Python 3.10 typing issue with altair)
        cols = st.columns(len(cache_states))
        for idx, row in cache_states.iterrows():
            with cols[idx]:
                st.metric(row['Cache State'], row['Count'])
    else:
        st.info("No URLs cached yet")

    # Database actions
    st.subheader("Database Actions")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 Refresh Stats", use_container_width=True):
            st.rerun()

    with col2:
        if st.button("⚠️ Purge All Data", type="secondary", use_container_width=True):
            if st.session_state.get('confirm_purge'):
                # Execute purge
                for table in ['query_results', 'url_processed', 'url_raw', 'urls', 'searches', 'domains']:
                    cache.conn.execute(f"DELETE FROM {table}")
                cache.conn.commit()
                st.success("All data purged!")
                st.session_state['confirm_purge'] = False
                st.rerun()
            else:
                st.session_state['confirm_purge'] = True
                st.warning("Click again to confirm purge")

# ============================================================================
# TAB 2: SEARCH HISTORY
# ============================================================================
with tab2:
    st.header("Search History")

    # Create sub-tabs for Recent Searches and Search Results
    subtab1, subtab2 = st.tabs(["📋 Recent Searches", "🔍 Search Results"])

    # SUB-TAB 1: Recent Searches
    with subtab1:
        # Get all unique queries for autocomplete suggestions
        cursor = cache.conn.cursor()
        cursor.execute("SELECT DISTINCT query_text FROM searches ORDER BY query_text")
        all_queries = [row['query_text'] for row in cursor.fetchall()]

        # Filter controls at the top - compact layout
        col1, col2 = st.columns([5, 1])
        with col1:
            # Use text_input with placeholder showing suggestions
            search_filter = st.text_input(
                "Filter by query (type to search, partial match supported)",
                placeholder="Type to filter queries...",
                key="recent_searches_filter"
            )
            # Show live autocomplete feedback (starts at 2+ characters)
            if search_filter and len(search_filter) >= 2:
                matching = [q for q in all_queries if search_filter.lower() in q.lower()]
                unique_count = len(set(matching))  # Count unique queries only
                if unique_count > 0:
                    # Show count only - no pills
                    st.caption(f"💡 Found {unique_count} matching quer{'y' if unique_count == 1 else 'ies'}")
                else:
                    # No matches found
                    st.caption("❌ No matching queries found. Try different keywords.")
        with col2:
            searches_limit = st.number_input("Max rows", 10, 1000, 100, key="searches_limit")

        # Query searches - filter uses LIKE for partial matching
        if search_filter:
            cursor.execute("""
                SELECT
                    query_id,
                    query_text,
                    created_at,
                    analysis_completed_at,
                    (SELECT COUNT(*) FROM query_results WHERE query_id = searches.query_id) as result_count
                FROM searches
                WHERE query_text LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f"%{search_filter}%", searches_limit))
        else:
            cursor.execute("""
                SELECT
                    query_id,
                    query_text,
                    created_at,
                    analysis_completed_at,
                    (SELECT COUNT(*) FROM query_results WHERE query_id = searches.query_id) as result_count
                FROM searches
                ORDER BY created_at DESC
                LIMIT ?
            """, (searches_limit,))

        searches_df = pd.DataFrame(cursor.fetchall())

        if not searches_df.empty:
            # Selectbox and details card on same row
            col1, col2 = st.columns([3, 7])

            with col1:
                # Selection for details - shows filtered results
                selected_idx = st.selectbox(
                    f"📋 View details ({len(searches_df)} searches)" if not search_filter else f"📋 Select from filtered results",
                    range(len(searches_df)),
                    format_func=lambda i: f"ID {searches_df.iloc[i]['query_id']}: {searches_df.iloc[i]['query_text']} ({searches_df.iloc[i]['result_count']} results)",
                    key="search_detail_selector"
                )

            if selected_idx is not None:
                selected_search = searches_df.iloc[selected_idx]
                query_id = selected_search['query_id']

                with col2:
                    # Slim details panel inline
                    st.markdown(f"""
                        <div style='background-color: rgba(28, 131, 225, 0.1); padding: 8px 12px; border-radius: 4px; margin-top: 28px;'>
                            <strong>📊 {selected_search['query_text']}</strong> &nbsp;&nbsp;|&nbsp;&nbsp;
                            ID: {query_id} &nbsp;&nbsp;|&nbsp;&nbsp;
                            Results: {selected_search['result_count']} &nbsp;&nbsp;|&nbsp;&nbsp;
                            Created: {selected_search['created_at'][:10]}
                        </div>
                    """, unsafe_allow_html=True)

                # Delete button - inline and small
                if st.button(f"🗑️ Delete", key=f"delete_search_{query_id}"):
                    cache.purge_search(query_id)
                    st.success(f"Deleted search {query_id}")
                    st.rerun()

            st.markdown("---")

            # Edge-to-edge scrollable table
            st.dataframe(
                searches_df,
                use_container_width=True,
                height=600,
                hide_index=True
            )
        else:
            st.info("No searches found")

    # SUB-TAB 2: Search Results
    with subtab2:
        # Filter controls
        col1, col2 = st.columns([5, 1])
        with col1:
            # Use text_input for filtering by title/snippet content
            results_filter = st.text_input(
                "Filter by title/snippet (type to search, partial match supported)",
                placeholder="Type to filter by title or snippet content...",
                key="search_results_filter"
            )
            # Show live autocomplete feedback (starts at 2+ characters)
            if results_filter and len(results_filter) >= 2:
                # Count matching results based on title/snippet
                cursor = cache.conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM query_results qr
                    WHERE qr.title_at_fetch LIKE ? OR qr.snippet_at_fetch LIKE ?
                """, (f"%{results_filter}%", f"%{results_filter}%"))
                count_result = cursor.fetchone()
                match_count = count_result['count'] if count_result else 0

                if match_count > 0:
                    # Show count only
                    st.caption(f"💡 Found {match_count} matching result{'s' if match_count != 1 else ''}")
                else:
                    # No matches found
                    st.caption("❌ No matching results found. Try different keywords.")
        with col2:
            results_limit = st.number_input("Max rows", 10, 1000, 100, key="results_limit")

        # Query results - filter by title/snippet using LIKE for partial matching
        # Join with url_raw, url_processed, and pdf_downloads to get content type and freshness
        cursor = cache.conn.cursor()
        if results_filter:
            cursor.execute("""
                SELECT
                    qr.*,
                    u.normalized_url,
                    u.revalidate_after,
                    d.registrable_domain,
                    s.query_text,
                    s.created_at as search_created_at,
                    -- Check if PDF exists
                    CASE WHEN pdf.pdf_id IS NOT NULL THEN 'PDF' ELSE 'HTML' END as content_type,
                    -- Get freshness state
                    CASE
                        WHEN pdf.pdf_id IS NOT NULL THEN pdf.freshness_state
                        WHEN u.revalidate_after > datetime('now') THEN 'fresh'
                        ELSE 'stale'
                    END as freshness,
                    -- Get processed content text
                    COALESCE(proc.content_text, pdf.text_preview, '') as content_text
                FROM query_results qr
                INNER JOIN urls u ON qr.url_id = u.url_id
                INNER JOIN domains d ON u.domain_id = d.domain_id
                INNER JOIN searches s ON qr.query_id = s.query_id
                LEFT JOIN pdf_downloads pdf ON qr.url_id = pdf.url_id
                LEFT JOIN url_raw raw ON qr.url_id = raw.url_id
                LEFT JOIN url_processed proc ON raw.raw_id = proc.raw_id
                WHERE qr.title_at_fetch LIKE ? OR qr.snippet_at_fetch LIKE ?
                ORDER BY s.created_at DESC, qr.serp_position
                LIMIT ?
            """, (f"%{results_filter}%", f"%{results_filter}%", results_limit))
        else:
            cursor.execute("""
                SELECT
                    qr.*,
                    u.normalized_url,
                    u.revalidate_after,
                    d.registrable_domain,
                    s.query_text,
                    s.created_at as search_created_at,
                    -- Check if PDF exists
                    CASE WHEN pdf.pdf_id IS NOT NULL THEN 'PDF' ELSE 'HTML' END as content_type,
                    -- Get freshness state
                    CASE
                        WHEN pdf.pdf_id IS NOT NULL THEN pdf.freshness_state
                        WHEN u.revalidate_after > datetime('now') THEN 'fresh'
                        ELSE 'stale'
                    END as freshness,
                    -- Get processed content text
                    COALESCE(proc.content_text, pdf.text_preview, '') as content_text
                FROM query_results qr
                INNER JOIN urls u ON qr.url_id = u.url_id
                INNER JOIN domains d ON u.domain_id = d.domain_id
                INNER JOIN searches s ON qr.query_id = s.query_id
                LEFT JOIN pdf_downloads pdf ON qr.url_id = pdf.url_id
                LEFT JOIN url_raw raw ON qr.url_id = raw.url_id
                LEFT JOIN url_processed proc ON raw.raw_id = proc.raw_id
                ORDER BY s.created_at DESC, qr.serp_position
                LIMIT ?
            """, (results_limit,))

        results_data = cursor.fetchall()

        if results_data:
            # Create DataFrame with original data
            results_df = pd.DataFrame(results_data)

            # Format Type and Freshness as HTML chips
            def format_type_chip(content_type):
                if content_type == 'PDF':
                    return '📄 PDF'
                else:
                    return '🌐 HTML'

            def format_freshness_chip(freshness):
                if freshness == 'fresh':
                    return '✓ Fresh'
                elif freshness == 'stale':
                    return '⚠ Stale'
                else:
                    return '⏱ Expired'

            # Add formatted columns for display
            results_df['Type'] = results_df.get('content_type', 'HTML').apply(format_type_chip)
            results_df['Freshness'] = results_df.get('freshness', 'unknown').apply(format_freshness_chip)

            # Add View Content button column
            results_df['View Content'] = results_df.apply(
                lambda row: '👁️ View' if row.get('content_text') else 'N/A',
                axis=1
            )

            # Select and reorder columns for display
            display_columns = [
                'title_at_fetch',
                'Type',
                'Freshness',
                'normalized_url',
                'query_text',
                'serp_position',
                'snippet_at_fetch',
                'View Content'
            ]

            # Filter to only columns that exist
            display_columns = [col for col in display_columns if col in results_df.columns]
            display_df = results_df[display_columns].copy()

            # Rename columns for display
            display_df.columns = [
                'Title',
                'Type',
                'Freshness',
                'URL',
                'Query',
                'Position',
                'Snippet',
                'View Content'
            ]

            # Display results count
            st.info(f"Showing {len(display_df)} result(s)")

            # Display table without internal scrollbar (page scroll handles it)
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

            # Content drawers below table
            st.markdown("---")
            st.subheader("View Full Content")

            # Create selectbox to choose which result to view
            result_options = {
                f"{row['title_at_fetch'] or 'No title'} (Position {row.get('serp_position', 'N/A')})": idx
                for idx, row in results_df.iterrows()
                if row.get('content_text')
            }

            if result_options:
                selected_result = st.selectbox(
                    "Select a result to view full content:",
                    options=list(result_options.keys()),
                    key="content_viewer_select"
                )

                if selected_result:
                    idx = result_options[selected_result]
                    row = results_df.iloc[idx]

                    from components.content_drawer import render_content_drawer
                    render_content_drawer(
                        content=row['content_text'],
                        drawer_key=f"result_{row['result_id']}",
                        title="Full Content"
                    )
            else:
                st.info("No processed content available for any results")
        else:
            st.info("No results found")

# ============================================================================
# TAB 3: URL CACHE
# ============================================================================
with tab3:
    st.header("URL Cache")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        url_filter = st.text_input("Filter by URL", "")
    with col2:
        cache_state_filter = st.selectbox("Cache State", ["All", "fresh", "stale", "revalidate"])
    with col3:
        url_limit = st.number_input("Limit", 10, 1000, 100, key="url_limit")

    # Build query
    where_clauses = []
    params = []

    if url_filter:
        where_clauses.append("normalized_url LIKE ?")
        params.append(f"%{url_filter}%")

    if cache_state_filter != "All":
        where_clauses.append("cache_state = ?")
        params.append(cache_state_filter)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    params.append(url_limit)

    cursor.execute(f"""
        SELECT * FROM v_url_cache_stats
        {where_sql}
        ORDER BY last_seen_at DESC
        LIMIT ?
    """, params)

    urls_df = pd.DataFrame(cursor.fetchall())

    if not urls_df.empty:
        st.dataframe(urls_df, use_container_width=True)

        # Selection for details/actions
        selected_url_idx = st.selectbox(
            "Select URL for details",
            range(len(urls_df)),
            format_func=lambda i: f"{urls_df.iloc[i]['normalized_url'][:80]}..."
        )

        if selected_url_idx is not None:
            selected_url = urls_df.iloc[selected_url_idx]
            url_id = selected_url['url_id']

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("URL Info")
                st.write(f"**URL:** {selected_url['normalized_url']}")
                st.write(f"**Domain:** {selected_url['registrable_domain']}")
                st.write(f"**Cache State:** {selected_url['cache_state']}")
                st.write(f"**Fetch Count:** {selected_url['fetch_count']}")
                st.write(f"**Process Count:** {selected_url['process_count']}")

            with col2:
                st.subheader("Actions")
                new_state = st.selectbox(
                    "Update Cache State",
                    ["fresh", "stale", "revalidate"],
                    key=f"state_{url_id}"
                )

                if st.button("Update State", key=f"update_{url_id}"):
                    cache.mark_url_staleness(url_id, new_state)
                    st.success(f"Updated to {new_state}")
                    st.rerun()

                if st.button(f"🗑️ Delete URL {url_id}", type="secondary", key=f"del_{url_id}"):
                    cache.purge_url(url_id)
                    st.success(f"Deleted URL {url_id} and all related data")
                    st.rerun()
    else:
        st.info("No URLs found")

# ============================================================================
# TAB 4: RAW FETCHES
# ============================================================================
with tab4:
    st.header("Raw Fetch History")

    # Optional filter by fetch ID
    with st.expander("🔍 Filter Options", expanded=False):
        filter_by_fetch = st.checkbox("Filter by specific fetch ID", value=False)
        if filter_by_fetch:
            fetch_id_filter = st.number_input("Fetch ID", min_value=1, value=1, key="fetch_id_filter")
        else:
            fetch_id_filter = None

    # Build query based on filter
    if fetch_id_filter:
        query = """
            SELECT
                ur.raw_id,
                ur.url_id,
                u.normalized_url,
                ur.fetched_at,
                ur.http_status,
                ur.content_hash,
                ur.etag,
                LENGTH(ur.raw_html) as html_size
            FROM url_raw ur
            INNER JOIN urls u ON ur.url_id = u.url_id
            WHERE ur.raw_id = ?
            ORDER BY ur.fetched_at DESC
        """
        cursor.execute(query, (fetch_id_filter,))
    else:
        # Show ALL fetches by default - no limit
        query = """
            SELECT
                ur.raw_id,
                ur.url_id,
                u.normalized_url,
                ur.fetched_at,
                ur.http_status,
                ur.content_hash,
                ur.etag,
                LENGTH(ur.raw_html) as html_size
            FROM url_raw ur
            INNER JOIN urls u ON ur.url_id = u.url_id
            ORDER BY ur.fetched_at DESC
        """
        cursor.execute(query)

    raw_df = pd.DataFrame(cursor.fetchall())

    if not raw_df.empty:
        st.info(f"Showing {len(raw_df)} fetch(es)")
        st.dataframe(raw_df, use_container_width=True, height=400)

        # View raw HTML - use selectbox with raw_id directly
        selected_raw_id = st.selectbox(
            "Type to search - View raw HTML for fetch:",
            raw_df['raw_id'].tolist(),
            format_func=lambda rid: f"Fetch {rid} - {raw_df[raw_df['raw_id']==rid]['fetched_at'].values[0]}"
        )

        if selected_raw_id is not None:
            cursor.execute("SELECT raw_html, fetch_meta_json FROM url_raw WHERE raw_id = ?", (selected_raw_id,))
            row = cursor.fetchone()

            if row:
                with st.expander("📄 Raw HTML Preview", expanded=True):
                    html_content = row['raw_html'] if row['raw_html'] else ""
                    st.text_area("HTML", html_content[:5000] + "..." if len(html_content) > 5000 else html_content, height=300)

                with st.expander("🔍 Fetch Metadata"):
                    st.json(json.loads(row['fetch_meta_json']) if row['fetch_meta_json'] else {})
            else:
                st.error(f"No data found for raw_id {selected_raw_id}")
    else:
        st.info("No fetches found")

# ============================================================================
# TAB 5: PROCESSED ANALYSES
# ============================================================================
with tab5:
    st.header("Processed Analyses")

    proc_limit = st.number_input("Limit", 10, 500, 50, key="proc_limit")

    cursor.execute("""
        SELECT
            proc_id,
            url_id,
            raw_id,
            pipeline_version,
            model_name,
            model_version,
            schema_version,
            published_at,
            updated_at,
            published_source,
            updated_source,
            created_at,
            LENGTH(content_text) as text_length
        FROM url_processed
        ORDER BY created_at DESC
        LIMIT ?
    """, (proc_limit,))

    proc_df = pd.DataFrame(cursor.fetchall())

    if not proc_df.empty:
        st.dataframe(proc_df, use_container_width=True)

        # View analysis details
        selected_proc_idx = st.selectbox(
            "View analysis details",
            range(len(proc_df)),
            format_func=lambda i: f"Analysis {proc_df.iloc[i]['proc_id']} - {proc_df.iloc[i]['created_at']}"
        )

        if selected_proc_idx is not None:
            proc_id = proc_df.iloc[selected_proc_idx]['proc_id']

            cursor.execute("""
                SELECT
                    up.*,
                    u.normalized_url
                FROM url_processed up
                INNER JOIN urls u ON up.url_id = u.url_id
                WHERE up.proc_id = ?
            """, (proc_id,))

            proc_result = cursor.fetchone()

            if proc_result:
                proc_row = dict(proc_result)

                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("Analysis Metadata")
                    st.write(f"**URL:** {proc_row.get('normalized_url', 'N/A')}")
                    st.write(f"**Pipeline:** {proc_row.get('pipeline_version', 'N/A')}")
                    st.write(f"**Model:** {proc_row.get('model_name', 'N/A')} v{proc_row.get('model_version', 'N/A')}")
                    st.write(f"**Published:** {proc_row.get('published_at', 'N/A')} ({proc_row.get('published_source', 'N/A')})")
                    st.write(f"**Updated:** {proc_row.get('updated_at', 'N/A')} ({proc_row.get('updated_source', 'N/A')})")

                with col2:
                    with st.expander("Content Text Preview"):
                        content_text = proc_row.get('content_text', '')[:1000] if proc_row.get('content_text') else ''
                        st.text_area("", content_text, height=200)

                    with st.expander("Analysis Summary"):
                        analysis_summary = proc_row.get('analysis_summary', '')
                        st.text_area("", analysis_summary if analysis_summary else '', height=200)

                with st.expander("Entities"):
                    entities_json = proc_row.get('entities_json')
                    st.json(json.loads(entities_json) if entities_json else {})

                with st.expander("Quality Scores"):
                    quality_scores_json = proc_row.get('quality_scores_json')
                    st.json(json.loads(quality_scores_json) if quality_scores_json else {})
            else:
                st.error(f"No data found for proc_id {proc_id}")
    else:
        st.info("No processed analyses found")

# ============================================================================
# SIDEBAR: SQL Query Interface
# ============================================================================
with st.sidebar:
    st.header("🔧 SQL Query")

    sql_query = st.text_area(
        "Custom SQL Query",
        "SELECT * FROM searches LIMIT 10",
        height=150
    )

    if st.button("Execute Query"):
        try:
            cursor = cache.conn.cursor()
            cursor.execute(sql_query)

            if sql_query.strip().upper().startswith('SELECT'):
                results = cursor.fetchall()
                if results:
                    df = pd.DataFrame(results)
                    st.dataframe(df)
                else:
                    st.info("No results")
            else:
                cache.conn.commit()
                st.success("Query executed successfully")
        except Exception as e:
            st.error(f"Error: {str(e)}")

    st.divider()

    st.subheader("Available Tables & Views")
    st.code("""
Tables:
- searches
- query_results
- urls
- domains
- pdf_downloads
- url_raw
- url_processed

Views:
- v_pdf_stats
- v_pdf_downloads_with_method
- v_domain_download_performance
- v_browser_pool_stats
- v_auto_switch_analysis
    """)

    st.subheader("Available Tables")
    st.code("""
domains
urls
searches
query_results
url_raw
url_processed
    """)
