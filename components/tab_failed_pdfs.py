"""
Tab 2: Background Queue Progress
Interface for viewing PDFs being processed in the background queue
"""
import streamlit as st
import time
import hashlib
import json
from datetime import datetime
from pathlib import Path
from services.background_queue_service import get_queue_service
from services.cache_service import CacheService
from services.pdf_extractor_unified_complete import PDFExtractor, check_if_scanned_pdf
from services.pdf_processor import PDFDeduplicator
from services.helpers.content_scorer import ContentScorer


def render_failed_pdfs_tab():
    """Render the Background Queue Progress tab"""

    st.header("🔄 Background PDF Processing Queue")

    # Info banner
    st.info("""
    **What is this?** When PDFs take longer than 8 seconds to process, they're added to a background queue.
    They'll be processed completely in the background and cached for future searches.
    """)

    # Auto-refresh toggle
    col1, col2 = st.columns([3, 1])
    with col1:
        auto_refresh = st.checkbox("🔁 Auto-refresh (every 5 seconds)", value=False, key="bg_queue_auto_refresh")
    with col2:
        if st.button("🔄 Refresh Now", key="bg_queue_refresh_now"):
            st.rerun()

    # Fetch queue data
    _fetch_queue_data()

    # Display queue statistics
    _display_queue_stats()

    # Display active items (pending + processing)
    _display_active_items()

    # Display recent completed items
    _display_completed_items()

    # Display failed items
    _display_failed_items()

    # Auto-refresh logic
    if auto_refresh:
        time.sleep(5)
        st.rerun()


def _fetch_queue_data():
    """Fetch queue data from the background queue service"""
    try:
        queue = get_queue_service()

        # Get statistics
        st.session_state['queue_stats'] = queue.get_queue_stats()

        # Get items by status
        st.session_state['pending_items'] = queue.get_all_items(status='pending')
        st.session_state['processing_items'] = queue.get_all_items(status='processing')
        st.session_state['completed_items'] = queue.get_all_items(status='completed')[:10]  # Last 10
        st.session_state['failed_items'] = queue.get_all_items(status='failed')

    except Exception as e:
        st.error(f"Error fetching queue data: {str(e)}")
        st.session_state['queue_stats'] = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}


def _display_queue_stats():
    """Display queue statistics"""
    stats = st.session_state.get('queue_stats', {})

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("⏳ Pending", stats.get('pending', 0))

    with col2:
        st.metric("🔄 Processing", stats.get('processing', 0))

    with col3:
        st.metric("✅ Completed", stats.get('completed', 0))

    with col4:
        st.metric("❌ Failed", stats.get('failed', 0))

    st.markdown("---")


def _display_active_items():
    """Display pending and processing items"""
    pending = st.session_state.get('pending_items', [])
    processing = st.session_state.get('processing_items', [])

    total_active = len(pending) + len(processing)

    if total_active == 0:
        st.success("✅ No PDFs currently in the queue!")
        return

    st.subheader(f"📋 Active Queue Items ({total_active})")

    # Processing items first
    if processing:
        st.markdown("### 🔄 Currently Processing")
        for item in processing:
            _display_queue_item(item, status_emoji="🔄", status_text="Processing")

    # Pending items
    if pending:
        st.markdown("### ⏳ Waiting in Queue")
        for item in pending:
            _display_queue_item(item, status_emoji="⏳", status_text="Pending")


def _display_completed_items():
    """Display recently completed items"""
    completed = st.session_state.get('completed_items', [])

    if not completed:
        return

    st.markdown("---")
    st.subheader(f"✅ Recently Completed ({len(completed)})")

    with st.expander("Show completed items", expanded=False):
        for item in completed:
            _display_queue_item(item, status_emoji="✅", status_text="Completed", show_duration=True)


def _display_failed_items():
    """Display failed items with manual upload option"""
    failed = st.session_state.get('failed_items', [])

    if not failed:
        return

    st.markdown("---")
    st.subheader(f"❌ Failed Items ({len(failed)})")

    st.info("💡 **Manual Upload Available**: Click the URL to download manually, then upload here to process the PDF.")

    # Display items directly without outer expander to avoid nesting
    for idx, item in enumerate(failed):
        _display_failed_item_with_upload(item, idx)


def _display_failed_item_with_upload(item: dict, idx: int):
    """Display a failed item with manual upload option"""
    url = item.get('url', 'Unknown URL')
    queue_id = item.get('id')

    with st.container():
        # Create a border/card effect
        st.markdown(f"""
        <div style="border: 1px solid #ff4b4b; border-radius: 5px; padding: 15px; margin-bottom: 15px;">
        </div>
        """, unsafe_allow_html=True)

        # Header with URL as clickable link and queue ID
        st.markdown(f"### ❌ Failed PDF #{idx + 1} (Queue ID: {queue_id})")

        # URL as clickable link that opens in new tab
        st.markdown(f"🔗 **URL**: [{url}]({url})")

        # Error details
        col1, col2, col3 = st.columns(3)

        with col1:
            added_at = item.get('added_at')
            if added_at:
                st.caption(f"📅 Added: {_format_timestamp(added_at)}")

        with col2:
            retry_info = f"🔄 Retries: {item.get('retry_count', 0)}/{item.get('max_retries', 3)}"
            st.caption(retry_info)

        with col3:
            st.caption("⚠️ Auto-download failed")

        # Error message
        if item.get('error_message'):
            error_msg = item.get('error_message')
            with st.expander("🔍 View Error Details", expanded=False):
                st.code(error_msg, language="text")

        st.divider()

        # Manual upload section
        st.markdown("#### 📤 Manual Upload")
        st.markdown("1. Click the URL above to open in a new tab\n2. Download the PDF manually\n3. Upload it here:")

        uploaded_file = st.file_uploader(
            "Choose PDF file",
            type=['pdf'],
            key=f"upload_failed_{queue_id}_{idx}",
            help="Upload the manually downloaded PDF file"
        )

        if uploaded_file is not None:
            # Process button
            col1, col2 = st.columns([1, 3])

            with col1:
                process_btn = st.button(
                    "🚀 Process PDF",
                    key=f"process_failed_{queue_id}_{idx}",
                    type="primary"
                )

            with col2:
                st.caption(f"📄 File: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")

            if process_btn:
                _process_manual_upload(uploaded_file, url, queue_id, item)

        st.markdown("---")


def _display_queue_item(item: dict, status_emoji: str, status_text: str, show_duration: bool = False, show_error: bool = False):
    """Display a single queue item"""
    with st.container():
        # Header row
        col1, col2 = st.columns([4, 1])

        with col1:
            url = item.get('url', 'Unknown URL')
            truncated_url = url[:80] + "..." if len(url) > 80 else url
            st.markdown(f"{status_emoji} **{truncated_url}**")

        with col2:
            st.markdown(f"**{status_text}**")

        # Details row
        col1, col2, col3 = st.columns(3)

        with col1:
            added_at = item.get('added_at')
            if added_at:
                st.caption(f"📅 Added: {_format_timestamp(added_at)}")

        with col2:
            retry_info = f"🔄 Retries: {item.get('retry_count', 0)}/{item.get('max_retries', 3)}"
            st.caption(retry_info)

        with col3:
            if show_duration and item.get('started_at') and item.get('completed_at'):
                duration = _calculate_duration(item.get('started_at'), item.get('completed_at'))
                st.caption(f"⏱️ Duration: {duration}")
            elif item.get('started_at'):
                st.caption(f"▶️ Started: {_format_timestamp(item.get('started_at'))}")

        # Error message if applicable
        if show_error and item.get('error_message'):
            error_msg = item.get('error_message')
            truncated_error = error_msg[:100] + "..." if len(error_msg) > 100 else error_msg
            st.error(f"❌ Error: {truncated_error}")

        st.markdown("---")


def _format_timestamp(timestamp_str: str) -> str:
    """Format timestamp for display"""
    if not timestamp_str:
        return "—"
    try:
        dt = datetime.fromisoformat(timestamp_str)

        # If today, show time only
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%H:%M:%S")

        # If recent, show relative time
        diff = now - dt
        if diff.days == 0:
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            if hours > 0:
                return f"{hours}h {minutes}m ago"
            else:
                return f"{minutes}m ago"
        elif diff.days == 1:
            return "Yesterday " + dt.strftime("%H:%M")
        else:
            return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return timestamp_str


def _calculate_duration(start_str: str, end_str: str) -> str:
    """Calculate duration between two timestamps"""
    try:
        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        duration = end - start

        total_seconds = duration.total_seconds()

        if total_seconds < 60:
            return f"{int(total_seconds)}s"
        elif total_seconds < 3600:
            minutes = int(total_seconds // 60)
            seconds = int(total_seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    except:
        return "—"


def _process_manual_upload(uploaded_file, url: str, queue_id: int, item: dict):
    """Process manually uploaded PDF"""
    try:
        with st.spinner("🔄 Processing uploaded PDF..."):
            # Create progress container
            progress_container = st.empty()
            progress_container.info("📥 Saving uploaded file...")

            # Save uploaded file to downloaded_pdfs directory
            pdf_dir = Path("downloaded_pdfs")
            pdf_dir.mkdir(exist_ok=True)

            # Generate filename based on URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
            original_name = Path(uploaded_file.name).stem
            filename = f"{url_hash}_{original_name}.pdf"
            filepath = pdf_dir / filename

            # Write uploaded file
            pdf_bytes = uploaded_file.read()
            filepath.write_bytes(pdf_bytes)
            pdf_hash = hashlib.md5(pdf_bytes).hexdigest()

            # First cache the PDF download
            try:
                cache = CacheService()
                cache.record_pdf_download_success(
                    url=url,
                    pdf_bytes=pdf_bytes,
                    pdf_hash=pdf_hash,
                    download_method='manual',  # Fixed: database constraint expects 'manual', not 'manual_upload'
                    filepath=str(filepath)
                )
                progress_container.info("✅ Cached PDF download record")
            except Exception as cache_dl_error:
                progress_container.warning(f"⚠️ Download cache failed: {str(cache_dl_error)}")

            progress_container.info("🔍 Extracting text and analyzing PDF...")

            # Process the local PDF file directly (skip download step)
            try:
                # Skip strict scanned check for manual uploads
                # Some PDFs have image-based cover pages but extractable content
                # Just try extraction and check if we got meaningful content

                # Extract text with full 7-phase processing
                progress_container.info("🔍 Initializing PDF extractor...")
                extractor = PDFExtractor()

                progress_container.info("📖 Extracting text from PDF (this may take a minute)...")
                extraction_result = extractor.extract(str(filepath))

                if not extraction_result:
                    raise ValueError("Extraction returned no result")

                # The unified extractor returns structured content (Section → Chunk → Blocks hierarchy)
                # Extract plain text from the structured content
                content_sections = extraction_result.get('content', [])

                if not content_sections:
                    raise ValueError("No content sections found in extraction result")

                # Extract text from all sections → chunks → blocks
                text_parts = []
                for section in content_sections:
                    for chunk in section.get('chunks', []):
                        for block in chunk.get('blocks', []):
                            block_text = block.get('text', '').strip()
                            if block_text:
                                text_parts.append(block_text)

                # Join all text parts
                cleaned_text = ' '.join(text_parts)

                if not cleaned_text:
                    raise ValueError("No text content found in extraction result (all sections/chunks empty)")

                # Check if we got meaningful content (more than just whitespace/garbage)
                word_count = len(cleaned_text.split())

                if word_count < 50:
                    raise ValueError(f"Insufficient extractable text - only {word_count} words found. PDF may be scanned/image-based.")

                # Quality scoring using PDF scoring method
                scorer = ContentScorer()
                final_score, score_details = scorer.score_pdf_content(
                    url=url,
                    pdf_metadata=extraction_result.get('metadata', {}),
                    extracted_content={
                        'word_count': word_count,
                        'metadata': extraction_result.get('metadata', {}),
                        'pages': extraction_result.get('pages', []),
                        'structure': extraction_result.get('structure', {})
                    }
                )
                quality_class = scorer.classify_score(final_score)

                # Create result (include both 'content' and 'cleaned_text' for compatibility)
                result = {
                    'status': 'success',
                    'url': url,
                    'title': extraction_result.get('metadata', {}).get('title', 'Manually Uploaded PDF'),
                    'content': cleaned_text,  # Full content
                    'cleaned_text': cleaned_text,  # Alias for compatibility
                    'word_count': word_count,
                    'final_score': final_score,
                    'quality_score': final_score,
                    'quality_class': quality_class,
                    'score_details': score_details,
                    'pdf_filepath': str(filepath),
                    'pdf_size_mb': filepath.stat().st_size / (1024 * 1024),
                    'metadata': extraction_result.get('metadata', {}),
                    'extraction_method': 'manual_upload',
                    'doc_id': extraction_result.get('doc_id', ''),
                    'fingerprint': extraction_result.get('fingerprint', '')
                }

            except Exception as extract_error:
                result = {
                    'status': 'error',
                    'error': str(extract_error)
                }

            if result.get('status') == 'success':
                progress_container.success("✅ Processing complete!")

                # Save JSON file to outputs/pdf_json directory
                try:
                    import json
                    json_dir = Path('outputs') / 'pdf_json'
                    json_dir.mkdir(parents=True, exist_ok=True)

                    # Use same naming as PDF file but with .json extension
                    pdf_filename = filepath.stem
                    json_filepath = json_dir / f"{pdf_filename}.json"

                    # Prepare complete result with extraction data
                    complete_result = {
                        **result,
                        'full_extraction': extraction_result,
                        'url': url,
                        'processing_method': 'manual_upload',
                        'processed_at': str(datetime.now())
                    }

                    with open(json_filepath, 'w', encoding='utf-8') as f:
                        json.dump(complete_result, f, indent=2, ensure_ascii=False, default=str)

                    st.info(f"📝 Saved structured data to: `{json_filepath.name}`")
                except Exception as json_error:
                    st.warning(f"⚠️ JSON save failed: {str(json_error)}")

                # Update PDF processing cache
                try:
                    cache = CacheService()
                    content_preview = result.get('content', '')[:500] if result.get('content') else ''
                    cache.record_pdf_processing_success(
                        url=url,
                        num_pages=extraction_result.get('num_pages', 0),
                        num_words=result.get('word_count', 0),
                        text_preview=content_preview,
                        freshness_days=30
                    )
                    cache.close()
                except Exception as cache_error:
                    st.warning(f"⚠️ Processing cache update failed: {str(cache_error)}")

                # Mark queue item as completed
                try:
                    queue = get_queue_service()
                    queue.mark_completed(queue_id, result_cache_key=pdf_hash)

                    # Display results
                    st.success(f"""
                    ✅ **PDF Successfully Processed!**

                    - **Queue ID**: {queue_id}
                    - **Title**: {result.get('title', 'N/A')}
                    - **Words**: {result.get('word_count', 0):,}
                    - **Quality Score**: {result.get('final_score', 0)}/100
                    - **Filepath**: `{filepath}`

                    The PDF has been cached and will appear in future search results.
                    This failed item (Queue ID: {queue_id}) has been moved to "Completed".
                    """)

                    # Show preview of content
                    with st.expander("📄 Content Preview", expanded=False):
                        preview_text = result.get('content', result.get('cleaned_text', ''))
                        preview = preview_text[:500]
                        st.text(preview + "..." if len(preview_text) > 500 else preview)

                    # Refresh button
                    if st.button("🔄 Refresh Queue", key=f"refresh_after_upload_{queue_id}"):
                        st.rerun()

                except Exception as queue_error:
                    st.warning(f"⚠️ PDF processed but queue update failed: {str(queue_error)}")
                    st.info("The PDF was processed and cached successfully but the queue status may not be updated.")

            else:
                error_msg = result.get('error', 'Unknown error')
                st.error(f"""
                ❌ **Processing Failed**

                {error_msg}

                Please check the error message and try again, or try a different PDF file.
                """)

                # Keep in failed state
                queue = get_queue_service()
                queue.mark_failed(queue_id, f"Manual upload processing failed: {error_msg}", increment_retry=False)

    except Exception as e:
        st.error(f"""
        ❌ **Upload Error**

        An error occurred while processing the upload: {str(e)}

        Please try again or contact support if the issue persists.
        """)

        # Log error to queue
        try:
            queue = get_queue_service()
            queue.mark_failed(queue_id, f"Manual upload error: {str(e)}", increment_retry=False)
        except:
            pass
