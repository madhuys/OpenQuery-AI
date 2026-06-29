-- Migration: Add PDF Fingerprints table for deduplication
-- Created: 2025-01-04
-- Purpose: Track processed PDFs by metadata fingerprint to avoid reprocessing duplicates

CREATE TABLE IF NOT EXISTS pdf_fingerprints (
    pdf_fingerprint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,  -- SHA-256 of (title + author + date)
    doc_id TEXT NOT NULL,               -- Document ID from PDFLiteExtractor (sha256:...)
    title TEXT,                         -- PDF title from metadata
    author TEXT,                        -- PDF author from metadata
    creation_date TEXT,                 -- ISO 8601 date
    modification_date TEXT,             -- ISO 8601 date
    num_pages INTEGER,                  -- Number of pages
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP  -- When first processed
);

-- Index for fast lookup
CREATE INDEX IF NOT EXISTS idx_pdf_fingerprints_fingerprint
    ON pdf_fingerprints(fingerprint);

-- Index for doc_id lookup
CREATE INDEX IF NOT EXISTS idx_pdf_fingerprints_doc_id
    ON pdf_fingerprints(doc_id);
