"""
Analysis Results Panel - Right Pane for Single URL Analysis
Displays content analysis for ONE URL result (triggered by "View Analysis" button)
Reuses logic from content_analysis_panel.py but for single-result display
"""
import streamlit as st
import json
import re
from typing import Dict
from pathlib import Path
import hashlib


def _convert_text_to_markdown_html(text: str) -> str:
    """
    Convert plain text to formatted HTML with markdown-style headings.

    Detects title lines (all caps, short lines) and converts them to proper headings.
    Fixes broken line breaks in the middle of sentences.

    Args:
        text: Plain text content

    Returns:
        HTML-formatted content with proper heading tags
    """
    if not text:
        return ""

    # Step 1: Clean up excessive newlines (3+ becomes 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Step 2: Remove single chars/numbers between newlines (e.g., "\n2\n" -> "\n\n")
    text = re.sub(r'\n([0-9a-zA-Z])\n', '\n\n', text)

    # Step 3: Join broken sentences (lines that don't end with sentence-ending punctuation)
    lines = text.split('\n')
    joined_lines = []
    buffer = ""

    for line in lines:
        stripped = line.strip()

        # Empty line - flush buffer and add blank line
        if not stripped:
            if buffer:
                joined_lines.append(buffer)
                buffer = ""
            joined_lines.append("")  # Preserve blank line
            continue

        # Add to buffer
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped

        # Check if line ends with sentence-ending punctuation or is likely a heading
        is_sentence_end = stripped and stripped[-1] in '.!?;:'
        is_heading = (len(stripped) < 80 and
                     stripped.isupper() and
                     any(c.isalpha() for c in stripped) and
                     len([c for c in stripped if c.isalpha()]) > 3)

        # Flush buffer if sentence ends or is heading
        if is_sentence_end or is_heading:
            joined_lines.append(buffer)
            buffer = ""

    # Flush any remaining buffer
    if buffer:
        joined_lines.append(buffer)

    # Step 4: Format lines as HTML
    formatted_lines = []

    for line in joined_lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            formatted_lines.append('<br>')
            continue

        # Detect headings (all caps, relatively short, not just numbers/symbols)
        if (len(stripped) < 80 and
            stripped.isupper() and
            any(c.isalpha() for c in stripped) and
            len([c for c in stripped if c.isalpha()]) > 3):
            # This is likely a heading
            formatted_lines.append(f'<h2 style="color: #1f77b4; margin-top: 20px; margin-bottom: 10px; font-weight: bold;">{stripped}</h2>')
        else:
            # Regular paragraph
            formatted_lines.append(f'<p style="margin-bottom: 10px; line-height: 1.6;">{stripped}</p>')

    return '\n'.join(formatted_lines)


def _load_full_pdf_content(url: str) -> str:
    """
    Load full PDF content from cached JSON file

    Args:
        url: PDF URL to find JSON for

    Returns:
        Formatted markdown content from full_text field, or empty string if not found
    """
    try:
        # Generate filename hash (same logic as in pdf_processing_service.py)
        url_hash = hashlib.md5(url.encode()).hexdigest()[:16]

        # Look for JSON files in outputs/pdf_json directory
        json_dir = Path('outputs') / 'pdf_json'
        if not json_dir.exists():
            return ""

        # Find JSON file matching this URL's hash
        json_files = list(json_dir.glob(f"{url_hash}*.json"))

        if not json_files:
            return ""

        # Load the JSON file
        with open(json_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Get full_text field (properly formatted with newlines)
        full_text = data.get('full_text', '')

        if not full_text:
            # Fallback to cleaned_text if full_text not available
            full_text = data.get('cleaned_text', '')

        return full_text

    except Exception as e:
        print(f"Error loading full PDF content: {e}")
        return ""


def _get_cache_indicator(result: Dict) -> str:
    """Generate cache indicator string"""
    if result.get('cached', False):
        cache_reason = result.get('cache_reason', 'cached')
        if 'HTTP 304' in cache_reason:
            return " 💾[304]"
        elif 'filtered_skip' in cache_reason:
            return " 💾[filtered]"
        elif 'error_skip' in cache_reason:
            return " 💾[error]"
        elif 'fresh' in cache_reason:
            return " 💾[fresh]"
        elif 'skip' in cache_reason:
            days = cache_reason.split('_')[-1] if '_' in cache_reason else 'unknown'
            return f" 💾[skip {days}]"
        else:
            return f" 💾[{cache_reason.split('_')[0]}]"
    return ""


def render_analysis_results_panel(result: Dict, url: str = None):
    """
    Render content analysis for a SINGLE URL result

    Args:
        result: Analysis result dict from /api/analyze-url
        url: Optional URL (if not in result)

    Returns:
        None (renders directly to Streamlit)
    """
    if not result:
        st.warning("No analysis result to display")
        return

    status = result.get('status', 'unknown')
    url = url or result.get('url', 'Unknown URL')

    # Header
    st.markdown("### 📊 Content Analysis")
    st.markdown(f"**URL:** {url}")

    # Different rendering based on status
    if status == 'success':
        _render_success_analysis(result)
    elif status == 'filtered':
        _render_filtered_analysis(result)
    elif status == 'error':
        _render_error_analysis(result)
    else:
        st.error(f"Unknown status: {status}")


def _render_success_analysis(result: Dict):
    """Render successful analysis result"""
    # Quality metrics
    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
    final_score = result.get('final_score', result.get('quality_score', 0))

    with col_q1:
        st.metric("Final Score", f"{final_score}/100")
    with col_q2:
        st.metric("Heuristic", f"{result.get('heuristic_score', 0)}/100")
    with col_q3:
        st.metric("NLP Score", f"{result.get('nlp_score', 0)}/100")
    with col_q4:
        st.metric("Words", result.get('word_count', 0))

    # Extraction method and content type
    extraction_method = result.get('extraction_method', result.get('content_type', 'unknown'))
    st.markdown(f"**Extraction Method:** {extraction_method}")

    # Quality class badge
    quality_class = result.get('final_class', result.get('quality_class', 'unknown'))
    quality_emoji = "🟢" if quality_class == "legit" else "🟡" if quality_class == "maybe" else "⚪"
    st.markdown(f"**Quality:** {quality_emoji} {quality_class.upper()}")

    st.markdown("---")

    # Show cache info if cached
    if result.get('cached'):
        cache_indicator = _get_cache_indicator(result)
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}{cache_indicator}")

    # PDF links if available
    if result.get('pdf_links'):
        st.markdown("**PDF Links Found:**")
        for pdf_link in result.get('pdf_links', [])[:5]:
            st.caption(f"• {pdf_link}")

    # Scoring details
    if result.get('score_breakdown'):
        with st.expander("🔍 Scoring Details", expanded=False):
            st.json(result.get('score_breakdown'))

    # NLP Analysis
    if result.get('nlp_analysis'):
        with st.expander("🧠 NLP Analysis", expanded=False):
            nlp = result.get('nlp_analysis', {})
            if nlp.get('structured_data'):
                st.markdown("**📊 Structured Data:**")
                st.json(nlp.get('structured_data'))
            if nlp.get('readability'):
                st.markdown("**📖 Readability:**")
                st.json(nlp.get('readability'))
            if nlp.get('wire_service', {}).get('is_wire'):
                st.info(f"📰 **Wire Service:** {nlp['wire_service']['wire_services']}")

    # Content preview
    if result.get('cleaned_text'):
        st.markdown("**Content Preview (First 500 chars):**")
        preview = result.get('cleaned_text', '')[:500]
        st.text_area("", value=preview, height=100, key="analysis_preview", label_visibility="collapsed")

        # Full content in collapsible section
        full_content = ""
        if result.get('content_type') == 'pdf':
            full_content = _load_full_pdf_content(result.get('url', ''))

        # Fallback to cleaned_text if no PDF JSON found
        if not full_content:
            full_content = result.get('cleaned_text', '')

        # Display with toggle button
        if full_content:
            # Initialize session state for this specific content
            toggle_key = "show_full_analysis_content"
            if toggle_key not in st.session_state:
                st.session_state[toggle_key] = False

            # Callback to toggle state
            def toggle_content():
                st.session_state[toggle_key] = not st.session_state[toggle_key]

            # Toggle button
            button_label = "▼ Show Full Content" if not st.session_state[toggle_key] else "▲ Hide Full Content"
            st.button(
                f"{button_label} ({len(full_content):,} chars)",
                key="toggle_analysis_content",
                on_click=toggle_content
            )

            # Show content if toggled on
            if st.session_state[toggle_key]:
                st.markdown("---")
                # Convert plain text to formatted HTML
                formatted_html = _convert_text_to_markdown_html(full_content)

                # Display in scrollable container with proper formatting
                st.markdown(
                    f"""
                    <div style="max-height: 600px; overflow-y: auto; padding: 20px;
                                border: 1px solid #ccc; border-radius: 8px;
                                background-color: #ffffff; font-family: 'Segoe UI', Tahoma, sans-serif;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        {formatted_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown("---")

    # Download JSON
    result_json = json.dumps(result, indent=2)
    st.download_button(
        label="📥 Download Analysis JSON",
        data=result_json,
        file_name=f"analysis_{result.get('url', 'unknown').split('/')[-1][:20]}.json",
        mime="application/json",
        key="download_analysis_json"
    )


def _render_filtered_analysis(result: Dict):
    """Render filtered analysis result"""
    st.warning("This content was filtered due to low quality score")

    st.markdown(f"**Reason:** {result.get('error', 'Quality filter')}")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.metric("Quality Score", f"{result.get('quality_score', 0)}/100")
    with col_f2:
        st.metric("Word Count", result.get('word_count', 0))

    if result.get('cached'):
        cache_indicator = _get_cache_indicator(result)
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}{cache_indicator}")

    # Show content preview if available
    if result.get('content') or result.get('cleaned_text'):
        with st.expander("Preview Content", expanded=False):
            preview = result.get('content', result.get('cleaned_text', ''))[:500]
            st.text_area("", value=preview, height=100, key="filtered_preview", label_visibility="collapsed")


def _render_error_analysis(result: Dict):
    """Render error analysis result"""
    failure_stage = result.get('failure_stage', 'unknown')
    if failure_stage and failure_stage != 'unknown':
        stage_emojis = {
            'fetch': '🌐',
            'download': '⬇️',
            'parse': '📄',
            'extract': '✂️',
            'clean': '🧹',
            'analyze': '🔍',
            'unknown': '❓'
        }
        stage_emoji = stage_emojis.get(failure_stage, '❓')
        st.error(f"{stage_emoji} **Failed at {failure_stage.upper()} stage**")

    st.error(result.get('error', 'Unknown error'))

    error_details = result.get('error_details')
    if error_details:
        st.caption(f"**Technical details:** {error_details}")

    if result.get('cached'):
        cache_indicator = _get_cache_indicator(result)
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}{cache_indicator}")
