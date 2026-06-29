"""
Content Analysis Panel - Right Pane
Display analysis results and PDF processing results
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


def render_content_analysis_panel():
    """Render content analysis results display"""
    
    # Check if we have results
    if "analysis_results" not in st.session_state:
        st.info("👈 Configure your search and click '🚀 Search & Analyze Now'")
        return

    results = st.session_state["analysis_results"]
    
    # Count PDFs in successful results
    pdf_count, pdf_results = _count_pdfs(results)

    # Header with PDF processing button
    _render_header(pdf_count, pdf_results)

    # Summary metrics
    _render_summary_metrics(results)

    # Show search parameters
    if "last_search" in st.session_state:
        with st.expander("📋 Search Parameters", expanded=False):
            st.json(st.session_state["last_search"])

    # Display results by status
    _display_successful_results(results)
    _display_filtered_results(results)
    _display_failed_results(results)
    _display_processing_summary(results)
    _display_pdf_processing_results()


def _render_cache_match_info():
    """Render cache match information banner"""
    cache_info = st.session_state.get("cache_match_info")

    if not cache_info:
        return

    match_type = cache_info.get("match_type")
    matched_query = cache_info.get("matched_query")
    similarity_score = cache_info.get("similarity_score")
    original_query = cache_info.get("original_query")

    if not match_type:
        return

    # Create styled banner based on match type
    if match_type == "exact":
        st.success(f"✅ **Exact Cache Match** - Results retrieved from cache for query: `{matched_query}`")
    elif match_type == "fuzzy":
        st.info(
            f"🔍 **Similar Cache Match** ({similarity_score}% similarity)\n\n"
            f"**Your query:** `{original_query}`\n\n"
            f"**Matched cached query:** `{matched_query}`\n\n"
            f"Results retrieved from cache."
        )


def _count_pdfs(results: Dict) -> tuple:
    """Count PDFs in successful results

    Returns:
        tuple: (pdf_count, pdf_results list)
    """
    pdf_results = []
    for result in results.get("results", []):
        if result.get("status") == "success" and result.get("pdf_links"):
            pdf_results.append(result)

    return len(pdf_results), pdf_results


def _render_header(pdf_count: int, pdf_results: list):
    """Render header with PDF processing button"""
    if pdf_count > 0:
        col_h1, col_h2, col_h3 = st.columns([3, 1, 2])
    else:
        col_h1, col_h2 = st.columns([4, 1])
        col_h3 = None

    with col_h1:
        st.header("📊 Content Analysis")
    with col_h2:
        if "extracted_urls" in st.session_state:
            urls_count = len(st.session_state["extracted_urls"])
            st.info(f"📎 {urls_count} URLs")

    # PDF Processing Button
    if col_h3 and pdf_count > 0:
        with col_h3:
            process_pdfs_button = st.button(
                f"📄 Process {pdf_count} PDF{'s' if pdf_count > 1 else ''}",
                type="primary",
                use_container_width=True,
                key="process_pdfs_btn"
            )

            if process_pdfs_button:
                st.session_state['trigger_pdf_processing'] = True
                st.session_state['pdf_results_to_process'] = pdf_results
                st.rerun()

    # Display cache match information (if available)
    _render_cache_match_info()


def _render_summary_metrics(results: Dict):
    """Render summary metrics"""
    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    with col_m1:
        serper_api_time = st.session_state.get('serper_api_time', 0)
        st.metric("⚡ Serper API", f"{serper_api_time:.3f}s")
    with col_m2:
        processing_time = st.session_state.get('processing_time', 0)
        st.metric("⚙️ Process", f"{processing_time:.3f}s")
    with col_m3:
        st.metric("✅ Success", results.get("successful", 0))
    with col_m4:
        st.metric("🚫 Filtered", results.get("filtered", 0))
    with col_m5:
        st.metric("❌ Failed", results.get("failed", 0))
    with col_m6:
        total_time = st.session_state.get('total_time', 0)
        st.metric("⏱️ Total", f"{total_time:.3f}s")


def _display_successful_results(results: Dict):
    """Display successful analysis results"""
    st.subheader("✅ Successful Results")
    success_count = 0

    for idx, result in enumerate(results.get("results", [])):
        if result.get("status") == "success":
            success_count += 1
            _render_result_expander(result, idx, success_count, "success")

    if success_count == 0:
        st.info("No successful results to display")
    else:
        st.caption(f"✅ Showing {success_count} successful results above")

    st.divider()


def _display_filtered_results(results: Dict):
    """Display filtered results"""
    st.subheader("🚫 Filtered Results")
    filtered_count = 0

    for idx, result in enumerate(results.get("results", [])):
        if result.get("status") == "filtered":
            filtered_count += 1
            _render_result_expander(result, idx, filtered_count, "filtered")

    if filtered_count == 0:
        st.info("No filtered results")

    st.divider()


def _display_failed_results(results: Dict):
    """Display failed results"""
    st.subheader("❌ Failed Results")
    error_count = 0

    for idx, result in enumerate(results.get("results", [])):
        if result.get("status") not in ["success", "filtered"]:
            error_count += 1
            _render_result_expander(result, idx, error_count, "failed")

    if error_count == 0:
        st.info("No failed results")

    st.divider()


def _render_result_expander(result: Dict, idx: int, count: int, result_type: str):
    """Render an individual result expander based on type"""
    
    if result_type == "success":
        final_score = result.get('final_score', result.get('quality_score', 0))
        final_class = result.get('final_class', result.get('quality_class', 'unknown'))
        quality_emoji = "🟢" if final_class == "legit" else "🟡" if final_class == "maybe" else "⚪"
        cache_indicator = _get_cache_indicator(result)
        
        with st.expander(f"#{count} {quality_emoji} {result.get('title', 'No title')[:80]}...{cache_indicator} ({final_score}/100)", expanded=False):
            _render_success_content(result, idx)
            
    elif result_type == "filtered":
        quality_score = result.get('quality_score', 0)
        cache_indicator = _get_cache_indicator(result)
        
        with st.expander(f"#{count} 🚫 {result.get('title', result.get('url'))[:80]}...{cache_indicator} ({quality_score}/100)", expanded=False):
            _render_filtered_content(result)
            
    elif result_type == "failed":
        with st.expander(f"#{count} ❌ {result.get('url')}", expanded=False):
            _render_failed_content(result)


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


def _render_success_content(result: Dict, idx: int):
    """Render content for successful results"""
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

    st.markdown(f"**URL:** {result.get('url')}")
    st.markdown(f"**Extraction Method:** {result.get('extraction_method', 'None')}")
    st.markdown("---")

    # Show cache info if cached
    if result.get('cached'):
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}")

    # PDF links if available
    if result.get('pdf_links'):
        st.markdown("**PDF Links Found:**")
        for pdf_link in result.get('pdf_links', [])[:5]:
            st.caption(f"• {pdf_link}")

    # Scoring details
    if result.get('score_breakdown'):
        st.markdown("**🔍 Scoring Details:**")
        st.json(result.get('score_breakdown'))

    # NLP Analysis
    if result.get('nlp_analysis'):
        nlp = result.get('nlp_analysis', {})
        st.markdown("**🧠 NLP Analysis:**")
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
        st.text_area("", value=preview, height=100, key=f"preview_{idx}", label_visibility="collapsed")

        # Full content in collapsible section (using button + container instead of nested expander)
        # Try to load from cached JSON first (for PDFs), fallback to cleaned_text
        full_content = ""
        if result.get('content_type') == 'pdf':
            full_content = _load_full_pdf_content(result.get('url', ''))

        # Fallback to cleaned_text if no PDF JSON found
        if not full_content:
            full_content = result.get('cleaned_text', '')

        # Display with toggle button
        if full_content:
            # Initialize session state for this specific content
            toggle_key = f"show_full_{idx}"
            if toggle_key not in st.session_state:
                st.session_state[toggle_key] = False

            # Toggle button
            button_label = "▼ Show Full Content" if not st.session_state[toggle_key] else "▲ Hide Full Content"
            if st.button(f"{button_label} ({len(full_content):,} chars)", key=f"toggle_{idx}"):
                st.session_state[toggle_key] = not st.session_state[toggle_key]

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
        label="📥 Download JSON",
        data=result_json,
        file_name=f"result_{idx}.json",
        mime="application/json",
        key=f"download_{idx}"
    )


def _render_filtered_content(result: Dict):
    """Render content for filtered results"""
    st.markdown(f"**URL:** {result.get('url')}")
    st.warning(f"**Reason:** {result.get('error', 'Quality filter')}")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.metric("Quality Score", f"{result.get('quality_score', 0)}/100")
    with col_f2:
        st.metric("Word Count", result.get('word_count', 0))

    if result.get('cached'):
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}")


def _render_failed_content(result: Dict):
    """Render content for failed results"""
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
        st.info(f"💾 **Cached Result:** {result.get('cache_reason', 'unknown')}")


def _display_processing_summary(results: Dict):
    """Display processing summary in collapsed expander"""
    with st.expander("📊 Processing Summary", expanded=False):
        for idx, result in enumerate(results.get("results", [])):
            url = result.get('url', 'Unknown URL')
            url_display = url[:60] + "..." if len(url) > 60 else url
            status = result.get('status', 'unknown')

            st.write(f"**{idx + 1}.** {url_display}")

            if status == 'success':
                score = result.get('final_score', result.get('quality_score', 0))
                st.success(f"✅ Done | Score: {score}/100")
            elif status == 'filtered':
                st.warning("🚫 Filtered")
            else:
                st.error("❌ Error")


def _display_pdf_processing_results():
    """Display PDF processing results if available"""
    if 'pdf_processing_results' not in st.session_state:
        return

    st.divider()
    st.subheader("📄 PDF Processing Results")

    pdf_proc_results = st.session_state['pdf_processing_results']
    
    # Summary metrics
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.metric("✅ Processed", pdf_proc_results.get('successful', 0))
    with col_p2:
        st.metric("🚫 Filtered", pdf_proc_results.get('filtered', 0))
    with col_p3:
        st.metric("🔄 Duplicates", pdf_proc_results.get('duplicates', 0))
    with col_p4:
        st.metric("❌ Errors", pdf_proc_results.get('errors', 0))

    # Display individual PDF results
    for idx, pdf_result in enumerate(pdf_proc_results.get('results', [])):
        _render_pdf_result(pdf_result, idx)


def _render_pdf_result(pdf_result: Dict, idx: int):
    """Render individual PDF processing result"""
    status = pdf_result.get('status')
    
    if status == 'success':
        score = pdf_result.get('quality_score', 0)
        title = pdf_result.get('title', 'Untitled PDF')
        
        with st.expander(f"✅ {title[:60]}... (Score: {score}/100)", expanded=False):
            col_pd1, col_pd2, col_pd3 = st.columns(3)
            with col_pd1:
                st.metric("Quality Score", f"{score}/100")
            with col_pd2:
                st.metric("Words", f"{pdf_result.get('word_count', 0):,}")
            with col_pd3:
                st.metric("Pages", pdf_result.get('metadata', {}).get('num_pages', 0))

            # Metadata
            st.markdown("**📋 Metadata:**")
            metadata = pdf_result.get('metadata', {})
            st.markdown(f"- **Author:** {metadata.get('author', 'Unknown')}")
            st.markdown(f"- **Created:** {metadata.get('creation_date', 'Unknown')}")
            st.markdown(f"- **Modified:** {metadata.get('modification_date', 'Unknown')}")

            # Full extraction
            with st.expander("🔍 Full Extraction (JSON)", expanded=False):
                st.json(pdf_result.get('full_extraction', {}))

            # Download JSON
            pdf_json = json.dumps(pdf_result, indent=2)
            st.download_button(
                label="📥 Download PDF Analysis JSON",
                data=pdf_json,
                file_name=f"{title[:30]}_analysis.json",
                mime="application/json",
                key=f"download_pdf_{idx}"
            )
    
    elif status == 'filtered':
        title = pdf_result.get('title', 'Untitled PDF')
        score = pdf_result.get('quality_score', 0)
        with st.expander(f"🚫 {title[:60]}... (Score: {score}/100)", expanded=False):
            st.warning(f"**Filtered due to low quality score:** {score}/100")
    
    elif status == 'duplicate':
        title = pdf_result.get('metadata', {}).get('title', 'Untitled PDF')
        with st.expander(f"🔄 {title[:60]}... (Duplicate)", expanded=False):
            st.info("**This PDF has the same metadata (title + author + date) as another already processed PDF.**")
    
    elif status == 'error':
        url = pdf_result.get('url', 'Unknown')
        with st.expander(f"❌ {url[:60]}... (Error)", expanded=False):
            st.error(f"**Error:** {pdf_result.get('error', 'Unknown error')}")
