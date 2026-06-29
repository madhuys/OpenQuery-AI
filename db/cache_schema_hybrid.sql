-- Hybrid PDF Download System Schema
-- Extends the existing cache system with domain preferences and browser pool support
-- This schema supports automatic learning of which domains need browser-based downloads

-- ============================================================================
-- Domain Download Preferences
-- ============================================================================
-- Tracks which download method works best for each domain
CREATE TABLE IF NOT EXISTS domain_download_preferences (
    pref_id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL,

    -- Preferred download method
    preferred_method TEXT NOT NULL DEFAULT 'auto'
        CHECK (preferred_method IN ('auto', 'requests', 'browser')),

    -- Reason for preference
    preference_reason TEXT,  -- 'timeout', 'bot_detection', 'manual_override', etc.

    -- Performance statistics
    requests_attempts INTEGER DEFAULT 0,
    requests_successes INTEGER DEFAULT 0,
    requests_total_duration_ms INTEGER DEFAULT 0,
    requests_avg_duration_ms INTEGER DEFAULT 0,

    browser_attempts INTEGER DEFAULT 0,
    browser_successes INTEGER DEFAULT 0,
    browser_total_duration_ms INTEGER DEFAULT 0,
    browser_avg_duration_ms INTEGER DEFAULT 0,

    -- Auto-switch tracking
    auto_switched_to_browser_at TIMESTAMP,  -- When domain was auto-switched
    auto_switch_trigger TEXT,  -- 'timeout_8s', '403_error', 'connection_reset', etc.

    -- Manual override tracking
    manually_set_to TEXT,  -- If user manually set preference
    manually_set_at TIMESTAMP,
    manually_set_by TEXT,  -- User identifier

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (domain_id) REFERENCES domains(domain_id) ON DELETE CASCADE,
    UNIQUE(domain_id)  -- One preference per domain
);

CREATE INDEX IF NOT EXISTS idx_domain_prefs_method ON domain_download_preferences(preferred_method);
CREATE INDEX IF NOT EXISTS idx_domain_prefs_auto_switch ON domain_download_preferences(auto_switched_to_browser_at);

-- ============================================================================
-- Application Settings
-- ============================================================================
-- Stores global application configuration for workers and browser pool
CREATE TABLE IF NOT EXISTS app_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    setting_type TEXT NOT NULL CHECK (setting_type IN ('int', 'float', 'bool', 'string', 'json')),
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings
INSERT OR IGNORE INTO app_settings (setting_key, setting_value, setting_type, description) VALUES
    ('pdf_worker_count', '10', 'int', 'Number of concurrent PDF download workers'),
    ('pdf_browser_pool_size', '5', 'int', 'Number of browser instances to keep in pool'),
    ('pdf_download_method', 'auto', 'string', 'Default download method: auto, requests, or browser'),
    ('pdf_timeout_threshold_ms', '8000', 'int', 'Timeout threshold for switching to browser (milliseconds)'),
    ('pdf_browser_pool_enabled', 'false', 'bool', 'Whether browser pool is currently active'),
    ('pdf_auto_learning_enabled', 'true', 'bool', 'Whether to auto-learn domain preferences'),
    ('pdf_max_file_size_mb', '60', 'int', 'Maximum PDF file size to download (MB)'),
    ('pdf_domain_concurrency', '4', 'int', 'Maximum concurrent downloads per domain');

-- ============================================================================
-- Extend pdf_downloads table
-- ============================================================================
-- Add columns for tracking download method and performance
-- These are ALTER TABLE statements that will be executed safely (IF NOT EXISTS logic in code)

-- Note: SQLite doesn't support IF NOT EXISTS for columns, so cache_service.py will handle this
-- The following columns need to be added to pdf_downloads:
--
-- download_method_used TEXT CHECK (download_method_used IN ('requests', 'browser'))
-- download_duration_ms INTEGER
-- switched_from_method TEXT  -- If this download switched methods (e.g., 'requests' → 'browser')
-- download_started_at TIMESTAMP
-- browser_session_id TEXT  -- Which browser instance was used (if browser method)

-- ============================================================================
-- Views for Monitoring
-- ============================================================================

-- View: Domain download performance comparison
CREATE VIEW IF NOT EXISTS v_domain_download_performance AS
SELECT
    d.registrable_domain,
    d.domain_id,
    dp.preferred_method,
    dp.preference_reason,

    -- Requests stats
    dp.requests_attempts,
    dp.requests_successes,
    CASE
        WHEN dp.requests_attempts > 0
        THEN ROUND(100.0 * dp.requests_successes / dp.requests_attempts, 2)
        ELSE 0
    END as requests_success_rate,
    dp.requests_avg_duration_ms,

    -- Browser stats
    dp.browser_attempts,
    dp.browser_successes,
    CASE
        WHEN dp.browser_attempts > 0
        THEN ROUND(100.0 * dp.browser_successes / dp.browser_attempts, 2)
        ELSE 0
    END as browser_success_rate,
    dp.browser_avg_duration_ms,

    -- Auto-switch info
    dp.auto_switched_to_browser_at,
    dp.auto_switch_trigger,

    -- Manual override info
    dp.manually_set_to,
    dp.manually_set_at,

    dp.updated_at as last_updated
FROM domains d
LEFT JOIN domain_download_preferences dp ON d.domain_id = dp.domain_id
WHERE dp.pref_id IS NOT NULL;

-- View: Recent PDF downloads with method tracking
CREATE VIEW IF NOT EXISTS v_pdf_downloads_with_method AS
SELECT
    u.normalized_url,
    d.registrable_domain,
    p.download_state,
    p.processing_state,
    p.download_method_used,
    p.download_duration_ms,
    p.switched_from_method,
    p.download_started_at,
    p.downloaded_at,
    p.pdf_size_bytes / 1024.0 / 1024.0 as size_mb,
    p.num_pages,
    p.download_retry_count,
    p.download_error
FROM pdf_downloads p
INNER JOIN urls u ON p.url_id = u.url_id
INNER JOIN domains d ON u.domain_id = d.domain_id;

-- View: Browser pool usage statistics
CREATE VIEW IF NOT EXISTS v_browser_pool_stats AS
SELECT
    COUNT(DISTINCT browser_session_id) as active_sessions,
    COUNT(*) as total_browser_downloads,
    SUM(CASE WHEN download_state = 'download_success' THEN 1 ELSE 0 END) as successful_downloads,
    ROUND(AVG(download_duration_ms), 2) as avg_duration_ms,
    MIN(download_started_at) as first_browser_download,
    MAX(downloaded_at) as last_browser_download
FROM pdf_downloads
WHERE download_method_used = 'browser';

-- View: Auto-switch analysis
CREATE VIEW IF NOT EXISTS v_auto_switch_analysis AS
SELECT
    d.registrable_domain,
    dp.auto_switch_trigger,
    dp.auto_switched_to_browser_at,
    COUNT(p.pdf_id) as pdfs_downloaded_after_switch,
    SUM(CASE WHEN p.download_state = 'download_success' THEN 1 ELSE 0 END) as successful_downloads,
    ROUND(AVG(p.download_duration_ms), 2) as avg_duration_ms
FROM domain_download_preferences dp
INNER JOIN domains d ON dp.domain_id = d.domain_id
LEFT JOIN urls u ON u.domain_id = d.domain_id
LEFT JOIN pdf_downloads p ON p.url_id = u.url_id
    AND p.downloaded_at > dp.auto_switched_to_browser_at
WHERE dp.auto_switched_to_browser_at IS NOT NULL
GROUP BY d.domain_id, d.registrable_domain, dp.auto_switch_trigger, dp.auto_switched_to_browser_at;

-- Update schema version
INSERT OR IGNORE INTO schema_version (version, description) VALUES
    (3, 'Added hybrid download system with domain preferences and browser pool support');
