"""
HTML Processing Service - Complete Pipeline
Matches PDF architecture: Download → Extract → Score → Structure

This service implements the complete HTML processing flow.
NO TIMEOUT CHECKS INSIDE - timeout managed by fast lane wrapper.

Flow:
1. Download HTML
2. Extract text (trafilatura → readability → BeautifulSoup)
3. Clean text
4. Quality scoring
5. NLP analysis
6. Structure extraction
7. Return complete result
"""

import time
import hashlib
import json
from pathlib import Path
from typing import Dict, Optional, Callable
from bs4 import BeautifulSoup
import trafilatura
from readability import Document

from services.helpers.content_scorer import ContentScorer
from services.helpers.nlp_analyzer import NLPAnalyzer
from services.cache_service import CacheService
from config.settings import AppSettings


def _extract_html_structure(html: str, title: str, cleaned_text: str) -> Dict:
    """
    Extract structured blocks, sections, and chunks from HTML.

    Used for:
    - JSON output (UI display)
    - Embeddings (semantic search)

    Returns:
        Dict with blocks, sections, and chunks
    """
    from bs4 import BeautifulSoup
    import re

    soup = BeautifulSoup(html, 'html.parser')

    # Extract blocks (paragraphs, headings, lists)
    blocks = []
    sections = []

    # Find all content blocks
    for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']):
        text = tag.get_text(strip=True)
        if len(text) >= 20:  # Minimum text length
            blocks.append({
                'type': tag.name,
                'text': text,
                'level': int(tag.name[1]) if tag.name.startswith('h') else 0
            })

    # Group into sections based on headings
    current_section = {'heading': title or 'Introduction', 'content': []}

    for block in blocks:
        if block['type'].startswith('h') and block['level'] <= 3:
            if current_section['content']:
                sections.append(current_section)
            current_section = {'heading': block['text'], 'content': []}
        else:
            current_section['content'].append(block['text'])

    if current_section['content']:
        sections.append(current_section)

    # Create chunks for embeddings (500-word chunks with 50-word overlap)
    words = cleaned_text.split()
    chunks = []
    chunk_size = 500
    overlap = 50

    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        if len(chunk_words) >= 50:  # Minimum chunk size
            chunks.append(' '.join(chunk_words))

    return {
        'blocks': blocks,
        'sections': sections,
        'chunks': chunks
    }


def process_html_complete(
    url: str,
    index: int = 0,
    progress_callback: Optional[Callable] = None,
    settings: Optional[AppSettings] = None,
    fast_lane_mode: bool = False
) -> Dict:
    """
    Complete HTML processing pipeline - download, extract, score, structure.

    NO TIMEOUT CHECKS - Let the fast lane wrapper manage timeout via ThreadPoolExecutor.
    This function just does the work without worrying about time limits.

    Args:
        url: HTML URL
        index: URL index (for progress reporting)
        progress_callback: Optional callback(index, stage, percent)
        settings: AppSettings instance
        fast_lane_mode: If True, skip NLP analysis for speed (2-4s vs 6-9s)

    Returns:
        Dict with complete HTML analysis including:
        - status: 'success', 'error', 'filtered'
        - title, content, metadata
        - heuristic_score, nlp_score, final_score, quality_class
        - word_count, extraction details
        - blocks, sections, chunks (for embeddings)
    """
    start_time = time.time()
    step_times = {}

    print(f"[HTML-{index}] Starting processing in thread {threading.current_thread().name}")

    # Load settings if not provided
    if settings is None:
        from config.settings import SETTINGS_FILE
        settings = AppSettings.load(SETTINGS_FILE)

    # Initialize services
    scorer = ContentScorer()
    nlp_analyzer = NLPAnalyzer()

    # STEP 1: Download HTML
    print(f"[HTML-{index}] 🆕 NO CACHE (fetching fresh): {url[:60]}...")

    if progress_callback:
        try:
            progress_callback(index, 'download', 10)
        except:
            pass

    try:
        import httpx

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        with httpx.Client(timeout=settings.analysis.html_timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

            # Get HTML content
            if 'text/html' in response.headers.get('content-type', ''):
                html = response.text
            else:
                return {
                    'status': 'error',
                    'error': f"Non-HTML content type: {response.headers.get('content-type')}",
                    'url': url,
                    'index': index
                }

        step_times['download'] = time.time() - start_time
        print(f"[HTML-{index}] Downloaded {len(html):,} chars ({len(response.content):,} bytes) in {step_times['download']:.2f}s")

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code in [401, 403, 404, 451]:
            print(f"[HTML-{index}] [ERROR] Non-retriable HTTP {status_code} - skipping retries")
            return {
                'status': 'error',
                'error': f"HTTP {status_code}: {str(e)}",
                'url': url,
                'index': index
            }
        raise

    except Exception as e:
        print(f"[HTML-{index}] Download error: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'url': url,
            'index': index
        }

    # Progress: Extraction stage
    if progress_callback:
        try:
            progress_callback(index, 'extract', 40)
        except:
            pass

    # STEP 2: Extract text with fallback chain
    print(f"[HTML-{index}] ⏱️  Starting extraction")

    extracted_text = None
    title = None

    # Try trafilatura first (best quality)
    try:
        extracted_text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False
        )
        if extracted_text and len(extracted_text) >= 100:
            print(f"[HTML-{index}] ✅ Extracted via trafilatura")
    except Exception as e:
        print(f"[HTML-{index}] Trafilatura failed: {e}")

    # Fallback to readability
    if not extracted_text or len(extracted_text) < 100:
        try:
            doc = Document(html)
            title = doc.title()
            text = doc.summary(html_partial=False)
            soup = BeautifulSoup(text, 'html.parser')
            extracted_text = soup.get_text(separator='\n', strip=True)
            if extracted_text and len(extracted_text) >= 50:
                print(f"[HTML-{index}] ✅ Extracted via readability")
        except Exception as e:
            print(f"[HTML-{index}] Readability failed: {e}")

    # Final fallback: BeautifulSoup raw extraction
    if not extracted_text or len(extracted_text) < 50:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for script in soup(["script", "style", "meta", "link"]):
                script.decompose()
            if not title and soup.title:
                title = soup.title.string
            extracted_text = soup.get_text(separator='\n', strip=True)
            print(f"[HTML-{index}] ✅ Extracted via BeautifulSoup fallback")
        except Exception as e:
            print(f"[HTML-{index}] BeautifulSoup failed: {e}")

    if not extracted_text:
        return {
            'status': 'error',
            'error': 'Failed to extract content',
            'url': url,
            'index': index
        }

    # Clean up text
    from services.helpers.text_post_processor import clean_extracted_text

    cleaned_text = clean_extracted_text(
        text=extracted_text,
        source='html',
        options={
            'remove_wiki_edit_markers': True,
            'remove_orphaned_hyphens': True,
            'clean_wikipedia_tables': True,
            'normalize_line_breaks': True
        }
    )

    # Get title if not found yet
    if not title:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.title.string if soup.title else url.split('//')[-1].split('/')[0]
        except:
            title = url.split('//')[-1].split('/')[0]

    step_times['extract'] = time.time() - start_time - step_times.get('download', 0)
    print(f"[HTML-{index}] Extracted {len(cleaned_text)} chars in {step_times['extract']:.2f}s")

    # Progress: Clean/Score stage
    if progress_callback:
        try:
            progress_callback(index, 'clean', 70)
        except:
            pass

    # STEP 3: Quality scoring (heuristic)
    try:
        extracted_content = {
            'content': cleaned_text,
            'title': title
        }

        score, score_breakdown = scorer.score_content(
            html=html,
            url=url,
            extracted_content=extracted_content
        )
        quality_score = score
    except Exception as e:
        print(f"[HTML-{index}] Scoring error: {e}")
        quality_score = 50
        score_breakdown = {}

    step_times['scoring'] = time.time() - start_time - sum(step_times.values())
    print(f"[HTML-{index}] ⏱️ Scoring: {step_times['scoring']:.2f}s (score={quality_score})")

    # STEP 4: NLP analysis (optional)
    nlp_analysis = None
    try:
        nlp_analysis = nlp_analyzer.analyze_content(
            html=html,
            url=url,
            extracted_text=cleaned_text,
            title=title
        )
        nlp_score = nlp_analysis.get('nlp_score', quality_score)
    except Exception as e:
        print(f"[HTML-{index}] NLP error: {e}")
        nlp_score = quality_score
        nlp_analysis = {'error': str(e)}

    step_times['nlp'] = time.time() - start_time - sum(step_times.values())
    print(f"[HTML-{index}] ⏱️ NLP: {step_times['nlp']:.2f}s (nlp_score={nlp_score})")

    # Final score (weighted average: 70% heuristic, 30% NLP)
    final_score = int(quality_score * 0.7 + nlp_score * 0.3)

    # STEP 5: Extract HTML structure for JSON output & embeddings
    html_structure = None
    try:
        html_structure = _extract_html_structure(html, title, cleaned_text)
        step_times['structure'] = time.time() - start_time - sum(step_times.values())
        print(f"[HTML-{index}] Extracted {len(html_structure['blocks'])} blocks, {len(html_structure['sections'])} sections")
        print(f"[HTML-{index}] ⏱️ Structure: {step_times['structure']:.2f}s")
    except Exception as e:
        print(f"[HTML-{index}] [WARN] Structure extraction failed: {e}")

    # Determine status based on quality threshold
    if final_score >= settings.analysis.html_quality_threshold:
        status = 'success'
        quality_class = 'legit' if final_score >= 70 else 'maybe'
    else:
        status = 'filtered'
        quality_class = 'junk'
        print(f"[HTML-{index}] [ERROR] FILTERED: score={final_score} < threshold={settings.analysis.html_quality_threshold}")

    # Calculate metrics
    word_count = len(cleaned_text.split())
    char_count = len(cleaned_text)
    processing_time = time.time() - start_time

    # Generate doc_id (for deduplication/embedding)
    from services.helpers.url_utils import normalize_url, compute_content_hash

    normalized_url = normalize_url(url)
    doc_id = compute_content_hash(normalized_url + cleaned_text[:1000])

    # Print timing breakdown
    total_measured = sum(step_times.values())
    other_time = processing_time - total_measured
    print(f"[HTML-{index}] ⏱️ TIMING: Total={processing_time:.2f}s | Download={step_times.get('download',0):.2f}s | Extract={step_times.get('extract',0):.2f}s | Score={step_times.get('scoring',0):.2f}s | NLP={step_times.get('nlp',0):.2f}s | Structure={step_times.get('structure',0):.2f}s | Other={other_time:.2f}s")
    print(f"[HTML-{index}] SUCCESS: score={final_score}, words={word_count}, blocks={len(html_structure['blocks']) if html_structure else 0}")

    # Progress: Complete
    if progress_callback:
        try:
            progress_callback(index, 'complete', 100)
        except:
            pass

    # STEP 6: Cache result (TODO: Implement cache_html_result method)
    # cache_service = CacheService()
    # try:
    #     cache_service.cache_html_result(
    #         url=url,
    #         status=status,
    #         final_score=final_score,
    #         word_count=word_count,
    #         title=title,
    #         error=None if status == 'success' else f"Filtered (score={final_score})"
    #     )
    #     print(f"[HTML-{index}] [OK] Cached result for future use")
    # except Exception as e:
    #     print(f"[HTML-{index}] [WARN] Cache failed: {e}")

    # STEP 7: Trigger background embedding (if enabled and successful)
    if html_structure and status == 'success':
        try:
            if settings.embedding.enabled:
                from services.embedding_service import embed_document_async

                embed_document_async(
                    url=normalized_url,
                    doc_type='html',
                    chunks=html_structure['chunks'],
                    doc_id=doc_id
                )
                print(f"[HTML-{index}] 🚀 Started background embedding for {len(html_structure['chunks'])} chunks")
        except Exception as e:
            print(f"[HTML-{index}] ⚠️  Embedding failed: {e}")

    # STEP 8: Save JSON result (optional, for UI display)
    if html_structure and (status == 'success' or status == 'filtered'):
        try:
            json_dir = Path('outputs') / 'html_json'
            json_dir.mkdir(parents=True, exist_ok=True)

            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:16]
            domain = url.split('//')[-1].split('/')[0].replace('www.', '')
            safe_title = ''.join(c for c in (title or domain)[:50] if c.isalnum() or c in (' ', '-', '_')).strip()

            json_filename = f"{doc_id}_{safe_title}.json"
            json_path = json_dir / json_filename

            json_data = {
                'url': url,
                'title': title,
                'doc_id': doc_id,
                'status': status,
                'quality_class': quality_class,
                'final_score': final_score,
                'heuristic_score': quality_score,
                'nlp_score': nlp_score,
                'word_count': word_count,
                'char_count': char_count,
                'processing_time': processing_time,
                'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'content_preview': cleaned_text[:500],
                'structure': {
                    'blocks': html_structure['blocks'],
                    'sections': html_structure['sections'],
                    'chunks': html_structure['chunks']
                }
            }

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)

            print(f"[HTML-{index}] [JSON] Saved to {json_filename}")
        except Exception as e:
            print(f"[HTML-{index}] [WARN] JSON save failed: {e}")

    # Return complete result
    return {
        'status': status,
        'url': url,
        'index': index,
        'title': title,
        'content': cleaned_text,
        'content_preview': cleaned_text[:500],
        'doc_id': doc_id,
        'heuristic_score': quality_score,
        'nlp_score': nlp_score,
        'final_score': final_score,
        'quality_class': quality_class,
        'word_count': word_count,
        'char_count': char_count,
        'processing_time': processing_time,
        'extraction_method': 'trafilatura+readability+bs4',
        'blocks': html_structure['blocks'] if html_structure else [],
        'sections': html_structure['sections'] if html_structure else [],
        'chunks': html_structure['chunks'] if html_structure else []
    }


# Import threading for thread name logging
import threading
