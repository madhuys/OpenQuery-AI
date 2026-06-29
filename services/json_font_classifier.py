"""
JSON Font Classifier & Document Restructurer

Takes raw PDF extraction JSON and applies sophisticated font-based classification:
- Top-10 font analysis
- Relative quartile-based heading assignment
- Header/footer detection
- Section boundary detection
- Smart chunking

This runs AFTER pdf_extractor_unified_complete.py and BEFORE final output.
"""

from typing import Dict, List, Optional, Tuple, Set
from collections import Counter, defaultdict
import re


class FontClassifier:
    """
    Implements the full classification rules:
    A) Block extraction (already done by PDF extractor)
    B) Header/Footer filtering
    C) Top-10 fonts scope
    D) Body size detection
    E) Title selection (≥10 chars)
    F) Relative heading bands (quartiles)
    G) Block type assignment
    H) Sectioning
    I) Chunking
    J) Diagnostics
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.header_footer_margin_pct = self.config.get('header_footer_margin_pct', 8)
        self.header_footer_recurrence_threshold = self.config.get('header_footer_recurrence_pct', 60)
        self.max_chunk_chars = self.config.get('max_chunk_chars', 1000)
        self.title_min_chars = self.config.get('title_min_chars', 10)
        self.max_heading_chars = self.config.get('max_heading_chars', 200)

    def process_document(self, pdf_extraction: Dict) -> Dict:
        """
        Main entry point: takes raw PDF extraction and returns classified document

        Args:
            pdf_extraction: Output from pdf_extractor_unified_complete.py

        Returns:
            Classified document with new structure
        """
        # Extract pages data
        pages_data = pdf_extraction.get('pages', [])
        if not pages_data:
            return pdf_extraction

        # Get page dimensions from first page (assume uniform)
        page_height = self._estimate_page_height(pages_data)

        # Step B: Mark header/footer blocks
        self._mark_header_footer_blocks(pages_data, page_height)

        # Step C: Compute top-10 fonts (by character coverage)
        top_10_fonts = self._compute_top_10_fonts(pages_data)

        # Step D: Determine body size (modal size from top-10)
        body_pt = self._determine_body_size(pages_data, top_10_fonts)

        # Step E: Select title size (largest ≥10 chars, from top-10)
        title_pt = self._select_title_size(pages_data, top_10_fonts, body_pt)

        # Step F: Compute relative quartile thresholds
        quartile_thresholds = self._compute_quartile_thresholds(body_pt, title_pt)

        # Step G: Classify all blocks
        self._classify_blocks(pages_data, top_10_fonts, body_pt, title_pt, quartile_thresholds)

        # Step H: Create sections
        sections = self._create_sections(pages_data)

        # Step I: Chunk sections
        self._chunk_sections(sections)

        # Step J: Build analysis/diagnostics
        analysis = self._build_analysis(
            top_10_fonts, body_pt, title_pt, quartile_thresholds, pages_data, sections
        )

        # Build final output structure
        return self._build_output(pdf_extraction, pages_data, sections, analysis, top_10_fonts)

    # ========================================================================
    # STEP B: Header/Footer Detection
    # ========================================================================

    def _estimate_page_height(self, pages_data: List[Dict]) -> float:
        """Estimate page height from blocks or default to 792pt (US Letter)"""
        # Try to get from first page blocks with bbox
        for page in pages_data[:3]:
            blocks = page.get('blocks', [])
            for block in blocks:
                bbox = block.get('bbox')
                if bbox and len(bbox) == 4:
                    # bbox = [x0, y0, x1, y1]
                    return max(bbox[1], bbox[3]) + 50  # Add margin

        return 792.0  # Default US Letter height

    def _mark_header_footer_blocks(self, pages_data: List[Dict], page_height: float):
        """
        Mark blocks as header_footer if:
        1. In top/bottom 8% of page
        2. Identical/near-identical text on ≥60% of pages
        """
        margin_height = page_height * (self.header_footer_margin_pct / 100.0)
        top_threshold = margin_height
        bottom_threshold = page_height - margin_height

        # Track recurring text across pages
        text_page_counts = defaultdict(set)  # text -> set of page numbers

        for page in pages_data:
            page_no = page.get('page_number', 0)
            blocks = page.get('blocks', [])

            for block in blocks:
                bbox = block.get('bbox')
                text = block.get('text', '').strip()

                if not text:
                    continue

                # Check position
                if bbox and len(bbox) == 4:
                    y0, y1 = bbox[1], bbox[3]
                    in_margin = y0 <= top_threshold or y1 >= bottom_threshold
                else:
                    in_margin = False

                # Mark positional header/footer
                if in_margin:
                    block['type'] = 'header_footer'
                    block['original_type'] = block.get('original_type', block.get('type', 'unknown'))

                # Track for recurrence check
                text_page_counts[text].add(page_no)

        # Check for recurring text (page numbers, running heads)
        total_pages = len(pages_data)
        recurrence_threshold_pages = total_pages * (self.header_footer_recurrence_threshold / 100.0)

        for page in pages_data:
            blocks = page.get('blocks', [])
            for block in blocks:
                text = block.get('text', '').strip()
                if text and len(text_page_counts[text]) >= recurrence_threshold_pages:
                    # Recurring text - mark as header_footer
                    if block.get('type') != 'header_footer':
                        block['type'] = 'header_footer'
                        block['original_type'] = block.get('original_type', block.get('type', 'unknown'))

    # ========================================================================
    # STEP C: Top-10 Fonts
    # ========================================================================

    def _compute_top_10_fonts(self, pages_data: List[Dict]) -> Set[float]:
        """
        Compute top-10 font sizes by character coverage
        (excluding header_footer blocks)

        Returns:
            Set of top-10 font sizes (rounded to 0.25pt)
        """
        size_coverage = Counter()

        for page in pages_data:
            blocks = page.get('blocks', [])
            for block in blocks:
                if block.get('type') == 'header_footer':
                    continue

                size_pt = block.get('font_size', 0)
                text = block.get('text', '')

                # Round to 0.25pt
                size_pt = round(size_pt * 4) / 4

                size_coverage[size_pt] += len(text)

        # Get top 10
        top_10 = [size for size, _ in size_coverage.most_common(10)]
        return set(top_10)

    # ========================================================================
    # STEP D: Body Size
    # ========================================================================

    def _determine_body_size(self, pages_data: List[Dict], top_10_fonts: Set[float]) -> float:
        """
        Determine body (paragraph) size = modal size by character-weighted frequency
        from top-10 fonts (excluding header_footer)
        """
        size_coverage = Counter()

        for page in pages_data:
            blocks = page.get('blocks', [])
            for block in blocks:
                if block.get('type') == 'header_footer':
                    continue

                size_pt = block.get('font_size', 0)
                size_pt = round(size_pt * 4) / 4

                if size_pt not in top_10_fonts:
                    continue

                text = block.get('text', '')
                size_coverage[size_pt] += len(text)

        if not size_coverage:
            return 10.0  # Default fallback

        # Most common size = body
        body_pt = size_coverage.most_common(1)[0][0]
        return body_pt

    # ========================================================================
    # STEP E: Title Selection
    # ========================================================================

    def _select_title_size(
        self, pages_data: List[Dict], top_10_fonts: Set[float], body_pt: float
    ) -> Optional[float]:
        """
        Select title size = largest size > body with at least one block ≥10 chars
        """
        candidate_sizes = []

        for page in pages_data:
            blocks = page.get('blocks', [])
            for block in blocks:
                if block.get('type') == 'header_footer':
                    continue

                size_pt = block.get('font_size', 0)
                size_pt = round(size_pt * 4) / 4

                if size_pt not in top_10_fonts:
                    continue

                if size_pt <= body_pt:
                    continue

                text = block.get('text', '').strip()
                if len(text) >= self.title_min_chars:
                    candidate_sizes.append(size_pt)

        if not candidate_sizes:
            return None

        # Largest qualifying size
        return max(candidate_sizes)

    # ========================================================================
    # STEP F: Quartile Thresholds
    # ========================================================================

    def _compute_quartile_thresholds(
        self, body_pt: float, title_pt: Optional[float]
    ) -> Dict:
        """
        Compute quartile ranges for H1-H4 based on relative position
        between body and title
        """
        if title_pt is None or title_pt <= body_pt:
            # No headings possible
            return {
                'h1': None,
                'h2': None,
                'h3': None,
                'h4': None
            }

        width = title_pt - body_pt

        # Quartile cutpoints (in relative units 0-1)
        # H1: (0.75, 1.0] - top 25%
        # H2: (0.50, 0.75]
        # H3: (0.25, 0.50]
        # H4: (0.00, 0.25] - bottom 25%

        return {
            'h1': {
                'r_min': 0.75,
                'r_max': 1.0,
                'size_min': body_pt + (width * 0.75),
                'size_max': title_pt
            },
            'h2': {
                'r_min': 0.50,
                'r_max': 0.75,
                'size_min': body_pt + (width * 0.50),
                'size_max': body_pt + (width * 0.75)
            },
            'h3': {
                'r_min': 0.25,
                'r_max': 0.50,
                'size_min': body_pt + (width * 0.25),
                'size_max': body_pt + (width * 0.50)
            },
            'h4': {
                'r_min': 0.00,
                'r_max': 0.25,
                'size_min': body_pt,
                'size_max': body_pt + (width * 0.25)
            }
        }

    # ========================================================================
    # STEP G: Block Classification
    # ========================================================================

    def _classify_blocks(
        self,
        pages_data: List[Dict],
        top_10_fonts: Set[float],
        body_pt: float,
        title_pt: Optional[float],
        quartile_thresholds: Dict
    ):
        """
        Classify each block based on font size and rules
        """
        for page in pages_data:
            blocks = page.get('blocks', [])

            for block in blocks:
                # Skip already-classified header_footer
                if block.get('type') == 'header_footer':
                    continue

                size_pt = block.get('font_size', 0)
                size_pt = round(size_pt * 4) / 4
                text = block.get('text', '').strip()

                # Check if in top-10
                if size_pt not in top_10_fonts:
                    # other_font: default to paragraph if close to body, else subtext
                    if abs(size_pt - body_pt) <= 0.5:
                        block['type'] = 'paragraph'
                    else:
                        block['type'] = 'subtext'
                    continue

                # Rule: headings/title >200 chars → body
                if len(text) > self.max_heading_chars:
                    block['type'] = 'paragraph'
                    continue

                # Title
                if title_pt and abs(size_pt - title_pt) < 0.01:
                    if len(text) >= self.title_min_chars:
                        block['type'] = 'title'
                        continue

                # Body (paragraph)
                if abs(size_pt - body_pt) <= 0.25:
                    block['type'] = 'paragraph'
                    continue

                # Subtext (smaller than body)
                if size_pt <= body_pt - 1.0:
                    block['type'] = 'subtext'
                    continue

                # Headings (quartile-based)
                if title_pt and size_pt > body_pt and size_pt < title_pt:
                    heading_level = self._assign_heading_level(size_pt, quartile_thresholds)
                    if heading_level:
                        block['type'] = heading_level
                        continue

                # Fallback: paragraph
                block['type'] = 'paragraph'

    def _assign_heading_level(self, size_pt: float, quartile_thresholds: Dict) -> Optional[str]:
        """Assign H1-H4 based on quartile ranges"""
        for level in ['h1', 'h2', 'h3', 'h4']:
            thresholds = quartile_thresholds.get(level)
            if not thresholds:
                continue

            size_min = thresholds['size_min']
            size_max = thresholds['size_max']

            # Exclusive upper bound for all except h1
            if level == 'h1':
                if size_min < size_pt <= size_max:
                    return 'heading1'
            else:
                if size_min < size_pt <= size_max:
                    return f'heading{level[1]}'

        return None

    # ========================================================================
    # STEP H: Sectioning
    # ========================================================================

    def _create_sections(self, pages_data: List[Dict]) -> List[Dict]:
        """
        Create sections based on title/heading stack rule:
        - Section = headers_stack + body_text
        - New section starts when title/H* appears after paragraph
        """
        sections = []
        current_section = None
        section_id = 0

        for page in pages_data:
            blocks = page.get('blocks', [])

            for block in blocks:
                block_type = block.get('type', '')

                if block_type == 'header_footer':
                    continue  # Ignore for sectioning

                is_header = block_type in ['title', 'heading1', 'heading2', 'heading3', 'heading4']
                is_body = block_type in ['paragraph', 'subtext']

                if is_header:
                    # Check if we need to start new section
                    if current_section and current_section.get('body_blocks'):
                        # Previous section had body - save it and start new
                        sections.append(current_section)
                        current_section = None

                    # Create section if needed
                    if current_section is None:
                        section_id += 1
                        current_section = {
                            'section_id': section_id,
                            'headers_stack': [],
                            'body_blocks': [],
                            'chunks': []
                        }

                    # Add to header stack
                    current_section['headers_stack'].append({
                        'block_id': block.get('block_id', f"b{id(block)}"),
                        'level': block_type,
                        'text': block.get('text', ''),
                        'page_number': page.get('page_number', 0)
                    })

                elif is_body:
                    # Create section if needed
                    if current_section is None:
                        section_id += 1
                        current_section = {
                            'section_id': section_id,
                            'headers_stack': [],
                            'body_blocks': [],
                            'chunks': []
                        }

                    # Add to body
                    current_section['body_blocks'].append({
                        'block_id': block.get('block_id', f"b{id(block)}"),
                        'type': block_type,
                        'text': block.get('text', ''),
                        'page_number': page.get('page_number', 0)
                    })

        # Save last section
        if current_section:
            sections.append(current_section)

        return sections

    # ========================================================================
    # STEP I: Chunking
    # ========================================================================

    def _chunk_sections(self, sections: List[Dict]):
        """
        Chunk each section's body text into ≤1000 char chunks
        """
        for section in sections:
            body_blocks = section.get('body_blocks', [])

            # Concatenate all body text
            full_text = ' '.join(block.get('text', '') for block in body_blocks)

            # Split into chunks
            chunks = self._split_into_chunks(
                full_text,
                section.get('section_id'),
                [b.get('block_id') for b in body_blocks]
            )

            section['chunks'] = chunks
            section['section_text'] = full_text

    def _split_into_chunks(
        self, text: str, section_id: int, source_blocks: List[str]
    ) -> List[Dict]:
        """Split text into chunks of ≤max_chunk_chars, breaking at whitespace"""
        chunks = []
        chunk_num = 0
        pos = 0

        while pos < len(text):
            chunk_num += 1
            end_pos = min(pos + self.max_chunk_chars, len(text))

            # Try to break at whitespace
            if end_pos < len(text):
                # Find last space before end_pos
                last_space = text.rfind(' ', pos, end_pos)
                if last_space > pos:
                    end_pos = last_space + 1

            chunk_text = text[pos:end_pos].strip()

            if chunk_text:
                chunks.append({
                    'chunk_id': f"s{section_id}-c{chunk_num}",
                    'char_start': pos,
                    'char_end': end_pos,
                    'text': chunk_text,
                    'source_blocks': source_blocks
                })

            pos = end_pos

        return chunks

    # ========================================================================
    # STEP J: Analysis/Diagnostics
    # ========================================================================

    def _build_analysis(
        self,
        top_10_fonts: Set[float],
        body_pt: float,
        title_pt: Optional[float],
        quartile_thresholds: Dict,
        pages_data: List[Dict],
        sections: List[Dict]
    ) -> Dict:
        """Build analysis metadata"""

        # Font coverage stats
        size_coverage = Counter()
        for page in pages_data:
            for block in page.get('blocks', []):
                if block.get('type') != 'header_footer':
                    size_pt = round(block.get('font_size', 0) * 4) / 4
                    size_coverage[size_pt] += len(block.get('text', ''))

        top_10_list = [
            {'size_pt': size, 'char_coverage': coverage}
            for size, coverage in size_coverage.most_common(10)
        ]

        # Block type counts
        block_counts = Counter()
        for page in pages_data:
            for block in page.get('blocks', []):
                block_counts[block.get('type', 'unknown')] += 1

        # Quartile info
        quartile_info = {}
        if title_pt and quartile_thresholds.get('h1'):
            quartile_info = {
                'heading_band_pt': {
                    'lower_pt': body_pt,
                    'upper_pt': title_pt,
                    'width_pt': title_pt - body_pt
                },
                'h1': {
                    'r_range': '(0.75,1.0]',
                    'size_range_pt': f"({quartile_thresholds['h1']['size_min']:.1f},{title_pt:.1f}]"
                },
                'h2': {
                    'r_range': '(0.5,0.75]',
                    'size_range_pt': f"({quartile_thresholds['h2']['size_min']:.1f},{quartile_thresholds['h2']['size_max']:.1f}]"
                },
                'h3': {
                    'r_range': '(0.25,0.5]',
                    'size_range_pt': f"({quartile_thresholds['h3']['size_min']:.1f},{quartile_thresholds['h3']['size_max']:.1f}]"
                },
                'h4': {
                    'r_range': '(0.0,0.25]',
                    'size_range_pt': f"({quartile_thresholds['h4']['size_min']:.1f},{quartile_thresholds['h4']['size_max']:.1f}]"
                },
                'subtext_max_pt': body_pt - 1.0
            }
        elif title_pt:
            quartile_info = {
                'body_pt': body_pt,
                'title_pt': title_pt,
                'subtext_max_pt': body_pt - 1.0
            }

        return {
            'classification_logic': 'relative_quartiles_between_title_and_body',
            'top_10_fonts_applied': True,
            'font_scope': {
                'top_10_font_sizes_by_coverage': top_10_list,
                'note': 'Top-10 computed from size-only coverage; non-top-10 blocks default to paragraph if |size−body|≤0.5 else subtext.'
            },
            'font_stats': {
                'body_pt': body_pt,
                'title_pt': title_pt,
                'relative_quartiles': quartile_info,
                'size_distribution': dict(size_coverage),
                'total_font_samples': sum(size_coverage.values())
            },
            'structure': {
                'font_thresholds': {
                    'body_pt': body_pt,
                    'title_pt': title_pt,
                    'relative_quartiles': {k: v['size_range_pt'] for k, v in quartile_info.items() if k.startswith('h') and isinstance(v, dict) and 'size_range_pt' in v} if quartile_info else {},
                    'notes': 'Headings assigned by relative quartiles between body and title; title blocks excluded from heading assignment.'
                },
                'block_counts': dict(block_counts),
                'section_count': len(sections),
                'chunk_count': sum(len(s.get('chunks', [])) for s in sections)
            }
        }

    # ========================================================================
    # Output Builder
    # ========================================================================

    def _build_output(
        self,
        pdf_extraction: Dict,
        pages_data: List[Dict],
        sections: List[Dict],
        analysis: Dict,
        top_10_fonts: Set[float]
    ) -> Dict:
        """Build final output matching the target schema"""

        # Get page height for bbox
        page_height = self._estimate_page_height(pages_data)

        # Build pages output
        output_pages = []
        for page in pages_data:
            page_no = page.get('page_number', 0)

            # Build blocks for this page
            page_blocks = []
            for block in page.get('blocks', []):
                # Assign block_id if missing
                if 'block_id' not in block:
                    block['block_id'] = f"p{page_no}-b{id(block)}"

                page_blocks.append({
                    'block_id': block['block_id'],
                    'type': block.get('type', 'paragraph'),
                    'text': block.get('text', ''),
                    'size_pt': round(block.get('font_size', 0), 1),
                    'font_weight': block.get('font_weight', 'Regular'),
                    'bbox': block.get('bbox', [0, 0, 0, 0]),
                    'align': block.get('align', 'left'),
                    'is_caps': block.get('is_caps', False)
                })

            # Get sections for this page
            page_sections = []
            for section in sections:
                # Check if any block in this section is on this page
                section_blocks = section.get('headers_stack', []) + section.get('body_blocks', [])
                if any(b.get('page_number') == page_no for b in section_blocks):
                    page_sections.append(section)

            output_pages.append({
                'page_no': page_no,
                'size': {'width_pt': 612, 'height_pt': page_height},
                'notes': {
                    'fonts': analysis['font_stats']['relative_quartiles'],
                    'header_footer_margin_pct': self.header_footer_margin_pct,
                    'top_10_font_sizes_by_coverage': analysis['font_scope']['top_10_font_sizes_by_coverage'],
                    'classification_logic': analysis['classification_logic']
                },
                'blocks': page_blocks,
                'sections': page_sections
            })

        # Update the pdf_extraction with new structure
        result = pdf_extraction.copy()

        # Update full_extraction
        if 'full_extraction' not in result:
            result['full_extraction'] = {}

        result['full_extraction'].update({
            'analysis': analysis
        })

        # Add document structure
        result['document'] = {
            'doc_id': result.get('doc_id', ''),
            'title': result.get('title', ''),
            'source': result.get('url', ''),
            'created_at': pdf_extraction.get('metadata', {}).get('creation_date', ''),
            'pages': output_pages
        }

        return result


# ============================================================================
# Main Processing Function
# ============================================================================

def classify_pdf_json(pdf_extraction: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Main entry point for JSON font classification

    Args:
        pdf_extraction: Raw output from pdf_extractor_unified_complete.py
        config: Optional configuration dict

    Returns:
        Classified document with new structure
    """
    classifier = FontClassifier(config)
    return classifier.process_document(pdf_extraction)
