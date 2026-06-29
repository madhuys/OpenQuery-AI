-- ============================================================================
-- Embedding Cache Schema for Azure OpenAI Embeddings
-- ============================================================================
-- Purpose: Store document chunk embeddings for semantic search
-- Tables: document_embeddings, embedding_status
-- ============================================================================

-- ============================================================================
-- 1. document_embeddings: Store embeddings for each chunk
-- ============================================================================
CREATE TABLE IF NOT EXISTS document_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,                  -- Source document URL
    doc_type TEXT NOT NULL,             -- 'html' or 'pdf'
    doc_id TEXT,                        -- Document fingerprint/hash
    chunk_id INTEGER NOT NULL,          -- Chunk index within document
    chunk_text TEXT NOT NULL,           -- Actual chunk text
    embedding BLOB NOT NULL,            -- Serialized numpy array (JSON array of floats)
    embedding_model TEXT NOT NULL,      -- Model used: text-embedding-3-small
    word_count INTEGER,                 -- Number of words in chunk
    char_count INTEGER,                 -- Number of characters in chunk
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(url, chunk_id)               -- One embedding per URL+chunk
);

-- Indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_embeddings_url ON document_embeddings(url);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc_id ON document_embeddings(doc_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc_type ON document_embeddings(doc_type);
CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON document_embeddings(created_at);

-- ============================================================================
-- 2. embedding_status: Track embedding processing status per document
-- ============================================================================
CREATE TABLE IF NOT EXISTS embedding_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,           -- Document URL
    doc_type TEXT NOT NULL,             -- 'html' or 'pdf'
    status TEXT NOT NULL,               -- 'pending', 'processing', 'completed', 'failed'
    total_chunks INTEGER,               -- Total chunks in document
    processed_chunks INTEGER DEFAULT 0, -- Chunks successfully embedded
    error_message TEXT,                 -- Error message if failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for status tracking
CREATE INDEX IF NOT EXISTS idx_embedding_status_url ON embedding_status(url);
CREATE INDEX IF NOT EXISTS idx_embedding_status_status ON embedding_status(status);
CREATE INDEX IF NOT EXISTS idx_embedding_status_doc_type ON embedding_status(doc_type);

-- ============================================================================
-- Notes:
-- ============================================================================
-- - embedding column stores JSON array: [0.123, -0.456, 0.789, ...]
-- - text-embedding-3-small produces 1536-dimension vectors
-- - Cosine similarity calculated in Python (not SQL) for performance
-- - status values:
--   * 'pending': Queued for embedding
--   * 'processing': Currently being embedded
--   * 'completed': All chunks embedded successfully
--   * 'failed': Embedding failed (can be retried)
-- ============================================================================
