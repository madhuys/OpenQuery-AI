"""
PDF Deduplication Service

This file contains PDFDeduplicator for detecting duplicate PDFs based on metadata fingerprints.

Note: Complete PDF processing pipeline is in pdf_processing_service.py
"""

import hashlib
from typing import Dict, Optional

from services.cache_service import CacheService


class PDFDeduplicator:
    """
    Deduplication system using metadata comparison

    Strategy:
    1. Generate fingerprint from (title, author, creation_date)
    2. Check against database of processed PDFs
    3. If match found, return cached result without processing
    """

    def __init__(self):
        self.cache = CacheService()

    def is_duplicate(self, metadata: Dict) -> tuple[bool, Optional[str]]:
        """
        Check if PDF is duplicate based on metadata

        Args:
            metadata: Metadata dict from PDF extractor

        Returns:
            (is_duplicate: bool, fingerprint: str)

        Fingerprint generation:
        - Normalize title (lowercase, strip whitespace)
        - Normalize author
        - Use creation_date or modification_date
        - Hash: sha256(title + author + date)
        """
        # Generate fingerprint
        fingerprint = self._generate_fingerprint(metadata)

        # Check cache
        is_dup = self.cache.check_pdf_fingerprint_exists(fingerprint)

        return is_dup, fingerprint

    def _generate_fingerprint(self, metadata: Dict) -> str:
        """
        Generate deterministic fingerprint from metadata

        Components:
        - title (normalized)
        - author (normalized)
        - creation_date or modification_date
        - file_size_mb (to differentiate files with missing metadata)

        Returns SHA256 hash
        """
        title = (metadata.get('title') or '').lower().strip()
        author = (metadata.get('author') or '').lower().strip()
        creation_date = metadata.get('creation_date') or metadata.get('modification_date') or ''
        file_size = str(metadata.get('file_size_mb', 0))

        # Filter out placeholder values
        if title in ['none', 'null', '']:
            title = ''
        if author in ['none', 'null', '']:
            author = ''

        # Build fingerprint string
        # Include file size to differentiate PDFs with missing metadata
        fingerprint_str = f"{title}|{author}|{creation_date}|{file_size}"

        # Hash
        fingerprint = hashlib.sha256(fingerprint_str.encode('utf-8')).hexdigest()

        return fingerprint

    def record_processed(self, fingerprint: str, doc_id: str, metadata: Dict):
        """
        Record processed PDF in deduplication database

        Args:
            fingerprint: Metadata fingerprint
            doc_id: Document ID from PDF extractor
            metadata: Full metadata dict
        """
        self.cache.record_pdf_fingerprint(fingerprint, doc_id, metadata)


# PDFProcessor and process_pdf_parallel have been DEPRECATED
# Use pdf_processing_service.py instead for complete PDF processing pipeline
