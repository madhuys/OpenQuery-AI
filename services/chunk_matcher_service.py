"""
Chunk Matcher Service
Finds exact matches between semantic search result chunks and source documents
"""
import re
from typing import Optional, Dict, List
import json
import sqlite3
from pathlib import Path


class ChunkMatcherService:
    """
    Service to match search result chunks to their exact location in source documents
    """

    def __init__(self, db_path: str = "db/serper_cache.db"):
        """Initialize with database path"""
        self.db_path = db_path

    def normalize_text(self, text: str) -> str:
        """
        Normalize text for matching by removing extra whitespace, line breaks, etc.

        Args:
            text: Raw text to normalize

        Returns:
            Normalized text with single spaces
        """
        # Replace all whitespace (spaces, tabs, newlines) with single space
        normalized = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        normalized = normalized.strip()
        return normalized

    def load_document(self, url: str, doc_type: str) -> Optional[Dict]:
        """
        Load processed document from database or JSON files

        Args:
            url: Document URL
            doc_type: 'html' or 'pdf'

        Returns:
            Document data dict with content and chunks or None if not found
        """
        # For PDFs, load from JSON files (they're not in the database)
        if doc_type == 'pdf':
            return self._load_pdf_from_json(url)

        # For HTML, load from database
        try:
            # Connect to database
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query the most recent processed version for this URL
            cursor.execute("""
                SELECT
                    p.content_text,
                    p.analysis_summary as title,
                    p.entities_json,
                    p.quality_scores_json,
                    p.published_at,
                    p.updated_at,
                    p.processing_status,
                    u.normalized_url
                FROM url_processed p
                JOIN urls u ON p.url_id = u.url_id
                WHERE u.normalized_url = ?
                ORDER BY p.created_at DESC
                LIMIT 1
            """, (url,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # Parse JSON fields
            entities_data = json.loads(row['entities_json']) if row['entities_json'] else {}
            quality_scores = json.loads(row['quality_scores_json']) if row['quality_scores_json'] else {}

            # Extract chunks from entities_json (if stored there) or content_text
            chunks = entities_data.get('chunks', [])

            # If no structured chunks, create from content_text
            if not chunks and row['content_text']:
                # Simple chunking: split by paragraphs
                content = row['content_text']
                paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                chunks = [{'text': p} for p in paragraphs]

            # Build document structure
            return {
                'url': url,
                'title': row['title'] or '',
                'content': chunks,  # List of chunks
                'full_text': row['content_text'] or '',
                'word_count': quality_scores.get('word_count', 0),
                'published_date': row['published_at'],
                'author': entities_data.get('author'),
                'status': row['processing_status']
            }

        except Exception as e:
            print(f"Error loading document from DB: {e}")
            return None

    def _load_pdf_from_json(self, url: str) -> Optional[Dict]:
        """
        Load PDF document from JSON file

        Args:
            url: PDF URL

        Returns:
            Document data dict with content and chunks or None if not found
        """
        import hashlib
        import os

        try:
            # Generate hash for this URL (same as PDF processing service)
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:16]

            # Check in outputs/pdf_json directory
            json_dir = Path('outputs/pdf_json')
            if not json_dir.exists():
                return None

            # Find matching JSON file
            for json_file in json_dir.glob(f'{url_hash}_*.json'):
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Extract chunks from full_extraction.content (Section → Chunk → Blocks structure)
                chunks = []
                full_text_parts = []

                if 'full_extraction' in data and 'content' in data['full_extraction']:
                    sections = data['full_extraction']['content']

                    for section in sections:
                        if section.get('chunks'):
                            for chunk in section['chunks']:
                                # Extract text from blocks within chunk
                                chunk_text = ''
                                if chunk.get('blocks'):
                                    chunk_text = ' '.join(block.get('text', '') for block in chunk['blocks'])

                                if chunk_text.strip():
                                    chunks.append({
                                        'text': chunk_text.strip(),
                                        'chunk_id': chunk.get('chunk_id', ''),
                                        'char_count': chunk.get('char_count', len(chunk_text)),
                                        'merged_from': chunk.get('merged_from', [])
                                    })
                                    full_text_parts.append(chunk_text.strip())

                # Build full text from chunks
                full_text = '\n\n'.join(full_text_parts) if full_text_parts else data.get('full_text', '')

                # Get metadata
                metadata = data.get('metadata', {}) if 'full_extraction' in data else {}

                return {
                    'url': url,
                    'title': data.get('title', metadata.get('title', '')),
                    'content': chunks,  # List of chunk dicts with text
                    'full_text': full_text,
                    'word_count': data.get('word_count', 0),
                    'published_date': metadata.get('creation_date'),
                    'author': metadata.get('author'),
                    'status': data.get('status', 'success')
                }

            return None

        except Exception as e:
            print(f"Error loading PDF from JSON: {e}")
            import traceback
            traceback.print_exc()
            return None

    def find_chunk_in_document(self, chunk_text: str, document_data: Dict) -> Optional[Dict]:
        """
        Find exact match of chunk in document content

        Args:
            chunk_text: The chunk text to find
            document_data: Processed document data

        Returns:
            Match info dict with:
            - chunk_index: Index of matching chunk
            - section_index: Index of matching section (if applicable)
            - start_char: Character position where match starts in full text
            - end_char: Character position where match ends in full text
            - context_before: Text before the match
            - context_after: Text after the match
            - full_text: Complete document text with match highlighted
        """
        # Use full_text from document if available, otherwise build from chunks
        full_text = document_data.get('full_text', '')
        content = document_data.get('content', [])

        # Build chunk positions tracking
        chunk_positions = []
        current_pos = 0

        # If we have full_text, use it directly and map chunks to positions
        if full_text and isinstance(content, list):
            # Track each chunk's position in the full text
            for chunk_idx, chunk in enumerate(content):
                if isinstance(chunk, dict):
                    chunk_original_text = chunk.get('text', '')
                elif isinstance(chunk, str):
                    chunk_original_text = chunk
                else:
                    continue

                # Find this chunk in the full text
                normalized_chunk = self.normalize_text(chunk_original_text)
                normalized_full = self.normalize_text(full_text)

                # Try to find the chunk in full text
                start_idx = normalized_full.find(normalized_chunk, current_pos)

                if start_idx != -1:
                    # Found it - estimate original position
                    # This is approximate since we normalized
                    start_pos = start_idx
                    end_pos = start_idx + len(chunk_original_text)

                    chunk_positions.append({
                        'chunk_idx': chunk_idx,
                        'section_idx': 0,
                        'start_pos': start_pos,
                        'end_pos': end_pos,
                        'original_text': chunk_original_text
                    })

                    current_pos = start_idx + len(normalized_chunk)

        # If no full_text, build it from chunks
        elif isinstance(content, list):
            full_text_parts = []
            current_pos = 0

            for chunk_idx, chunk in enumerate(content):
                if isinstance(chunk, dict):
                    chunk_original_text = chunk.get('text', '')
                elif isinstance(chunk, str):
                    chunk_original_text = chunk
                else:
                    continue

                start_pos = current_pos
                full_text_parts.append(chunk_original_text)
                current_pos += len(chunk_original_text)
                end_pos = current_pos

                chunk_positions.append({
                    'chunk_idx': chunk_idx,
                    'section_idx': 0,
                    'start_pos': start_pos,
                    'end_pos': end_pos,
                    'original_text': chunk_original_text
                })

                # Add space between chunks
                full_text_parts.append('\n\n')
                current_pos += 2

            full_text = ''.join(full_text_parts)

        # Normalize both texts for matching
        normalized_full_text = self.normalize_text(full_text)
        normalized_chunk = self.normalize_text(chunk_text)

        # Find match in normalized text
        match_start_normalized = normalized_full_text.find(normalized_chunk)

        if match_start_normalized == -1:
            # Try fuzzy matching - find the chunk position that has the highest overlap
            best_match = None
            best_overlap = 0

            for pos_info in chunk_positions:
                normalized_original = self.normalize_text(pos_info['original_text'])

                # Check if this chunk contains the search text
                if normalized_chunk in normalized_original or normalized_original in normalized_chunk:
                    overlap = len(set(normalized_chunk.split()) & set(normalized_original.split()))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_match = pos_info

            if best_match:
                # Use the best matching chunk
                return {
                    'chunk_index': best_match['chunk_idx'],
                    'section_index': best_match['section_idx'],
                    'start_char': best_match['start_pos'],
                    'end_char': best_match['end_pos'],
                    'context_before': full_text[max(0, best_match['start_pos'] - 200):best_match['start_pos']],
                    'context_after': full_text[best_match['end_pos']:min(len(full_text), best_match['end_pos'] + 200)],
                    'matched_text': full_text[best_match['start_pos']:best_match['end_pos']],
                    'full_text': full_text,
                    'match_type': 'fuzzy'
                }

            return None  # No match found

        # Map normalized position back to original text position
        # We need to account for whitespace that was removed during normalization
        match_end_normalized = match_start_normalized + len(normalized_chunk)

        # Build a mapping from normalized positions to original positions
        orig_pos = 0
        norm_pos = 0
        norm_to_orig_map = {}

        for i, char in enumerate(full_text):
            if not char.isspace() or (char == ' ' and (i == 0 or not full_text[i-1].isspace())):
                # This character appears in normalized text
                norm_to_orig_map[norm_pos] = i
                if char.isspace():
                    norm_pos += 1  # Single space in normalized
                else:
                    norm_pos += 1

        # Handle end-of-string mapping
        norm_to_orig_map[norm_pos] = len(full_text)

        # Find original start position
        # Scan backwards from mapped position to find exact match start
        approx_start = norm_to_orig_map.get(match_start_normalized, 0)

        # Search for the actual match in original text around this position
        # Look in a window around the approximate position
        search_window_start = max(0, approx_start - 100)
        search_window_end = min(len(full_text), approx_start + len(chunk_text) + 100)
        search_window = full_text[search_window_start:search_window_end]

        # Try to find exact match with normalized comparison
        best_match_pos = None
        best_match_len = 0

        for i in range(len(search_window)):
            # Try matching from this position
            test_end = min(i + len(chunk_text) + 200, len(search_window))
            test_text = search_window[i:test_end]

            if self.normalize_text(test_text).startswith(normalized_chunk):
                # Found a potential match, find exact end
                for end_offset in range(len(chunk_text), len(test_text) + 1):
                    if self.normalize_text(search_window[i:i+end_offset]) == normalized_chunk:
                        match_len = end_offset
                        if match_len > best_match_len:
                            best_match_pos = search_window_start + i
                            best_match_len = match_len
                        break

        if best_match_pos is not None:
            start_char = best_match_pos
            end_char = best_match_pos + best_match_len

            return {
                'chunk_index': 0,
                'section_index': 0,
                'start_char': start_char,
                'end_char': end_char,
                'context_before': full_text[max(0, start_char - 200):start_char],
                'context_after': full_text[end_char:min(len(full_text), end_char + 200)],
                'matched_text': full_text[start_char:end_char],
                'full_text': full_text,
                'match_type': 'exact'
            }

        return None

    def match_chunk_to_source(self, url: str, chunk_text: str, doc_type: str = 'html') -> Optional[Dict]:
        """
        Main method to match a chunk to its source document

        Args:
            url: Document URL
            chunk_text: Chunk text to match
            doc_type: Document type ('html' or 'pdf')

        Returns:
            Match result dict or None if not found
        """
        # Load document
        document_data = self.load_document(url, doc_type)

        if not document_data:
            return {
                'error': 'Document not found in cache',
                'url': url,
                'doc_type': doc_type
            }

        # Find match
        match_info = self.find_chunk_in_document(chunk_text, document_data)

        if match_info:
            match_info.update({
                'url': url,
                'doc_type': doc_type,
                'document_title': document_data.get('title', ''),
                'document_metadata': {
                    'word_count': document_data.get('word_count', 0),
                    'published_date': document_data.get('published_date'),
                    'author': document_data.get('author')
                }
            })

        return match_info
