-- PDF Download Tracking Table
-- Tracks PDF download attempts, success/failure states, and processing results
-- This extends the existing cache schema with PDF-specific tracking

CREATE TABLE IF NOT EXISTS pdf_downloads (
    pdf_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id INTEGER NOT NULL,

    -- Download state tracking
    download_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_state IN ('pending', 'downloading', 'download_success', 'download_failed')),
    download_attempted_at TIMESTAMP,
    downloaded_at TIMESTAMP,
    last_fetched TIMESTAMP,  -- Added: last time this PDF was fetched
    download_error TEXT,
    pdf_size_bytes INTEGER,
    pdf_hash TEXT,  -- SHA-256 of PDF content
    download_method TEXT CHECK (download_method IN ('requests', 'playwright', 'manual')),  -- Added
    filepath TEXT,  -- Added: local storage path

    -- Processing state tracking
    processing_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (processing_state IN ('pending', 'processing', 'processed_success', 'processing_failed')),
    processing_attempted_at TIMESTAMP,
    processed_at TIMESTAMP,
    processing_error TEXT,
    extraction_method TEXT,  -- 'pypdfium2', 'pdfplumber', etc.
    extracted INTEGER DEFAULT 0 CHECK (extracted IN (0, 1)),  -- Added: extraction flag
    processed INTEGER DEFAULT 0 CHECK (processed IN (0, 1)),  -- Added: processing flag

    -- Content metadata (after successful processing)
    num_pages INTEGER,
    num_words INTEGER,
    text_preview TEXT,  -- First 1000 chars

    -- Freshness tracking
    freshness_state TEXT NOT NULL DEFAULT 'fresh'
        CHECK (freshness_state IN ('fresh', 'stale', 'expired')),
    revalidate_after TIMESTAMP,

    -- Retry tracking
    download_retry_count INTEGER DEFAULT 0,
    processing_retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (url_id) REFERENCES urls(url_id) ON DELETE CASCADE
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_pdf_downloads_url ON pdf_downloads(url_id);
CREATE INDEX IF NOT EXISTS idx_pdf_downloads_state ON pdf_downloads(download_state, processing_state);
CREATE INDEX IF NOT EXISTS idx_pdf_downloads_freshness ON pdf_downloads(freshness_state, revalidate_after);
CREATE INDEX IF NOT EXISTS idx_pdf_downloads_hash ON pdf_downloads(pdf_hash);

-- View: PDF download statistics
CREATE VIEW IF NOT EXISTS v_pdf_stats AS
SELECT
    u.normalized_url,
    d.registrable_domain,
    p.download_state,
    p.processing_state,
    p.freshness_state,
    p.pdf_size_bytes / 1024.0 / 1024.0 as size_mb,
    p.num_pages,
    p.num_words,
    p.downloaded_at,
    p.processed_at,
    p.download_retry_count,
    p.processing_retry_count,
    p.download_error,
    p.processing_error
FROM pdf_downloads p
INNER JOIN urls u ON p.url_id = u.url_id
INNER JOIN domains d ON u.domain_id = d.domain_id;

-- Update schema version
INSERT OR IGNORE INTO schema_version (version, description) VALUES
    (2, 'Added pdf_downloads table for PDF-specific tracking');
