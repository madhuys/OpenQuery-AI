"""
PDF Processing Service - Complete Pipeline
Integrates: Download → Extract (7 Phases) → Dedup → Score

This service implements the complete PDF processing flow with full structure detection.

Flow:
1. Download PDF (pdf_service.py)
2. Extract with full processing (pdf_extractor_unified_complete.py) - 7 PHASES:
   - Phase 1: Validation
   - Phase 2-3: Extraction & Font Analysis (single pass)
   - Phase 4: Structure Detection & Block Creation
   - Phase 5: Header/Footer Detection
   - Phase 6: Intelligent Chunking
   - Phase 7: Final Output Generation
3. Deduplication check (pdf_processor.py)
4. Quality scoring (content_scorer.py)
5. Return complete result with scores and structured data
"""

import time
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Optional, Callable

from services.pdf_service import download_pdf_parallel
from services.pdf_extractor_unified_complete import PDFExtractor
from services.pdf_processor import PDFDeduplicator
from services.helpers.content_scorer import ContentScorer
from services.json_font_classifier import classify_pdf_json
from services.cache_service import CacheService
from config.settings import AppSettings, SETTINGS_FILE


def process_pdf_complete(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    max_size_mb: int = 60,
    enable_scoring: bool = True,
    timeout: int = 30,
    max_retries: int = 2
) -> Dict:
    """
    Complete PDF processing pipeline - download, extract, score

    Args:
        url: PDF URL
        index: URL index (for progress reporting)
        progress_callback: Optional callback(index, stage, percent)
        max_size_mb: Max file size in MB
        enable_scoring: Enable quality scoring (default: True)
        timeout: PDF download timeout in seconds (default: 30)
        max_retries: Maximum download retry attempts (default: 2)

    Returns:
        Dict with complete PDF analysis including:
        - status: 'success', 'error', 'filtered', 'duplicate'
        - title, content, metadata
        - heuristic_score, nlp_score, final_score, quality_class
        - word_count, extraction details
        - pdf_filepath, doc_id, fingerprint
    """
    start_time = time.time()

    print(f"[PDF-PROCESS-{index}] [START] Starting complete PDF processing for: {url[:60]}...")

    # Load settings
    try:
        settings = AppSettings.load(SETTINGS_FILE)
    except Exception as e:
        print(f"[PDF-PROCESS-{index}] [WARN]  Could not load settings, using defaults: {e}")
        settings = AppSettings()

    # STEP 0: Check PDF cache FIRST - skip if fresh
    from services.pdf_cache_service import PDFCacheService
    import json
    from pathlib import Path

    cache_service = PDFCacheService()
    should_download, cached_data = cache_service.should_download_pdf(url)

    if not should_download and cached_data:
        print(f"[PDF-PROCESS-{index}] [CACHE-HIT] Fresh PDF found in cache, skipping processing")

        # PRIORITY 1: Check if JSON file exists (takes priority over cached errors)
        # This ensures manually processed PDFs show as successful even if there's a stale error cache
        pdf_filepath = cache_service.get_cached_pdf_filepath(url)

        if pdf_filepath:
            # Try to load the JSON result file from outputs/pdf_json/
            # JSON files are named: {url_hash}_{pdf_filename}.json
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:16]

            json_dir = Path('outputs') / 'pdf_json'
            # Find JSON file matching this URL hash
            json_files = list(json_dir.glob(f"{url_hash}_*.json")) if json_dir.exists() else []

            if json_files:
                try:
                    with open(json_files[0], 'r', encoding='utf-8') as f:
                        full_result = json.load(f)

                    print(f"[PDF-PROCESS-{index}] [CACHE-HIT] ✅ Loaded cached result from {json_files[0].name} (JSON takes priority)")
                    elapsed = time.time() - start_time
                    full_result['processing_time'] = elapsed
                    full_result['cache_hit'] = True
                    full_result['cache_reason'] = cached_data.get('cache_reason', 'fresh_pdf')

                    # CRITICAL: Create embeddings for cached PDF if not already embedded
                    try:
                        # AppSettings already imported at module level (line 34)
                        settings = AppSettings.load(SETTINGS_FILE)

                        if settings.embedding.enabled and full_result.get('status') == 'success':
                            from services.embedding_service import embed_document_async
                            from services.helpers.url_utils import normalize_url

                            # Normalize URL for consistent embedding storage
                            normalized_url = normalize_url(url)

                            # Extract chunks from full_extraction.content (Section → Chunk → Blocks structure)
                            chunks = []
                            full_extraction = full_result.get('full_extraction', {})
                            sections = full_extraction.get('content', [])

                            if sections and isinstance(sections, list):
                                # Restructured content format (sections → chunks → blocks)
                                for section in sections:
                                    if section.get('chunks'):
                                        for chunk in section['chunks']:
                                            # Extract text from blocks within chunk
                                            chunk_text = ''
                                            if chunk.get('blocks'):
                                                chunk_text = ' '.join(block.get('text', '') for block in chunk['blocks'])

                                            # Create properly formatted chunk for embedding
                                            # Use pre-calculated char_count if available (from merge_small_chunks)
                                            if chunk_text.strip():
                                                chunks.append({
                                                    'text': chunk_text.strip(),
                                                    'word_count': len(chunk_text.split()),
                                                    'char_count': chunk.get('char_count', len(chunk_text)),
                                                    'chunk_id': chunk.get('chunk_id', ''),
                                                    'merged_from': chunk.get('merged_from', [])  # Track if this chunk was merged
                                                })
                            elif full_result.get('chunks'):
                                # Old chunks format
                                for chunk in full_result['chunks']:
                                    if isinstance(chunk, dict) and chunk.get('text'):
                                        chunks.append(chunk)
                                    elif isinstance(chunk, str):
                                        chunks.append({'text': chunk, 'word_count': len(chunk.split()), 'char_count': len(chunk)})

                            if chunks:
                                embed_document_async(
                                    url=normalized_url,
                                    doc_type='pdf',
                                    chunks=chunks,
                                    doc_id=full_result.get('doc_id', '')
                                )
                                print(f"[PDF-PROCESS-{index}] 🚀 Started background embedding for {len(chunks)} chunks (from cache)")
                    except Exception as e:
                        print(f"[PDF-PROCESS-{index}] ⚠️ Embedding failed for cached PDF: {e}")

                    return full_result
                except Exception as e:
                    print(f"[PDF-PROCESS-{index}] [CACHE-ERROR] Could not load cached JSON: {e}")
                    # Fall through to check cached error or reprocess

        # PRIORITY 2: Check if it's an error/failure (only if no JSON file exists)
        if 'error' in cached_data:
            print(f"[PDF-PROCESS-{index}] [CACHE-HIT] Returning cached error: {cached_data.get('error')}")
            elapsed = time.time() - start_time
            return {
                'status': 'error',
                'url': url,
                'index': index,
                'title': 'Cached Error',
                'content': '',
                'error': cached_data.get('error'),
                'heuristic_score': 0,
                'nlp_score': 0,
                'final_score': 0,
                'quality_score': 0,
                'quality_class': 'error',
                'word_count': 0,
                'processing_time': elapsed,
                'cache_hit': True,
                'cache_reason': cached_data.get('cache_reason')
            }

        # PRIORITY 3: Success case but no JSON file found
        print(f"[PDF-PROCESS-{index}] [CACHE-MISS] Could not load full cached result, will process from scratch")

    # STEP 1: Download PDF
    if progress_callback:
        try:
            progress_callback(index, 'download', 10)
        except:
            pass

    print(f"[PDF-PROCESS-{index}] [DOWNLOAD] Step 1: Downloading PDF...")
    download_result = download_pdf_parallel(
        url,
        index,
        progress_callback,
        max_retries=max_retries,
        timeout=timeout,
        max_size_mb=max_size_mb
    )

    if download_result['status'] != 'success':
        return {
            'status': 'error',
            'error': download_result.get('error', 'Download failed'),
            'url': url,
            'index': index,
            'title': 'Download Failed',
            'content': '',
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_score': 0,
            'quality_class': 'error',
            'word_count': 0
        }

    pdf_filepath = download_result['pdf_filepath']
    print(f"[PDF-PROCESS-{index}] [OK] Downloaded: {pdf_filepath}")

    # STEP 2: Extract content + metadata in SINGLE PASS
    if progress_callback:
        try:
            progress_callback(index, 'extract', 30)
        except:
            pass

    print(f"[PDF-PROCESS-{index}] [EXTRACT] Step 2: Extracting PDF (complete 7-phase processing)...")
    extraction_start = time.time()

    try:
        # REMOVED: Pre-check for scanned PDFs causes false positives (bondcap PDF had 42k words but failed pre-check)
        # The extraction pipeline handles text-less PDFs gracefully by returning 0 words
        # If it's truly scanned, word_count will be 0 and quality score will be low

        # Use unified extractor for SINGLE PASS extraction
        max_pages = settings.analysis.pdf_max_pages if hasattr(settings.analysis, 'pdf_max_pages') else None
        extractor = PDFExtractor(max_pages=max_pages)
        extraction_result = extractor.extract(pdf_filepath)

        extraction_time = time.time() - extraction_start

        if not extraction_result.get('success'):
            print(f"[PDF-PROCESS-{index}] [ERROR] Extraction failed: {extraction_result.get('error', 'Unknown')}")
            return {
                'status': 'error',
                'error': f"Extraction failed: {extraction_result.get('error', 'Unknown')}",
                'url': url,
                'index': index,
                'title': 'Extraction Error',
                'content': '',
                'heuristic_score': 0,
                'nlp_score': 0,
                'final_score': 0,
                'quality_score': 0,
                'quality_class': 'error',
                'word_count': 0,
                'pdf_filepath': pdf_filepath
            }

        print(f"[PDF-PROCESS-{index}] [OK] Extraction successful: {extraction_result.get('total_words', 0)} words in {extraction_time:.2f}s")

        # STEP 2.5: JSON Font Classification (new advanced classification)
        classified_result = None  # Initialize so it's available in final result building

        if progress_callback:
            try:
                progress_callback(index, 'classify', 50)
            except:
                pass

        print(f"[PDF-PROCESS-{index}] [CLASSIFY] Step 2.5: Applying advanced font-based classification...")
        try:
            # Build initial result structure for classifier
            classifier_input = {
                'url': url,
                'index': index,
                'title': extraction_result.get('metadata', {}).get('title', ''),
                'metadata': extraction_result.get('metadata', {}),
                'num_pages': extraction_result.get('num_pages', 0),
                'total_words': extraction_result.get('total_words', 0),
                'total_characters': extraction_result.get('total_characters', 0),
                'pages': extraction_result.get('pages', []),
                'doc_id': extraction_result.get('doc_id', ''),
                'fingerprint': extraction_result.get('fingerprint', ''),
                'file_size_mb': extraction_result.get('file_size_mb', 0),
                'full_extraction': extraction_result
            }

            # Apply advanced classification
            classified_result = classify_pdf_json(classifier_input)

            # Merge classification results back
            extraction_result = classified_result.get('full_extraction', extraction_result)

            print(f"[PDF-PROCESS-{index}] [OK] Classification complete - document structure available")

        except Exception as e:
            import traceback
            print(f"[PDF-PROCESS-{index}] [WARN] Classification failed, using basic extraction: {e}")
            traceback.print_exc()
            # Continue with basic extraction if classification fails

        # STEP 3: Deduplication check (using extracted metadata)
        metadata = extraction_result.get('metadata', {})
        file_size_mb = Path(pdf_filepath).stat().st_size / (1024 * 1024)
        metadata['file_size_mb'] = file_size_mb
        metadata['source_url'] = url

        # Generate fingerprint
        title = (metadata.get('title') or '').lower().strip()
        author = (metadata.get('author') or '').lower().strip()
        creation_date = metadata.get('creation_date') or ''
        fingerprint_str = f"{title}|{author}|{creation_date}|{file_size_mb}"
        fingerprint = hashlib.sha256(fingerprint_str.encode('utf-8')).hexdigest()

        print(f"[PDF-PROCESS-{index}] [DEDUP] Step 3: Checking for duplicates...")
        deduplicator = PDFDeduplicator()
        is_duplicate, existing_fingerprint = deduplicator.is_duplicate(metadata)

        if is_duplicate:
            print(f"[PDF-PROCESS-{index}] [WARN]  DUPLICATE: fingerprint={fingerprint[:16]}...")
        else:
            print(f"[PDF-PROCESS-{index}] [OK] Unique PDF: fingerprint={fingerprint[:16]}...")
            # Record in deduplication database
            try:
                doc_id = fingerprint[:16]
                deduplicator.record_processed(fingerprint, doc_id, metadata)
            except Exception as e:
                print(f"[PDF-PROCESS-{index}] [WARN]  Could not record fingerprint: {e}")

    except Exception as e:
        print(f"[PDF-PROCESS-{index}] [ERROR] Extraction error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'error': f'Extraction error: {str(e)}',
            'url': url,
            'index': index,
            'title': 'Extraction Error',
            'content': '',
            'heuristic_score': 0,
            'nlp_score': 0,
            'final_score': 0,
            'quality_score': 0,
            'quality_class': 'error',
            'word_count': 0,
            'pdf_filepath': pdf_filepath
        }

    # STEP 4: Quality scoring (if enabled)
    score = 0
    score_class = 'unknown'
    score_details = {}

    if enable_scoring:
        if progress_callback:
            try:
                progress_callback(index, 'extract', 90)
            except:
                pass

        # print(f"[PDF-PROCESS-{index}] [SCORE] Step 4: Quality scoring...")

        try:
            scorer = ContentScorer()

            # Prepare metadata for scoring (from unified extractor)
            pdf_metadata = {
                'title': metadata.get('title', ''),
                'author': metadata.get('author', ''),
                'subject': metadata.get('subject', ''),
                'keywords': metadata.get('keywords', ''),
                'creation_date': metadata.get('creation_date', ''),
                'modification_date': metadata.get('modification_date', ''),
                'num_pages': extraction_result.get('num_pages', 0),
                'file_size_mb': file_size_mb
            }

            # Prepare extracted content for scoring
            # Note: Unified extractor doesn't have 'structure' field, only font_stats
            extracted_for_scoring = {
                'metadata': metadata,
                'word_count': extraction_result.get('total_words', 0),
                'pages': extraction_result.get('pages', []),
                'font_stats': extraction_result.get('font_stats', {})
            }

            # Score the PDF
            score, score_details = scorer.score_pdf_content(
                url=url,
                pdf_metadata=pdf_metadata,
                extracted_content=extracted_for_scoring
            )

            # Classify based on thresholds (using PDF scoring settings)
            threshold_legit = 70  # Default
            threshold_maybe = 40  # Default

            if hasattr(settings, 'pdf_scoring'):
                threshold_legit = settings.pdf_scoring.threshold_legit
                threshold_maybe = settings.pdf_scoring.threshold_maybe

            if score >= threshold_legit:
                score_class = "legit"
            elif score >= threshold_maybe:
                score_class = "maybe"
            else:
                score_class = "skip"

            # print(f"[PDF-PROCESS-{index}] [OK] Quality score: {score}/100 ({score_class})")

        except Exception as e:
            print(f"[PDF-PROCESS-{index}] [WARN]  Scoring failed: {e}")
            import traceback
            traceback.print_exc()
            score = 50  # Default score
            score_class = "maybe"
            score_details = {'error': str(e)}

    # Progress: Complete
    if progress_callback:
        try:
            progress_callback(index, 'complete', 100)
        except:
            pass

    total_time = time.time() - start_time

    # Prepare content preview (first 500 chars from extracted text)
    content_preview = ""
    extraction_method_used = "none"

    # Method 1: Try restructured content (Section → Chunk → Blocks)
    if extraction_result.get('content') and isinstance(extraction_result['content'], list):
        # print(f"[PDF-PROCESS-{index}] [CONTENT] Trying Method 1: Restructured content ({len(extraction_result['content'])} sections)")
        for section in extraction_result['content']:
            if section.get('chunks'):
                for chunk in section['chunks']:
                    for block in chunk.get('blocks', []):
                        content_preview += block.get('text', '') + ' '
                        if len(content_preview) >= 500:
                            break
                    if len(content_preview) >= 500:
                        break
            if len(content_preview) >= 500:
                break
        if content_preview:
            extraction_method_used = "restructured_content"

    # Method 2: Fallback to old chunks format
    if not content_preview and extraction_result.get('chunks'):
        # print(f"[PDF-PROCESS-{index}] [CONTENT] Trying Method 2: Old chunks format ({len(extraction_result['chunks'])} chunks)")
        for chunk in extraction_result['chunks']:
            content_preview += chunk.get('text', '') + ' '
            if len(content_preview) >= 500:
                break
        if content_preview:
            extraction_method_used = "old_chunks"

    # Method 3: Direct from pages array (always present in unified extractor)
    if not content_preview and extraction_result.get('pages'):
        # print(f"[PDF-PROCESS-{index}] [CONTENT] Trying Method 3: Pages text field ({len(extraction_result['pages'])} pages)")
        for page in extraction_result['pages'][:3]:  # First 3 pages
            page_text = page.get('text', '')
            content_preview += page_text + ' '
            if len(content_preview) >= 500:
                break
        if content_preview:
            extraction_method_used = "pages_text"

    # Method 4: Last resort - from structured blocks
    if not content_preview and extraction_result.get('pages'):
        # print(f"[PDF-PROCESS-{index}] [CONTENT] Trying Method 4: Structured blocks from pages")
        for page in extraction_result['pages'][:3]:
            for block in page.get('blocks', []):
                content_preview += block.get('text', '') + ' '
                if len(content_preview) >= 500:
                    break
            if len(content_preview) >= 500:
                break
        if content_preview:
            extraction_method_used = "structured_blocks"

    content_preview = content_preview[:500].strip()

    if not content_preview:
        print(f"[PDF-PROCESS-{index}] [WARN]  Failed to extract content preview - all methods returned empty")
    # else:
        # print(f"[PDF-PROCESS-{index}] [OK] Content preview extracted ({len(content_preview)} chars) via {extraction_method_used}")

    # Extract FULL TEXT (not just preview) for full_text field
    full_text = ""

    # Method 1: From pages array (most reliable)
    if extraction_result.get('pages'):
        for page in extraction_result['pages']:
            page_text = page.get('text', '')
            full_text += page_text + '\n\n'

    # Method 2: Fallback to restructured content
    elif extraction_result.get('content') and isinstance(extraction_result['content'], list):
        for section in extraction_result['content']:
            if section.get('chunks'):
                for chunk in section['chunks']:
                    for block in chunk.get('blocks', []):
                        full_text += block.get('text', '') + ' '

    full_text = full_text.strip()

    # Clean up broken line breaks in full_text
    # 1. Convert 3+ newlines to 2
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)

    # 2. Remove single chars/numbers between newlines (e.g., "\n2\n" -> "\n\n")
    full_text = re.sub(r'\n([0-9a-zA-Z])\n', '\n\n', full_text)

    # 3. Join broken sentences (lines that don't end with sentence-ending punctuation)
    lines = full_text.split('\n')
    joined_lines = []
    buffer = ""

    for line in lines:
        stripped = line.strip()

        # Empty line - flush buffer and preserve blank line
        if not stripped:
            if buffer:
                joined_lines.append(buffer)
                buffer = ""
            joined_lines.append("")  # Preserve paragraph break
            continue

        # Add to buffer
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped

        # Check if line ends with sentence-ending punctuation
        is_sentence_end = stripped and stripped[-1] in '.!?;:'

        # Flush buffer if sentence ends
        if is_sentence_end:
            joined_lines.append(buffer)
            buffer = ""

    # Flush any remaining buffer
    if buffer:
        joined_lines.append(buffer)

    # Rebuild full_text with cleaned lines
    full_text = '\n'.join(joined_lines)

    # print(f"[PDF-PROCESS-{index}] [OK] Full text extracted & cleaned: {len(full_text):,} chars, {len(full_text.split()):,} words")

    # Build complete result
    result = {
        'status': 'success' if score_class != 'skip' else 'filtered',
        'url': url,
        'index': index,
        'title': metadata.get('title', 'Untitled PDF'),
        'content': content_preview,  # 500-char preview for API response
        'cleaned_text': content_preview,  # 500-char preview (legacy field)
        'full_text': full_text,  # FULL extracted text (all pages)

        # Scores (compatible with frontend expectations)
        'heuristic_score': score,  # PDF scoring is heuristic-based
        'nlp_score': 0,  # No NLP scoring for PDFs yet
        'final_score': score,
        'quality_score': score,
        'quality_class': score_class,
        'score_breakdown': score_details,

        # Word count and metadata
        'word_count': extraction_result.get('total_words', 0),
        'total_words': extraction_result.get('total_words', 0),
        'total_characters': extraction_result.get('total_characters', 0),

        # PDF-specific data
        'pdf_filepath': pdf_filepath,
        'pdf_size_mb': metadata.get('file_size_mb', 0),
        'num_pages': metadata.get('num_pages', 0),
        'doc_id': extraction_result.get('doc_id', ''),
        'fingerprint': fingerprint,
        'is_duplicate': is_duplicate,

        # Metadata
        'metadata': metadata,
        'extraction_method': extraction_result.get('profile', 'pdf_unified_extractor'),
        'content_type': 'pdf',

        # Full extraction result (for debugging/advanced use)
        'full_extraction': extraction_result,

        # Structured document output (from advanced font classifier)
        'document': classified_result.get('document') if classified_result else None,

        # Timing
        'process_time': total_time,
        'extraction_time': extraction_time,
        'download_time': download_result.get('download_time', 0),

        # Cache info
        'cached': download_result.get('cached', False),
        'cache_reason': download_result.get('cache_reason', '')
    }

    print(f"[PDF-PROCESS-{index}] [OK] Complete PDF processing done in {total_time:.2f}s")
    print(f"[PDF-PROCESS-{index}]    Score: {score}/100 ({score_class}), Words: {result['word_count']}")

    # CRITICAL: Embed FIRST (before JSON save) - embeddings are needed for search
    if result.get('status') == 'success':
        try:
            # AppSettings already imported at module level (line 34)
            settings = AppSettings.load(SETTINGS_FILE)

            if settings.embedding.enabled:
                from services.embedding_service import embed_document_async
                from services.helpers.url_utils import normalize_url

                # Normalize URL for consistent embedding storage (removes trailing slash, etc.)
                normalized_url = normalize_url(url)

                # Extract chunks from extraction_result - try multiple formats
                chunks = []

                # Method 1: Try restructured content (Section → Chunk → Blocks)
                if extraction_result.get('content') and isinstance(extraction_result['content'], list):
                    for section in extraction_result['content']:
                        if section.get('chunks'):
                            for chunk in section['chunks']:
                                # Extract text from blocks within chunk
                                chunk_text = ''
                                if chunk.get('blocks'):
                                    chunk_text = ' '.join(block.get('text', '') for block in chunk['blocks'])

                                # Create properly formatted chunk for embedding
                                # Use pre-calculated char_count if available (from merge_small_chunks)
                                if chunk_text.strip():
                                    chunks.append({
                                        'text': chunk_text.strip(),
                                        'word_count': len(chunk_text.split()),
                                        'char_count': chunk.get('char_count', len(chunk_text)),
                                        'chunk_id': chunk.get('chunk_id', ''),
                                        'merged_from': chunk.get('merged_from', [])  # Track if this chunk was merged
                                    })

                # Method 2: Fallback to old chunks format
                if not chunks and extraction_result.get('chunks'):
                    for chunk in extraction_result['chunks']:
                        if isinstance(chunk, dict) and chunk.get('text'):
                            chunks.append(chunk)
                        elif isinstance(chunk, str):
                            chunks.append({'text': chunk, 'word_count': len(chunk.split()), 'char_count': len(chunk)})

                if chunks:
                    embed_document_async(
                        url=normalized_url,  # Use normalized URL
                        doc_type='pdf',
                        chunks=chunks,
                        doc_id=result.get('doc_id', '')
                    )
                    # print(f"[PDF-PROCESS-{index}] 🚀 Started background embedding for {len(chunks)} chunks")
        except Exception as e:
            print(f"[PDF-PROCESS-{index}] ⚠️ Embedding failed: {e}")

    # OPTIONAL: Save complete result as JSON file (for UI display only)
    try:
        json_dir = Path('outputs') / 'pdf_json'
        json_dir.mkdir(parents=True, exist_ok=True)

        # Use same naming as PDF file but with .json extension
        pdf_filename = Path(pdf_filepath).stem
        json_filepath = json_dir / f"{pdf_filename}.json"

        # Create a serializable copy of result (remove non-serializable objects)
        result_copy = result.copy()
        # Remove or convert non-serializable fields if any
        if 'full_extraction' in result_copy and isinstance(result_copy['full_extraction'], dict):
            # Keep full_extraction but ensure it's serializable
            pass

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(result_copy, f, indent=2, ensure_ascii=False, default=str)

        # print(f"[PDF-PROCESS-{index}] [OK] Saved JSON result to {json_filepath.name}")
    except Exception as e:
        print(f"[PDF-PROCESS-{index}] [WARN] Failed to save JSON result (non-critical): {e}")

    # Update PDF processing cache
    cache = None
    try:
        cache = CacheService()
        cache.record_pdf_processing_success(
            url=url,
            num_pages=result.get('num_pages', 0),
            num_words=result.get('word_count', 0),
            text_preview=result.get('content_preview', ''),
            freshness_days=30  # PDFs stay fresh for 30 days
        )
        # print(f"[PDF-PROCESS-{index}] [OK] Cached processing result for future use")
    except Exception as e:
        print(f"[PDF-PROCESS-{index}] [WARN] Failed to cache processing result: {e}")
    finally:
        # CRITICAL: Close connection to ensure commit is flushed to disk
        if cache:
            cache.close()

    return result
