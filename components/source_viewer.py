"""
Source Viewer Component
Displays matched source document with highlighted chunks
"""
import streamlit as st
from typing import Dict, Optional


def render_source_viewer(match_result: Optional[Dict] = None):
    """
    Render source document viewer with highlighted match

    Args:
        match_result: Match result from ChunkMatcherService
    """
    st.markdown("### 📄 Source Document Viewer")

    if match_result is None:
        # Empty state
        st.info("👈 Click **'Match Chunk to Source'** on any search result to view the full document with highlighted match")
        st.markdown("""
        **How it works:**
        1. Select a search result from the left panel
        2. Click the **'Match Chunk to Source'** button
        3. The full source document will appear here
        4. The matched chunk will be **highlighted in red**
        5. The view will auto-scroll to the highlighted section
        """)
        return

    # Check for error
    if 'error' in match_result:
        st.error(f"❌ {match_result['error']}")
        st.caption(f"URL: {match_result.get('url', 'N/A')}")
        st.caption(f"Type: {match_result.get('doc_type', 'N/A')}")
        return

    # Display document metadata
    with st.expander("📊 Document Metadata", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Match Type", match_result.get('match_type', 'N/A').upper())
            st.caption(f"**Word Count:** {match_result.get('document_metadata', {}).get('word_count', 'N/A')}")
        with col2:
            st.caption(f"**Section:** {match_result.get('section_index', 'N/A')}")
            st.caption(f"**Chunk:** {match_result.get('chunk_index', 'N/A')}")

        st.markdown(f"**Title:** {match_result.get('document_title', 'N/A')}")
        st.markdown(f"**URL:** [{match_result.get('url', 'N/A')}]({match_result.get('url', '#')})")

        metadata = match_result.get('document_metadata', {})
        if metadata.get('author'):
            st.caption(f"**Author:** {metadata['author']}")
        if metadata.get('published_date'):
            st.caption(f"**Published:** {metadata['published_date']}")

    # Display full document with highlighted match
    st.markdown("---")
    st.markdown("### 📄 Full Document with Highlighted Match")

    full_text = match_result.get('full_text', '')

    if full_text:
        # Get match positions
        start_char = match_result.get('start_char', 0)
        end_char = match_result.get('end_char', 0)

        # Split text into before, match, and after
        text_before = full_text[:start_char]
        text_match = full_text[start_char:end_char]
        text_after = full_text[end_char:]

        # Escape HTML special characters to prevent injection
        import html as html_module
        text_before_escaped = html_module.escape(text_before)
        text_match_escaped = html_module.escape(text_match)
        text_after_escaped = html_module.escape(text_after)

        # Preserve line breaks - convert to <br> tags
        text_before_html = text_before_escaped.replace('\n', '<br>\n')
        text_match_html = text_match_escaped.replace('\n', '<br>\n')
        text_after_html = text_after_escaped.replace('\n', '<br>\n')

        # Create full document HTML with highlight
        full_doc_html = f"""
<div id="doc-container" style="
    padding: 20px;
    background-color: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    max-height: 700px;
    overflow-y: auto;
    font-family: Georgia, serif;
    line-height: 1.8;
    color: #333;
    font-size: 15px;
">
{text_before_html}<mark id="matched-section" style="background-color: #fff3cd; border: 2px solid #ffc107; padding: 4px 8px; border-radius: 4px; font-weight: 600;">{text_match_html}</mark>{text_after_html}
</div>
<script>
setTimeout(function() {{
    var element = document.getElementById('matched-section');
    if (element) {{
        element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}
}}, 300);
</script>
"""

        st.markdown(full_doc_html, unsafe_allow_html=True)

        # Show match info
        st.caption(f"📍 Match found at position {start_char}-{end_char} • {match_result.get('match_type', 'N/A').upper()} match • Document length: {len(full_text):,} characters")
    else:
        st.warning("Full document text not available")

    # Action buttons
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔗 Open Original", use_container_width=True):
            st.markdown(f"[Open in new tab]({match_result.get('url', '#')})")

    with col2:
        if st.button("📋 Copy Matched Text", use_container_width=True):
            st.code(matched_text, language=None)
            st.success("✅ Text displayed above - copy manually")

    with col3:
        if st.button("❌ Clear Viewer", use_container_width=True):
            if 'source_viewer_match' in st.session_state:
                del st.session_state['source_viewer_match']
            st.rerun()
