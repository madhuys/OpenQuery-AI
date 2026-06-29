-- Serper Search Cache Database Schema
-- SQLite version with all required tables, indexes, and constraints

-- ==============================================================================
-- DOMAINS TABLE - Track domain-level metadata
-- ==============================================================================
CREATE TABLE IF NOT EXISTS domains (
    domain_id INTEGER PRIMARY KEY AUTOINCREMENT,
    registrable_domain TEXT UNIQUE NOT NULL,
    robots_cache_json TEXT,  -- JSON stored as TEXT in SQLite
    sitemap_index_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (json_valid(robots_cache_json) OR robots_cache_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_domains_registrable ON domains(registrable_domain);

-- ==============================================================================
-- URLS TABLE - Canonical URL tracking with staleness management
-- ==============================================================================
CREATE TABLE IF NOT EXISTS urls (
    url_id INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_url TEXT UNIQUE NOT NULL,
    domain_id INTEGER NOT NULL,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    first_published_at_detected TIMESTAMP,
    last_updated_at_detected TIMESTAMP,
    sitemap_lastmod TIMESTAMP,
    cache_state TEXT DEFAULT 'fresh' CHECK (cache_state IN ('fresh', 'stale', 'revalidate')),
    revalidate_after TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (domain_id) REFERENCES domains(domain_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_urls_normalized ON urls(normalized_url);
CREATE INDEX IF NOT EXISTS idx_urls_domain_lastseen ON urls(domain_id, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_urls_cache_state ON urls(cache_state, revalidate_after);

-- ==============================================================================
-- SEARCHES TABLE - Search query tracking with complete analysis results
-- ==============================================================================
CREATE TABLE IF NOT EXISTS searches (
    query_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    settings_json TEXT NOT NULL,  -- Full search settings (engine, region, freshness, etc.)
    analysis_results_json TEXT,   -- Complete analyzed results (stored after processing)
    analysis_completed_at TIMESTAMP,  -- When analysis finished
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (json_valid(settings_json)),
    CHECK (json_valid(analysis_results_json) OR analysis_results_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_searches_created ON searches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_searches_query_text ON searches(query_text);

-- ==============================================================================
-- QUERY_RESULTS TABLE - Links searches to URLs with SERP metadata
-- ==============================================================================
CREATE TABLE IF NOT EXISTS query_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    url_id INTEGER NOT NULL,
    engine TEXT NOT NULL,  -- 'google', 'serper', 'brave'
    serp_position INTEGER,
    title_at_fetch TEXT,
    snippet_at_fetch TEXT,
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (query_id) REFERENCES searches(query_id) ON DELETE CASCADE,
    FOREIGN KEY (url_id) REFERENCES urls(url_id) ON DELETE CASCADE,

    UNIQUE(query_id, url_id)
);

CREATE INDEX IF NOT EXISTS idx_query_results_query ON query_results(query_id, serp_position);
CREATE INDEX IF NOT EXISTS idx_query_results_url ON query_results(url_id, found_at DESC);

-- ==============================================================================
-- URL_RAW TABLE - Raw fetch history with content hashing
-- ==============================================================================
CREATE TABLE IF NOT EXISTS url_raw (
    raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id INTEGER NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    http_status INTEGER NOT NULL,
    final_url TEXT NOT NULL,  -- After redirects
    etag TEXT,
    last_modified_header TEXT,
    content_hash TEXT NOT NULL,  -- SHA-256 of normalized HTML
    raw_html TEXT,  -- Store full HTML (or use external blob storage)
    fetch_meta_json TEXT,  -- Headers, redirect chain, timing

    FOREIGN KEY (url_id) REFERENCES urls(url_id) ON DELETE CASCADE,

    CHECK (json_valid(fetch_meta_json) OR fetch_meta_json IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_url_raw_url_fetched ON url_raw(url_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_url_raw_content_hash ON url_raw(url_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_url_raw_hash_lookup ON url_raw(content_hash);

-- ==============================================================================
-- URL_PROCESSED TABLE - Processed analysis results with versioning
-- ==============================================================================
CREATE TABLE IF NOT EXISTS url_processed (
    proc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id INTEGER NOT NULL,
    raw_id INTEGER NOT NULL,
    pipeline_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    content_text TEXT,
    analysis_summary TEXT,
    entities_json TEXT,  -- Extracted entities, facets
    quality_scores_json TEXT,  -- Readability, boilerplate %, etc.
    published_at TIMESTAMP,
    updated_at TIMESTAMP,
    published_source TEXT CHECK (published_source IN ('jsonld', 'og', 'byline', 'http_last_modified', 'sitemap', 'feed', 'none', NULL)),
    updated_source TEXT CHECK (updated_source IN ('jsonld', 'og', 'byline', 'http_last_modified', 'sitemap', 'feed', 'none', NULL)),
    processing_status TEXT DEFAULT 'success' CHECK (processing_status IN ('success', 'filtered', 'failed', NULL)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (url_id) REFERENCES urls(url_id) ON DELETE CASCADE,
    FOREIGN KEY (raw_id) REFERENCES url_raw(raw_id) ON DELETE CASCADE,

    CHECK (json_valid(entities_json) OR entities_json IS NULL),
    CHECK (json_valid(quality_scores_json) OR quality_scores_json IS NULL),

    UNIQUE(url_id, raw_id, pipeline_version, model_name, model_version, schema_version)
);

CREATE INDEX IF NOT EXISTS idx_url_processed_url ON url_processed(url_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_url_processed_raw ON url_processed(raw_id);
CREATE INDEX IF NOT EXISTS idx_url_processed_versions ON url_processed(pipeline_version, model_name, model_version, schema_version);

-- ==============================================================================
-- TRACKING PARAMS - Known tracking parameters to strip during normalization
-- ==============================================================================
CREATE TABLE IF NOT EXISTS tracking_params (
    param_name TEXT PRIMARY KEY,
    description TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed common tracking params
INSERT OR IGNORE INTO tracking_params (param_name, description) VALUES
    ('utm_source', 'Google Analytics campaign source'),
    ('utm_medium', 'Google Analytics campaign medium'),
    ('utm_campaign', 'Google Analytics campaign name'),
    ('utm_term', 'Google Analytics campaign term'),
    ('utm_content', 'Google Analytics campaign content'),
    ('gclid', 'Google Click ID'),
    ('fbclid', 'Facebook Click ID'),
    ('msclkid', 'Microsoft Click ID'),
    ('mc_cid', 'Mailchimp Campaign ID'),
    ('mc_eid', 'Mailchimp Email ID'),
    ('_ga', 'Google Analytics client ID'),
    ('ref', 'Generic referrer'),
    ('source', 'Generic source'),
    ('campaign', 'Generic campaign');

-- ==============================================================================
-- DATABASE VERSION - Schema migration tracking
-- ==============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    (1, 'Initial schema with domains, urls, searches, query_results, url_raw, url_processed');

-- ==============================================================================
-- VIEWS - Convenience views for common queries
-- ==============================================================================

-- View: Recent searches with result counts
CREATE VIEW IF NOT EXISTS v_recent_searches AS
SELECT
    s.query_id,
    s.query_text,
    s.created_at,
    json_extract(s.settings_json, '$.search_type') as search_type,
    json_extract(s.settings_json, '$.num_results') as num_results,
    COUNT(qr.result_id) as actual_results
FROM searches s
LEFT JOIN query_results qr ON s.query_id = qr.query_id
GROUP BY s.query_id
ORDER BY s.created_at DESC;

-- View: URL cache statistics
CREATE VIEW IF NOT EXISTS v_url_cache_stats AS
SELECT
    u.url_id,
    u.normalized_url,
    d.registrable_domain,
    u.cache_state,
    u.first_seen_at,
    u.last_seen_at,
    COUNT(DISTINCT ur.raw_id) as fetch_count,
    COUNT(DISTINCT up.proc_id) as process_count,
    MAX(ur.fetched_at) as last_fetched,
    MAX(up.created_at) as last_processed
FROM urls u
INNER JOIN domains d ON u.domain_id = d.domain_id
LEFT JOIN url_raw ur ON u.url_id = ur.url_id
LEFT JOIN url_processed up ON u.url_id = up.url_id
GROUP BY u.url_id;

-- View: Latest processed version per URL
CREATE VIEW IF NOT EXISTS v_latest_processed AS
SELECT
    up.*,
    u.normalized_url,
    ur.content_hash,
    ur.fetched_at
FROM url_processed up
INNER JOIN urls u ON up.url_id = u.url_id
INNER JOIN url_raw ur ON up.raw_id = ur.raw_id
WHERE up.proc_id = (
    SELECT proc_id
    FROM url_processed
    WHERE url_id = up.url_id
    ORDER BY created_at DESC
    LIMIT 1
);
