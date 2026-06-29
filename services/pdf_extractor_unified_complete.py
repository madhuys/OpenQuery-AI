"""
Unified PDF Extractor - Complete (Phases 1-7)
PyMuPDF Only - Single pass extraction with full processing pipeline

Phases:
1. Validation
2-3. Extraction & Font Analysis (single pass)
4. Structure Detection & Block Creation (with batch cleaning)
5. Header/Footer Detection
6. Intelligent Chunking
7. Final Output Generation
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("❌ PyMuPDF not installed. Install with: pip install PyMuPDF")

try:
    from spellchecker import SpellChecker
    HAS_SPELLCHECKER = True
    # Initialize ONCE globally to avoid repeated initialization
    _GLOBAL_SPELL_CHECKER = SpellChecker() if HAS_SPELLCHECKER else None
except ImportError:
    HAS_SPELLCHECKER = False
    _GLOBAL_SPELL_CHECKER = None


# ============================================================================
# PHASE 1: VALIDATION
# ============================================================================

def validate_pdf_file(pdf_path: str) -> Tuple[bool, Optional[str]]:
    """
    Quick validation of PDF file before extraction
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        (is_valid, error_message)
    """
    path = Path(pdf_path)
    
    # Check file exists
    if not path.exists():
        return False, f"File not found: {pdf_path}"
    
    # Check file size
    file_size = path.stat().st_size
    if file_size == 0:
        return False, "File is empty (0 bytes)"
    
    if file_size > 500 * 1024 * 1024:  # > 500MB
        return False, f"File too large ({file_size / (1024*1024):.0f}MB, max 500MB)"
    
    # Check PDF header
    try:
        with open(path, 'rb') as f:
            header = f.read(8)
        
        if not header.startswith(b'%PDF-'):
            return False, "Not a valid PDF file (missing %PDF- header)"
    except Exception as e:
        return False, f"Cannot read file: {str(e)}"
    
    # Try opening with PyMuPDF
    if HAS_PYMUPDF:
        try:
            doc = fitz.open(str(path))
            doc.close()
        except Exception as e:
            error_msg = str(e).lower()
            if 'password' in error_msg or 'encrypted' in error_msg:
                return False, "PDF is password protected"
            elif 'corrupt' in error_msg or 'damaged' in error_msg:
                return False, "PDF file is corrupted"
            else:
                return False, f"Cannot open PDF: {str(e)}"
    
    return True, None


# ============================================================================
# PHASES 2-3: EXTRACTION & FONT ANALYSIS (Single Pass)
# ============================================================================

def _process_single_page(doc: 'fitz.Document', page_num: int) -> Tuple[Dict, List[float]]:
    """
    Process a single page - thread-safe helper function

    Args:
        doc: PyMuPDF document (thread-safe for reading)
        page_num: Page number to process (0-indexed)

    Returns:
        Tuple of (page_data dict, font_sizes list)
    """
    try:
        page = doc[page_num]

        # Get text with font information in ONE call
        blocks = page.get_text("dict")["blocks"]

        # Extract both text and font info together
        page_text = ""
        text_objects = []
        page_font_sizes = []

        for block in blocks:
            if "lines" in block:  # Text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span.get("text", "")
                        size = round(span.get("size", 0), 2)

                        # Collect text
                        page_text += text

                        # Collect font info
                        if text.strip():  # Skip empty spans
                            text_obj = {
                                'text': text,
                                'size': size,
                                'font': span.get("font", ""),
                                'flags': span.get("flags", 0),
                                'color': span.get("color", 0)
                            }
                            text_objects.append(text_obj)

                            # Collect for statistics (weighted by length)
                            if size > 0:
                                page_font_sizes.extend([size] * len(text))

                    page_text += "\n"

        # Calculate page stats
        char_count = len(page_text)
        word_count = len(page_text.split())

        page_data = {
            'page_number': page_num + 1,
            'text': page_text,
            'char_count': char_count,
            'word_count': word_count,
            'has_text': len(page_text.strip()) > 0,
            'text_objects': text_objects
        }

        return page_data, page_font_sizes

    except Exception as e:
        # Handle problematic pages gracefully
        page_data = {
            'page_number': page_num + 1,
            'text': '',
            'char_count': 0,
            'word_count': 0,
            'has_text': False,
            'text_objects': [],
            'error': str(e)
        }
        return page_data, []


def extract_pdf_with_fonts(pdf_path: str, max_pages: Optional[int] = None) -> Dict:
    """
    Extract EVERYTHING from PDF in one pass using PyMuPDF
    
    Single open, single pass extraction:
    - Metadata (title, author, dates, page count)
    - Text content (raw text per page)
    - Font information (sizes, names, styles, colors)
    - Statistics (character count, word count)
    
    Args:
        pdf_path: Path to PDF file
        max_pages: Optional limit on pages to process
        
    Returns:
        Dict with pages (text + text_objects) and font_stats
    """
    result = {
        'success': False,
        'error': None,
        'metadata': {},
        'pages': [],
        'font_stats': get_default_font_stats(),
        'total_characters': 0,
        'total_words': 0,
        'num_pages': 0
    }
    
    if not HAS_PYMUPDF:
        result['error'] = 'PyMuPDF not available'
        return result
    
    try:
        # ===== SINGLE OPEN =====
        doc = fitz.open(str(pdf_path))
        num_pages = len(doc)
        result['num_pages'] = num_pages
        
        # Limit pages if requested
        if max_pages:
            num_pages = min(num_pages, max_pages)
        
        # ===== EXTRACT METADATA =====
        result['metadata'] = extract_metadata(doc, num_pages)
        
        # ===== EXTRACT TEXT + FONTS (Parallel with Threading) =====
        pages_data = []
        all_font_sizes = []
        total_chars = 0
        total_words = 0

        # Determine thread count: use 4 threads for PDFs with 20+ pages, else 2
        # Cap at CPU count to avoid over-threading
        num_threads = min(4 if num_pages >= 20 else 2, os.cpu_count() or 2)

        # Use ThreadPoolExecutor for parallel page processing
        # PyMuPDF releases GIL, so threading provides true parallelism here
        page_executor = ThreadPoolExecutor(max_workers=num_threads)
        try:
            # Submit all page processing tasks
            future_to_page = {
                page_executor.submit(_process_single_page, doc, page_num): page_num
                for page_num in range(num_pages)
            }

            # Collect results as they complete
            page_results = {}
            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    page_data, page_font_sizes = future.result()
                    page_results[page_num] = (page_data, page_font_sizes)
                except Exception as e:
                    # Handle errors for this page
                    page_results[page_num] = ({
                        'page_number': page_num + 1,
                        'text': '',
                        'char_count': 0,
                        'word_count': 0,
                        'has_text': False,
                        'text_objects': [],
                        'error': str(e)
                    }, [])

            # Sort results by page number to maintain order
            for page_num in range(num_pages):
                page_data, page_font_sizes = page_results[page_num]
                pages_data.append(page_data)
                all_font_sizes.extend(page_font_sizes)
                total_chars += page_data['char_count']
                total_words += page_data['word_count']
        finally:
            # Explicitly shutdown and cleanup threads
            # Use wait=False to allow fast lane timeout to work
            page_executor.shutdown(wait=False)
            del page_executor
        
        doc.close()
        # ===== SINGLE CLOSE =====
        
        result['pages'] = pages_data
        result['total_characters'] = total_chars
        result['total_words'] = total_words
        
        # ===== ANALYZE FONT SIZES =====
        if all_font_sizes:
            result['font_stats'] = calculate_font_statistics(all_font_sizes)
        else:
            result['font_stats'] = get_default_font_stats()
            result['error'] = 'No font information extracted (scanned PDF?)'
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = f"PyMuPDF extraction failed: {str(e)}"
        result['success'] = False
    
    return result


def extract_metadata(doc: 'fitz.Document', num_pages: int) -> Dict:
    """
    Extract PDF metadata from open document
    
    Args:
        doc: Open PyMuPDF document
        num_pages: Number of pages
        
    Returns:
        Dict with metadata fields
    """
    try:
        metadata = doc.metadata
        
        return {
            'title': metadata.get('title', ''),
            'author': metadata.get('author', ''),
            'subject': metadata.get('subject', ''),
            'keywords': metadata.get('keywords', ''),
            'creator': metadata.get('creator', ''),
            'producer': metadata.get('producer', ''),
            'creation_date': metadata.get('creationDate', ''),
            'modification_date': metadata.get('modDate', ''),
            'format': metadata.get('format', ''),
            'encryption': metadata.get('encryption', ''),
            'num_pages': num_pages
        }
    except Exception as e:
        return {
            'num_pages': num_pages,
            'error': f"Metadata extraction failed: {str(e)}"
        }


def calculate_font_statistics(font_sizes: List[float]) -> Dict:
    """
    Calculate font size statistics and thresholds for structure detection
    
    Args:
        font_sizes: List of font sizes (weighted by character count)
        
    Returns:
        Dict with median, common size, thresholds, distribution
    """
    if not font_sizes:
        return get_default_font_stats()
    
    size_counter = Counter(font_sizes)
    sorted_sizes = sorted(font_sizes)
    unique_sizes = sorted(set(font_sizes))
    
    # Median size
    median_size = sorted_sizes[len(sorted_sizes) // 2]
    
    # Most common size (body text)
    common_size = size_counter.most_common(1)[0][0]
    body_size = common_size
    
    # Title: Largest size
    title_size = max(unique_sizes)
    
    # Subtext: Smaller than body
    sizes_below_body = [s for s in unique_sizes if s < body_size]
    subtext_size = min(sizes_below_body) if sizes_below_body else body_size * 0.8
    
    # Heading sizes - CORRECTED LOGIC
    sizes_above_body = [s for s in unique_sizes if s > body_size]

    if not sizes_above_body:
        # No headings detected, use calculated proportions
        h1_size = body_size * 1.5
        h2_size = body_size * 1.3
        h3_size = body_size * 1.2
        h4_size = body_size * 1.1
    else:
        # H4: Most common font size ABOVE body
        heading_counter = {s: size_counter[s] for s in sizes_above_body}
        h4_size = max(heading_counter.keys(), key=heading_counter.get)

        # H1: Most common font size BELOW title (excluding title itself)
        sizes_above_no_title = [s for s in sizes_above_body if s < title_size]
        if sizes_above_no_title:
            heading_counter_no_title = {s: size_counter[s] for s in sizes_above_no_title}
            h1_size = max(heading_counter_no_title.keys(), key=heading_counter_no_title.get)
        else:
            h1_size = title_size * 0.8

        # H2 and H3: Between H1 and H4
        if h1_size > h4_size:
            # H1 is bigger than H4 (expected)
            range_size = (h1_size - h4_size) / 3
            h2_size = h1_size - range_size
            h3_size = h4_size + range_size
        else:
            # H4 is bigger or equal to H1 (unusual, but handle it)
            # In this case H4 becomes the largest, H1 becomes smallest
            # Swap them and distribute
            h2_size = h4_size * 0.85
            h3_size = h4_size * 0.7
    
    thresholds = {
        'body': body_size,
        'title': title_size,
        'h1': h1_size,
        'h2': h2_size,
        'h3': h3_size,
        'h4': h4_size,
        'subtext': subtext_size
    }
    
    return {
        'median_size': round(median_size, 2),
        'common_size': round(common_size, 2),
        'thresholds': thresholds,
        'size_distribution': dict(size_counter.most_common(10)),
        'unique_sizes': unique_sizes[:20],  # Top 20 unique sizes
        'total_font_samples': len(font_sizes)
    }


def get_default_font_stats() -> Dict:
    """
    Get default font statistics (when analysis fails or no fonts found)
    
    Returns:
        Dict with default values
    """
    return {
        'median_size': 12.0,
        'common_size': 12.0,
        'thresholds': {
            'title': 24.0,
            'h1': 18.0,
            'h2': 16.0,
            'h3': 14.0,
            'h4': 13.0,
            'body': 12.0,
            'subtext': 10.0
        },
        'size_distribution': {},
        'unique_sizes': [],
        'total_font_samples': 0
    }


# ============================================================================
# PHASE 4: STRUCTURE DETECTION & BLOCK CREATION
# ============================================================================

def is_artifact(text: str) -> bool:
    """Quick artifact check - filter single chars, double chars, isolated numbers"""
    text_stripped = text.strip()
    if len(text_stripped) <= 2:
        return True
    if text_stripped.isdigit() and len(text_stripped) <= 4:
        return True
    return False


def clean_all_blocks_batch(blocks: List[Dict], enable_spell_check: bool = False) -> None:
    """
    Clean ALL blocks in one batch (called ONCE)
    Modifies blocks in-place for maximum efficiency
    
    Args:
        blocks: List of all blocks from all pages
        enable_spell_check: Enable spell checking (slower)
    """
    # Batch spell check if enabled
    corrections = {}
    if enable_spell_check and HAS_SPELLCHECKER and _GLOBAL_SPELL_CHECKER:
        first_words = {}
        for block in blocks:
            words = block['text'].split()
            if words:
                fw = words[0].lstrip('•-*→').lower()
                if fw and (fw[0].islower() or len(fw) < 4):
                    first_words[fw] = True
        
        # Check unique words ONCE
        for word in first_words:
            try:
                corrected = _GLOBAL_SPELL_CHECKER.correction(word)
                if corrected and corrected != word:
                    corrections[word] = corrected.capitalize()
            except:
                pass
    
    # Common OCR fixes (instant)
    common_fixes = {
        'rganizations': 'Organizations',
        'rganization': 'Organization',
        'rganizing': 'Organizing',
        'rganized': 'Organized',
        'pportunity': 'Opportunity',
        'pportunities': 'Opportunities',
        'perations': 'Operations',
        'peration': 'Operation',
        'nformation': 'Information',
        'mportant': 'Important',
        'mplementation': 'Implementation',
        'nnovation': 'Innovation',
        'ntegration': 'Integration',
    }
    
    # Apply cleaning to all blocks
    for block in blocks:
        text = block['text']
        
        # Fix mid-sentence breaks (simplified)
        text = re.sub(r'([a-z])\n([a-z])', r'\1 \2', text)
        
        # Apply corrections
        words = text.split()
        if words:
            fw = words[0].lstrip('•-*→')
            fw_lower = fw.lower()
            
            # Try common fixes first
            if fw in common_fixes:
                words[0] = words[0].replace(fw, common_fixes[fw])
            # Then spell check corrections
            elif fw_lower in corrections:
                words[0] = words[0].replace(fw, corrections[fw_lower])
            
            text = ' '.join(words)
        
        # Normalize whitespace
        text = re.sub(r' +', ' ', text).strip()
        
        # Update block in-place
        block['text'] = text


def classify_text_by_font_size(font_size: float, thresholds: Dict, text: str = '') -> str:
    """
    Classify text type based on font size and text content
    
    Args:
        font_size: Font size to classify
        thresholds: Dict of font size thresholds
        text: Text content (for word count rule)
    
    Returns:
        str: Text type (title, h1, h2, h3, h4, body, subtext)
    """
    # Rule: Headings with > 20 words should be body
    if text and len(text.split()) > 20:
        return 'body'
    
    if font_size >= thresholds['title']:
        return 'title'
    elif font_size >= thresholds['h1']:
        return 'h1'
    elif font_size >= thresholds['h2']:
        return 'h2'
    elif font_size >= thresholds['h3']:
        return 'h3'
    elif font_size >= thresholds['h4']:
        return 'h4'
    elif font_size >= thresholds['body'] * 0.95:  # Allow 5% tolerance
        return 'body'
    else:
        return 'subtext'


def extract_structured_blocks_from_spans(page: Dict, font_thresholds: Dict) -> List[Dict]:
    """
    Extract structured text blocks from text spans based on font sizes
    Groups consecutive spans of the same type into blocks
    NO CLEANING - returns raw blocks for batch processing
    
    Args:
        page: Page dict with text_objects
        font_thresholds: Font size thresholds
        
    Returns:
        List of raw blocks (uncleaned)
    """
    blocks = []
    text_objects = page.get('text_objects', [])
    
    if not text_objects:
        # No font info, return entire page as body text
        return [{
            'type': 'body',
            'text': page['text'],
            'font_size': font_thresholds['body']
        }]
    
    current_block = None
    
    for text_obj in text_objects:
        text = text_obj['text']
        size = text_obj['size']
        
        # Skip artifacts early
        if is_artifact(text):
            continue
        
        # Classify with text content for word count rule
        text_type = classify_text_by_font_size(size, font_thresholds, text=text)
        
        # Start new block or continue current one
        # Special case: if previous block ends mid-sentence (no punctuation), continue it
        # even if font size changed (common in PDFs with multi-line headings)
        is_sentence_continuation = False
        if current_block is not None:
            last_text = current_block['text'].rstrip()
            last_word = last_text.split()[-1] if last_text.split() else ''

            # Check if previous block ended mid-sentence
            if last_text and not last_text[-1] in '.!?:;,�':
                text_first_word = text.strip().split()[0] if text.strip().split() else ''

                # Continue if:
                # 1. New text starts lowercase
                # 2. Last word is possessive (ends with 's, ending with apostrophe)
                # 3. Last word is preposition/article (of, the, a, an, in, on, for, to, etc.)
                if text.strip() and (
                    text.strip()[0].islower() or
                    last_word.endswith(('�s', "'s", '�')) or  # Possessive
                    last_word.lower() in ['the', 'a', 'an', 'of', 'in', 'on', 'for', 'to', 'with', 'by', 'from', 'at', 'as', 'is', 'are', 'was', 'were']
                ):
                    is_sentence_continuation = True

        if current_block is None or (current_block['type'] != text_type and not is_sentence_continuation):
            # Save previous block
            if current_block is not None:
                blocks.append(current_block)

            # Start new block
            current_block = {
                'type': text_type,
                'font_size': size,
                'font': text_obj.get('font', ''),
                'text': text
            }
        else:
            # Continue current block (same type OR sentence continuation)
            # Smart joining: preserve natural spacing from PDF
            if current_block['text'].endswith((' ', '\n', '\t', '-')):
                current_block['text'] += text
            elif text.startswith((' ', '\n', '\t')):
                current_block['text'] += text
            else:
                current_block['text'] += ' ' + text
    
    # Add last block
    if current_block is not None:
        blocks.append(current_block)
    
    # Filter artifacts - NO CLEANING
    raw_blocks = []
    for block in blocks:
        text = block['text'].strip()

        if text and not is_artifact(text):
            block_type = block['type']

            # POST-PROCESSING: Reclassify long "headings" as body text
            # Real headings are typically short (< 150 characters or < 25 words)
            if block_type in ['title', 'h1', 'h2', 'h3', 'h4']:
                word_count = len(text.split())
                char_count = len(text)

                # If heading is too long, it's actually body text
                if word_count > 25 or char_count > 150:
                    block_type = 'body'

            raw_blocks.append({
                'type': block_type,
                'text': text,
                'font_size': block['font_size'],
                'font': block.get('font', ''),
                'original_type': block['type']  # Keep original for debugging
            })

    return raw_blocks


# ============================================================================
# PHASE 5: HEADER/FOOTER DETECTION
# ============================================================================

def detect_headers_footers(structured_pages: List[Dict]) -> List[Dict]:
    """
    Detect headers and footers across pages (OPTIMIZED with sampling + defaultdict)

    Rules:
    1. If a text block appears on most pages (≥50%), it's a header/footer
    2. Only check if document has > 7 pages
    3. Check ALL blocks on each page (not just first/last)
    4. Mark detected blocks as 'header_footer' type

    Optimizations:
    - For large PDFs (>100 pages), sample 50% of pages for detection
    - Use defaultdict(set) for faster lookups

    Args:
        structured_pages: List of page dicts with blocks

    Returns:
        list: Updated pages with header/footer blocks marked
    """
    import random

    total_pages = len(structured_pages)

    # Only detect headers/footers if document has > 7 pages
    if total_pages <= 7:
        return structured_pages

    # OPTIMIZATION 1: Sample 50% for large documents
    if total_pages > 100:
        sample_size = total_pages // 2
        sampled_indices = set(random.sample(range(total_pages), sample_size))
        pages_to_check = [p for i, p in enumerate(structured_pages) if i in sampled_indices]
        threshold = sample_size // 2
    else:
        pages_to_check = structured_pages
        threshold = total_pages // 2

    # OPTIMIZATION 2: Use defaultdict for faster insertion
    text_occurrences = defaultdict(set)

    for page in pages_to_check:
        page_num = page['page_number']
        blocks = page.get('blocks', [])

        if not blocks:
            continue

        # Check ALL blocks on the page
        for block in blocks:
            text = block['text'].strip()

            # Normalize text for comparison (pre-compute once)
            normalized = ' '.join(text.lower().split())

            # Skip very short text (< 10 chars)
            if len(normalized) < 10:
                continue

            text_occurrences[normalized].add(page_num)
    
    # Find texts that appear on threshold or more pages
    header_footer_texts = set()
    
    for normalized_text, pages_set in text_occurrences.items():
        if len(pages_set) >= threshold:
            header_footer_texts.add(normalized_text)
    
    # Mark blocks as header/footer in the structured pages
    marked_count = 0
    for page in structured_pages:
        blocks = page.get('blocks', [])
        
        for block in blocks:
            text = block['text'].strip()
            normalized = ' '.join(text.lower().split())
            
            if normalized in header_footer_texts:
                # Mark as header/footer
                block['type'] = 'header_footer'
                block['is_header_footer'] = True
                marked_count += 1
    
    return structured_pages


# ============================================================================
# PHASE 6: INTELLIGENT CHUNKING
# ============================================================================

def create_chunks_from_blocks(structured_pages: List[Dict]) -> List[Dict]:
    """
    Create chunks from structured blocks
    
    Rules:
    - Group consecutive headings together
    - Include all body/subtext content until next heading
    - Max 1000 characters per chunk
    - Split with -cs naming (character split)
    - Merge empty chunks with next chunk
    """
    chunks = []
    chunk_counter = 0
    
    heading_types = ['title', 'h1', 'h2', 'h3', 'h4']
    content_types = ['body', 'subtext']
    
    for page in structured_pages:
        blocks = page.get('blocks', [])
        
        current_chunk = None
        current_chunk_id = None
        
        for block in blocks:
            block_type = block['type']
            block_text = block['text']
            
            # Skip header/footer blocks
            if block_type == 'header_footer' or block.get('is_header_footer', False):
                continue
            
            if block_type in heading_types:
                # Heading block
                if current_chunk and current_chunk.get('has_body', False):
                    chunks.extend(split_chunk_if_needed(current_chunk, current_chunk_id))
                    current_chunk = None
                
                if current_chunk is None:
                    chunk_counter += 1
                    current_chunk_id = f"chunk_{chunk_counter}"
                    current_chunk = {
                        'chunk_id': current_chunk_id,
                        'page_number': page['page_number'],
                        'headings': [],
                        'content': '',
                        'has_body': False,
                        'blocks': []
                    }
                
                current_chunk['headings'].append({
                    'type': block_type,
                    'text': block_text
                })
                current_chunk['blocks'].append(block)
            
            elif block_type in content_types:
                # Body/subtext content
                if current_chunk is None:
                    chunk_counter += 1
                    current_chunk_id = f"chunk_{chunk_counter}"
                    current_chunk = {
                        'chunk_id': current_chunk_id,
                        'page_number': page['page_number'],
                        'headings': [],
                        'content': '',
                        'has_body': False,
                        'blocks': []
                    }
                
                current_chunk['content'] += block_text + '\n'
                current_chunk['has_body'] = True
                current_chunk['blocks'].append(block)
        
        # Save last chunk of page
        if current_chunk:
            chunks.extend(split_chunk_if_needed(current_chunk, current_chunk_id))
    
    # Post-processing: Merge heading-only chunks with next chunk
    merged_chunks = []
    pending_headings = []
    
    for chunk in chunks:
        has_content = chunk.get('content', '').strip() != ''
        
        if has_content:
            if pending_headings:
                chunk['headings'] = pending_headings + chunk['headings']
                pending_headings = []
            merged_chunks.append(chunk)
        else:
            pending_headings.extend(chunk.get('headings', []))
    
    # Add leftover headings
    if pending_headings:
        merged_chunks.append({
            'chunk_id': f"chunk_{len(merged_chunks) + 1}",
            'page_number': chunks[-1]['page_number'] if chunks else 1,
            'headings': pending_headings,
            'heading_text': '\n'.join([f"{h['type'].upper()}: {h['text']}" for h in pending_headings]),
            'content': '',
            'char_count': sum(len(h['text']) for h in pending_headings),
            'word_count': sum(len(h['text'].split()) for h in pending_headings),
            'is_split': False
        })
    
    return merged_chunks


def split_chunk_if_needed(chunk: Dict, base_chunk_id: str) -> List[Dict]:
    """
    Split chunk if it exceeds 1000 characters
    
    Args:
        chunk: Chunk dict with headings and content
        base_chunk_id: Base chunk ID (e.g., "chunk_5")
    
    Returns:
        list: List of chunks (split if needed with -cs1, -cs2, etc.)
    """
    MAX_CHUNK_SIZE = 1000
    
    headings = chunk.get('headings', [])
    heading_lines = []
    for h in headings:
        heading_lines.append(f"{h['type'].upper()}: {h['text']}")
    
    heading_text = '\n'.join(heading_lines)
    content_text = chunk.get('content', '').strip()
    
    full_text = heading_text
    if content_text:
        full_text += '\n' + content_text
    
    total_size = len(full_text)
    
    # If under limit, return as-is
    if total_size <= MAX_CHUNK_SIZE:
        return [{
            'chunk_id': base_chunk_id,
            'page_number': chunk['page_number'],
            'headings': headings,
            'heading_text': heading_text,
            'content': content_text,
            'char_count': total_size,
            'word_count': len(full_text.split()),
            'is_split': False
        }]
    
    # Need to split
    result_chunks = []
    page_number = chunk['page_number']
    heading_size = len(heading_text)
    remaining_content = content_text
    sub_chunk_index = 1
    
    while True:
        if sub_chunk_index == 1:
            # First chunk includes all headings
            available_for_content = MAX_CHUNK_SIZE - heading_size - 1
            
            if available_for_content <= 0:
                # Headings alone exceed limit
                result_chunks.append({
                    'chunk_id': f"{base_chunk_id}-cs{sub_chunk_index}",
                    'page_number': page_number,
                    'headings': headings,
                    'heading_text': heading_text,
                    'content': '',
                    'char_count': heading_size,
                    'word_count': len(heading_text.split()),
                    'is_split': True,
                    'split_part': sub_chunk_index
                })
                sub_chunk_index += 1
            else:
                content_chunk = remaining_content[:available_for_content]
                remaining_content = remaining_content[available_for_content:]
                
                result_chunks.append({
                    'chunk_id': f"{base_chunk_id}-cs{sub_chunk_index}",
                    'page_number': page_number,
                    'headings': headings,
                    'heading_text': heading_text,
                    'content': content_chunk,
                    'char_count': heading_size + len(content_chunk) + 1,
                    'word_count': len((heading_text + ' ' + content_chunk).split()),
                    'is_split': True,
                    'split_part': sub_chunk_index
                })
                sub_chunk_index += 1
                
                if not remaining_content:
                    break
        else:
            # Continuation chunks
            abbreviated_heading = "(continued)"
            if headings:
                first_heading = headings[0]['text'][:50]
                abbreviated_heading = f"(continued from: {first_heading}...)"
            
            content_chunk = remaining_content[:MAX_CHUNK_SIZE]
            remaining_content = remaining_content[MAX_CHUNK_SIZE:]
            
            result_chunks.append({
                'chunk_id': f"{base_chunk_id}-cs{sub_chunk_index}",
                'page_number': page_number,
                'headings': [],
                'heading_text': abbreviated_heading,
                'content': content_chunk,
                'char_count': len(content_chunk),
                'word_count': len(content_chunk.split()),
                'is_split': True,
                'split_part': sub_chunk_index
            })
            sub_chunk_index += 1
            
            if not remaining_content:
                break
    
    return result_chunks


# ============================================================================
# PHASE 7: FINAL OUTPUT GENERATION
# ============================================================================

def generate_fingerprint(metadata: Dict, file_size_mb: float) -> Tuple[str, str]:
    """Generate fingerprint from metadata"""
    title = (metadata.get('title') or '').lower().strip()
    author = (metadata.get('author') or '').lower().strip()
    creation_date = metadata.get('creation_date') or ''
    file_size = str(file_size_mb)
    
    # Filter out placeholder values
    if title in ['none', 'null', '']:
        title = ''
    if author in ['none', 'null', '']:
        author = ''
    
    # Build fingerprint string
    fingerprint_str = f"{title}|{author}|{creation_date}|{file_size}"
    
    # Hash
    fingerprint = hashlib.sha256(fingerprint_str.encode('utf-8')).hexdigest()
    
    return fingerprint, fingerprint_str


# ============================================================================
# COMPLETE EXTRACTION (All Phases)
# ============================================================================

def create_sections_from_flat_blocks(content_blocks: List[Dict]) -> List[Dict]:
    """
    Group content blocks into sections based on heading hierarchy

    Sections start with h1 or h2 level headings
    """
    sections = []
    current_section = None
    section_counter = 0

    for block in content_blocks:
        block_type = block.get('type', '')
        original_type = block.get('original_type', '')

        # Start new section on major headings (h1, h2, or title)
        if original_type in ['h1', 'h2', 'title']:
            # Save previous section
            if current_section and current_section['blocks']:
                sections.append(current_section)

            # Start new section
            section_counter += 1
            current_section = {
                'section_id': f's{section_counter}',
                'heading': block.get('text', ''),
                'heading_level': original_type,
                'blocks': [],
                'start_page': block.get('page_number', 1),
                'end_page': block.get('page_number', 1)
            }

        # Add block to current section
        if current_section is None:
            # Create initial section if doc starts without heading
            section_counter += 1
            current_section = {
                'section_id': f's{section_counter}',
                'heading': '(Document Start)',
                'heading_level': 'none',
                'blocks': [],
                'start_page': block.get('page_number', 1),
                'end_page': block.get('page_number', 1)
            }

        current_section['blocks'].append(block)
        current_section['end_page'] = max(
            current_section['end_page'],
            block.get('page_number', 1)
        )

    # Save last section
    if current_section and current_section['blocks']:
        sections.append(current_section)

    return sections


def chunk_section_blocks(section: Dict, max_chars: int = 1000) -> List[Dict]:
    """
    Break a section into chunks of max_chars size

    Each chunk contains:
    - chunk_id: s<n>-c<m>
    - blocks: list of content blocks with page numbers
    - page_numbers: list of unique pages in this chunk
    - char_count: total characters
    """
    section_id = section['section_id']
    blocks = section['blocks']

    chunks = []
    current_chunk = {
        'blocks': [],
        'char_count': 0,
        'page_numbers': set()
    }
    chunk_counter = 0

    for block in blocks:
        block_text = block.get('text', '')
        block_chars = len(block_text)
        page_num = block.get('page_number', 1)

        # Check if adding this block exceeds limit
        if current_chunk['char_count'] + block_chars > max_chars and current_chunk['blocks']:
            # Save current chunk
            chunk_counter += 1
            chunks.append({
                'chunk_id': f'{section_id}-c{chunk_counter}',
                'blocks': current_chunk['blocks'],
                'page_numbers': sorted(list(current_chunk['page_numbers'])),
                'char_count': current_chunk['char_count']
            })

            # Start new chunk
            current_chunk = {
                'blocks': [],
                'char_count': 0,
                'page_numbers': set()
            }

        # Add block to current chunk
        current_chunk['blocks'].append(block)
        current_chunk['char_count'] += block_chars
        current_chunk['page_numbers'].add(page_num)

    # Save last chunk
    if current_chunk['blocks']:
        chunk_counter += 1
        chunks.append({
            'chunk_id': f'{section_id}-c{chunk_counter}',
            'blocks': current_chunk['blocks'],
            'page_numbers': sorted(list(current_chunk['page_numbers'])),
            'char_count': current_chunk['char_count']
        })

    return chunks


def merge_small_chunks(chunks: List[Dict], min_chars: int = 500) -> List[Dict]:
    """
    Merge chunks that are smaller than min_chars with adjacent chunks

    Rules:
    - If chunk is too small and NOT the last chunk: merge with NEXT chunk
    - If chunk is too small and IS the last chunk: merge with PREVIOUS chunk
    - Continue merging until chunk reaches minimum 500 characters
    - Preserve all block information, page numbers, and chunk IDs

    Args:
        chunks: List of chunk dicts with blocks, char_count, page_numbers, chunk_id
        min_chars: Minimum characters per chunk (default 500)

    Returns:
        List of merged chunks meeting minimum size requirement
    """
    if not chunks:
        return chunks

    # Track merge statistics
    chunks_before = len(chunks)
    chunks_merged = 0

    merged_chunks = []
    i = 0

    while i < len(chunks):
        current_chunk = chunks[i].copy()
        current_char_count = current_chunk.get('char_count', 0)

        # Check if current chunk is too small
        while current_char_count < min_chars:
            # If not the last chunk, try to merge with next
            if i + 1 < len(chunks):
                next_chunk = chunks[i + 1]

                # Merge next chunk into current
                current_chunk['blocks'].extend(next_chunk['blocks'])

                # Update page numbers (combine sets and sort)
                current_pages = set(current_chunk.get('page_numbers', []))
                next_pages = set(next_chunk.get('page_numbers', []))
                current_chunk['page_numbers'] = sorted(list(current_pages | next_pages))

                # Update char count
                current_char_count += next_chunk.get('char_count', 0)
                current_chunk['char_count'] = current_char_count

                # Update chunk_id to indicate merge (keep first chunk's ID)
                # but add a note that it was merged
                if 'merged_from' not in current_chunk:
                    current_chunk['merged_from'] = [current_chunk['chunk_id']]
                current_chunk['merged_from'].append(next_chunk['chunk_id'])

                # Move forward to skip the merged chunk
                i += 1
                chunks_merged += 1

            # If this is the last chunk (or became last after merges) and still too small
            elif i > 0:
                # Merge current chunk into the previous chunk in merged_chunks
                if merged_chunks:
                    prev_chunk = merged_chunks[-1]

                    # Merge current into previous
                    prev_chunk['blocks'].extend(current_chunk['blocks'])

                    # Update page numbers
                    prev_pages = set(prev_chunk.get('page_numbers', []))
                    curr_pages = set(current_chunk.get('page_numbers', []))
                    prev_chunk['page_numbers'] = sorted(list(prev_pages | curr_pages))

                    # Update char count
                    prev_chunk['char_count'] = prev_chunk.get('char_count', 0) + current_char_count

                    # Track merge
                    if 'merged_from' not in prev_chunk:
                        prev_chunk['merged_from'] = [prev_chunk['chunk_id']]
                    prev_chunk['merged_from'].append(current_chunk['chunk_id'])

                    # Don't add current_chunk separately since it was merged
                    current_chunk = None
                    chunks_merged += 1
                    break
                else:
                    # First chunk and it's too small - keep it anyway
                    break
            else:
                # Single chunk that's too small - keep it anyway
                break

        # Add the current chunk if it wasn't merged into previous
        if current_chunk is not None:
            merged_chunks.append(current_chunk)

        i += 1

    # Log merge statistics (summary only)
    chunks_after = len(merged_chunks)
    if chunks_merged > 0:
        # Only log summary, not every merge operation
        pass  # Removed verbose per-merge logging

    return merged_chunks


def restructure_content_to_sections(content_blocks: List[Dict]) -> List[Dict]:
    """
    Restructure flat content array to Section → Chunk → Blocks hierarchy

    Input: Flat array of blocks with page numbers
    Output: Array of sections with chunked blocks
    """
    # Step 1: Create sections
    sections = create_sections_from_flat_blocks(content_blocks)

    # Step 2: Chunk each section
    restructured_sections = []

    for section in sections:
        chunks = chunk_section_blocks(section, max_chars=1000)

        # Step 3: Merge small chunks to ensure minimum 500 characters
        merged_chunks = merge_small_chunks(chunks, min_chars=500)

        restructured_section = {
            'section_id': section['section_id'],
            'heading': section['heading'],
            'heading_level': section['heading_level'],
            'start_page': section['start_page'],
            'end_page': section['end_page'],
            'chunks': merged_chunks
        }

        restructured_sections.append(restructured_section)

    return restructured_sections


def extract_pdf_complete(pdf_path: str, max_pages: Optional[int] = None, enable_spell_check: bool = False) -> Dict:
    """
    Complete PDF extraction pipeline (Phases 1-7)

    Args:
        pdf_path: Path to PDF file
        max_pages: Optional limit on pages to process
        enable_spell_check: Enable spell checking (slower, off by default)

    Returns:
        Dict with comprehensive structured output
    """
    # Phase 1: Validation
    is_valid, error_msg = validate_pdf_file(pdf_path)
    if not is_valid:
        return {
            'success': False,
            'error': error_msg,
            'file_path': str(pdf_path)
        }
    
    # Phases 2-3: Extraction & Font Analysis
    result = extract_pdf_with_fonts(pdf_path, max_pages)
    
    if not result['success']:
        return result
    
    # Phase 4: Structure Detection (Parallel with Threading)
    font_thresholds = result['font_stats']['thresholds']
    structured_pages = []
    all_blocks = []  # Collect for batch cleaning

    # Use threading for structure detection (same as page extraction)
    # Determine thread count
    total_pages = result['num_pages']
    num_structure_threads = min(4 if total_pages >= 20 else 2, os.cpu_count() or 2)

    def _extract_blocks_for_page(page_data, thresholds):
        """Extract structured blocks for a single page - thread-safe"""
        blocks = extract_structured_blocks_from_spans(page_data, thresholds)
        return {
            'page_number': page_data['page_number'],
            'text': page_data['text'],
            'char_count': page_data['char_count'],
            'blocks': blocks
        }

    # Process pages in parallel
    structure_executor = ThreadPoolExecutor(max_workers=num_structure_threads)
    try:
        futures = {
            structure_executor.submit(_extract_blocks_for_page, page, font_thresholds): idx
            for idx, page in enumerate(result['pages'])
        }

        # Collect results maintaining order
        page_results = {}
        for future in as_completed(futures):
            page_idx = futures[future]
            page_results[page_idx] = future.result()

        # Sort by page index and collect all blocks
        for idx in range(len(result['pages'])):
            page_result = page_results[idx]
            structured_pages.append(page_result)
            all_blocks.extend(page_result['blocks'])
    finally:
        # Explicitly shutdown and cleanup threads
        # Use wait=False to allow fast lane timeout to work
        structure_executor.shutdown(wait=False)
        del structure_executor
    
    # Phase 4B: Batch clean ALL blocks ONCE
    clean_all_blocks_batch(all_blocks, enable_spell_check=enable_spell_check)
    
    # Phase 5: Header/Footer Detection
    structured_pages = detect_headers_footers(structured_pages)
    
    # Phase 6: Intelligent Chunking
    chunks = create_chunks_from_blocks(structured_pages)
    
    # Phase 7: Final Output
    file_size_mb = round(Path(pdf_path).stat().st_size / (1024 * 1024), 2)
    fingerprint, fingerprint_str = generate_fingerprint(result['metadata'], file_size_mb)
    
    # Count blocks by type
    block_counts = defaultdict(int)
    for page in structured_pages:
        for block in page.get('blocks', []):
            block_counts[block['type']] += 1
    
    # Count chunks
    total_chunks = len(chunks)
    split_chunks = len([c for c in chunks if c.get('is_split', False)])
    
    # Flatten blocks for backward compatibility
    all_blocks_output = []
    for page in structured_pages:
        for block in page.get('blocks', []):
            all_blocks_output.append({
                'type': 'heading' if block['type'] in ['title', 'h1', 'h2', 'h3', 'h4'] else 'paragraph',
                'text': block.get('text', ''),
                'page_number': page['page_number'],
                'font_size': block.get('font_size', 0),
                'original_type': block['type']
            })

    # TITLE DETECTION FALLBACK: Extract from content if metadata is empty
    # Cascade: 1) title block → 2) first heading → 3) first body sentence
    metadata_title = (result['metadata'].get('title') or '').strip()
    extracted_title = metadata_title

    if not metadata_title or metadata_title.lower() in ['none', 'null', 'untitled', '']:
        # Step 1: Try to find first 'title' block (first 3 pages)
        for page in structured_pages[:3]:
            for block in page.get('blocks', []):
                if block['type'] == 'title' and block.get('text', '').strip():
                    extracted_title = block['text'].strip()
                    break
            if extracted_title and extracted_title != metadata_title:
                break

        # Step 2: If no title block, use first heading (h1-h4)
        if not extracted_title or extracted_title == metadata_title:
            for page in structured_pages[:3]:
                for block in page.get('blocks', []):
                    if block['type'] in ['h1', 'h2', 'h3', 'h4'] and block.get('text', '').strip():
                        extracted_title = block['text'].strip()
                        break
                if extracted_title and extracted_title != metadata_title:
                    break

        # Step 3: If no heading, use first sentence from body text
        if not extracted_title or extracted_title == metadata_title:
            for page in structured_pages[:3]:
                for block in page.get('blocks', []):
                    if block['type'] == 'body' and block.get('text', '').strip():
                        # Extract first sentence (up to first period, exclamation, or question mark)
                        text = block['text'].strip()
                        # Find first sentence ending
                        for delimiter in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                            if delimiter in text:
                                extracted_title = text.split(delimiter)[0] + delimiter[0]
                                break
                        # If no sentence delimiter, take first 100 chars
                        if not extracted_title or extracted_title == metadata_title:
                            extracted_title = text[:100] + ('...' if len(text) > 100 else '')
                        break
                if extracted_title and extracted_title != metadata_title:
                    break

        # Update metadata with extracted title
        if extracted_title and extracted_title != metadata_title:
            result['metadata']['title'] = extracted_title

    # PHASE 8: Restructure content to Section → Chunk → Blocks hierarchy
    restructured_sections = restructure_content_to_sections(all_blocks_output)
    total_restructured_chunks = sum(len(s['chunks']) for s in restructured_sections)

    return {
        'success': True,
        'profile': 'unified_complete:v1.0',
        'doc_id': fingerprint[:16],
        'fingerprint': fingerprint,
        'file_name': Path(pdf_path).name,
        'file_path': str(pdf_path),
        'file_size_mb': file_size_mb,
        'metadata': result['metadata'],
        'num_pages': result['num_pages'],
        'total_words': result['total_words'],
        'total_characters': result['total_characters'],
        'content': restructured_sections,  # Section → Chunk → Blocks hierarchy
        'pages': structured_pages,
        'chunks': chunks,
        'font_stats': result['font_stats'],
        'structure': {
            'font_thresholds': result['font_stats']['thresholds'],
            'block_counts': dict(block_counts),
            'chunk_count': total_chunks,
            'split_chunk_count': split_chunks,
            'section_count': len(restructured_sections),
            'restructured_chunk_count': total_restructured_chunks,
            'hierarchy': 'Section → Chunk → Page → Blocks'
        }
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def check_if_scanned_pdf(pdf_path: str, check_pages: int = 5) -> bool:
    """
    Quick check if PDF is scanned (image-based, no extractable text)
    """
    if not HAS_PYMUPDF:
        return False
    
    try:
        doc = fitz.open(str(pdf_path))
        num_pages = min(check_pages, len(doc))
        
        for page_num in range(num_pages):
            page = doc[page_num]
            text = page.get_text()
            
            if len(text.strip()) > 100:
                doc.close()
                return False
        
        doc.close()
        return True
        
    except Exception:
        return False


# ============================================================================
# MAIN EXTRACTOR CLASS
# ============================================================================

class PDFExtractor:
    """
    Unified PDF Extractor - All 7 Phases
    
    Extracts metadata, text, font information, structure, and chunks
    """
    
    def __init__(self, max_pages: Optional[int] = None, enable_spell_check: bool = False):
        """
        Initialize extractor
        
        Args:
            max_pages: Optional limit on pages to process
            enable_spell_check: Enable spell checking (slower, off by default)
        """
        if not HAS_PYMUPDF:
            raise RuntimeError("PyMuPDF not available - install with: pip install PyMuPDF")
        
        self.max_pages = max_pages
        self.enable_spell_check = enable_spell_check
    
    def extract(self, pdf_path: str) -> Dict:
        """
        Extract all information from PDF (All 7 Phases)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with complete extraction results
        """
        return extract_pdf_complete(pdf_path, self.max_pages, self.enable_spell_check)
    
    def extract_metadata_only(self, pdf_path: str) -> Dict:
        """
        Extract only metadata (fast, no text extraction)
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict with metadata
        """
        try:
            doc = fitz.open(str(pdf_path))
            metadata = extract_metadata(doc, len(doc))
            doc.close()
            
            return {
                'success': True,
                'metadata': metadata
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor_unified_complete.py <pdf_file>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    print(f"\n{'='*80}")
    print(f"UNIFIED PDF EXTRACTOR - Complete (Phases 1-7)")
    print(f"{'='*80}")
    print(f"File: {pdf_path}\n")
    
    # Create extractor
    extractor = PDFExtractor()
    
    # Extract
    print("Extracting...")
    result = extractor.extract(pdf_path)
    
    if result['success']:
        print(f"\n✅ SUCCESS!\n")
        print(f"Document ID: {result['doc_id']}")
        print(f"Fingerprint: {result['fingerprint'][:32]}...")
        
        print(f"\nMetadata:")
        print(f"  Title: {result['metadata'].get('title', 'N/A')}")
        print(f"  Author: {result['metadata'].get('author', 'N/A')}")
        print(f"  Pages: {result['num_pages']}")
        
        print(f"\nText Stats:")
        print(f"  Characters: {result['total_characters']:,}")
        print(f"  Words: {result['total_words']:,}")
        
        print(f"\nFont Analysis:")
        font_stats = result['font_stats']
        print(f"  Median size: {font_stats['median_size']}pt")
        print(f"  Body size: {font_stats['thresholds']['body']}pt")
        print(f"  Title size: {font_stats['thresholds']['title']}pt")
        print(f"  Font samples: {font_stats.get('total_font_samples', 0):,}")
        
        print(f"\nStructure:")
        for block_type, count in result['structure']['block_counts'].items():
            print(f"  {block_type:15s}: {count:4d}")
        
        print(f"\nChunks: {result['structure']['chunk_count']}")
        print(f"Split chunks: {result['structure']['split_chunk_count']}")
        
        print(f"\nThresholds:")
        for level, size in font_stats['thresholds'].items():
            print(f"  {level:8s}: {size:5.1f}pt")
    
    else:
        print(f"\n❌ FAILED!")
        print(f"Error: {result['error']}")