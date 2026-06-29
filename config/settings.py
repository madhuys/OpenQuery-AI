"""
Settings Configuration for OpenQuery AI
Centralized settings management with defaults for all parameters
"""
import json
import os
from typing import Dict, Optional, Literal
from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class SearchSettings:
    """Search type and query settings"""
    search_type: Literal["search", "news", "videos", "scholar"] = "search"
    default_query: str = "latest AI developments"
    default_provider: Literal["serper", "ddg"] = "serper"


@dataclass
class GeographicSettings:
    """Geographic and language settings"""
    # Country code (gl) - ISO 3166-1 alpha-2
    country: str = "us"  # Default to United States

    # Language code (hl) - ISO 639-1
    language: str = "en"  # Default to English

    # Location (human-readable)
    location: str = ""  # Optional, e.g., "New York, United States"


@dataclass
class ResultSettings:
    """Result retrieval settings"""
    # Number of results per search type
    num_results: int = 20

    # Enable expanded search (videos + scholar)
    enable_videos: bool = False
    enable_scholar: bool = False

    # Enable document/PDF-specific search (adds " pdf" to query)
    enable_document_search: bool = False

    # Calculate total results
    @property
    def total_results(self) -> int:
        """Calculate total results across all enabled search types"""
        count = self.num_results  # Base search
        if self.enable_videos:
            count += self.num_results
        if self.enable_scholar:
            count += self.num_results
        if self.enable_document_search:
            count += 10  # Document search always fetches page 1 (10 results)
        return count


@dataclass
class TimeFilterSettings:
    """Time filtering and safety settings"""
    # Time filter options: None, "qdr:d" (day), "qdr:w" (week), "qdr:m" (month), "qdr:y" (year)
    time_filter: Optional[str] = None  # None, "day", "week", "month", "year", "custom"

    # Custom date range (if time_filter == "custom")
    custom_start_date: Optional[str] = None  # YYYY-MM-DD
    custom_end_date: Optional[str] = None    # YYYY-MM-DD

    # Safe search: "active" or "off"
    safe_search: Literal["active", "off"] = "off"

    # Enable autocorrect
    enable_autocorrect: bool = True

    def get_tbs_value(self) -> Optional[str]:
        """Convert time_filter to Serper tbs parameter"""
        if not self.time_filter or self.time_filter == "None":
            return None
        elif self.time_filter == "day":
            return "qdr:d"
        elif self.time_filter == "week":
            return "qdr:w"
        elif self.time_filter == "month":
            return "qdr:m"
        elif self.time_filter == "year":
            return "qdr:y"
        elif self.time_filter == "custom" and self.custom_start_date and self.custom_end_date:
            # Format: cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY
            start = datetime.strptime(self.custom_start_date, "%Y-%m-%d").strftime("%m/%d/%Y")
            end = datetime.strptime(self.custom_end_date, "%Y-%m-%d").strftime("%m/%d/%Y")
            return f"cd_min:{start},cd_max:{end}"
        return None


@dataclass
class AnalysisSettings:
    """Content analysis settings"""
    # Worker settings
    max_workers: int = 10  # Total parallel workers
    max_download_workers: int = 5  # Concurrent downloads
    router_max_workers: int = 1  # Router thread pool workers (usually 1 is sufficient)

    # Timeout settings (seconds)
    html_timeout: int = 4  # HTML download timeout
    pdf_timeout: int = 8   # PDF download timeout
    url_timeout: int = 3   # General URL timeout
    api_health_timeout: int = 5  # API health check timeout
    api_stream_timeout: int = 300  # API streaming analysis timeout (5 minutes)
    thread_join_timeout: int = 180  # Background worker thread join timeout (3 minutes)
    database_busy_timeout: int = 30  # SQLite busy timeout (seconds)

    # Retry settings
    max_retry_attempts: int = 0  # Maximum retry attempts for failed requests (0 = no retries, single attempt only)
    retry_delay: int = 2  # Delay between retries (seconds)

    # Rate limiting
    rate_limit_per_domain: int = 4  # Max concurrent requests per domain
    rate_limit_delay: float = 0.1  # Delay between requests to same domain (seconds)

    # Filtering thresholds
    html_quality_threshold: int = 40  # Minimum quality score for HTML content
    pdf_quality_threshold: int = 40   # Minimum quality score for PDF content

    # PDF specific settings
    pdf_max_size_mb: int = 60  # Maximum PDF file size in MB
    pdf_max_pages: int = 2000   # Maximum pages to extract from PDF

    # Cache freshness defaults (days) - used when not specified by content type
    default_pdf_freshness_days: int = 30  # Default PDF cache freshness
    default_cache_freshness_days: int = 30  # Default general cache freshness


@dataclass
class CacheSettings:
    """Cache freshness and enablement settings"""
    # ========== Cache Enablement ==========
    enable_serper_cache: bool = True  # Cache Serper API results
    enable_html_cache: bool = True    # Cache HTML processing results

    # ========== Fuzzy Query Matching ==========
    enable_fuzzy_cache_matching: bool = True  # Enable fuzzy/similarity-based query matching
    fuzzy_match_threshold: int = 98  # Minimum similarity score for fuzzy matching (0-100, higher = more strict)

    # ========== Serper Cache Freshness (Hours) - Individual per search type ==========
    serper_news_freshness_hours: int = 6      # News: 6 hours (frequent updates)
    serper_search_freshness_hours: int = 24   # General search: 24 hours
    serper_videos_freshness_hours: int = 48   # Videos: 48 hours
    serper_scholar_freshness_hours: int = 168 # Scholar: 7 days (168 hours)

    # ========== HTML Cache Freshness (Days) - Individual per content type ==========
    html_news_staleness_days: int = 7       # News articles: 7 days
    html_blog_staleness_days: int = 7       # Blog posts: 7 days
    html_product_staleness_days: int = 30   # Product pages: 30 days
    html_docs_staleness_days: int = 30      # Documentation: 30 days
    html_evergreen_staleness_days: int = 90 # Evergreen content: 90 days
    html_unknown_staleness_days: int = 30   # Unknown content: 30 days

    # ========== URL Revalidation Settings ==========
    # If content was last fetched > threshold days ago, revalidate it
    revalidation_threshold_days: int = 15  # Revalidate if last fetch > 15 days ago

    # ========== Error & Filtered Cache (Days) ==========
    error_cache_days: int = 15     # How long to remember failed URLs
    filtered_cache_days: int = 15  # How long to remember filtered URLs

    # ========== Cache Size Limits ==========
    max_cache_size_gb: int = 100  # Maximum cache database size in GB

    # ========== Helper Properties ==========
    @property
    def serper_freshness_by_type(self) -> Dict[str, int]:
        """Get Serper freshness by search type (hours)"""
        return {
            'news': self.serper_news_freshness_hours,
            'search': self.serper_search_freshness_hours,
            'videos': self.serper_videos_freshness_hours,
            'scholar': self.serper_scholar_freshness_hours
        }

    @property
    def html_staleness_by_type(self) -> Dict[str, int]:
        """Get HTML staleness by content type (days)"""
        return {
            'news': self.html_news_staleness_days,
            'blog': self.html_blog_staleness_days,
            'product': self.html_product_staleness_days,
            'docs': self.html_docs_staleness_days,
            'documentation': self.html_docs_staleness_days,
            'evergreen': self.html_evergreen_staleness_days,
            'unknown': self.html_unknown_staleness_days
        }


@dataclass
class PDFSettings:
    """PDF processing settings"""
    # spaCy enrichment (TOGGLE: Turn on/off here)
    spacy_enabled: bool = False  # ← SET TRUE TO ENABLE NLP ENRICHMENT
    spacy_require_gpu: bool = True  # Require GPU (error if unavailable)
    spacy_enable_ner: bool = True  # Enable named entity recognition
    spacy_enable_chunks: bool = False  # Enable noun chunks (requires parser)

    # Extraction settings
    pdf_max_pages: Optional[int] = None  # None = process all pages
    pdf_enable_tables: bool = True
    pdf_enable_lists: bool = True
    pdf_transliterate_unicode: bool = False  # Use unidecode for non-ASCII

    def __post_init__(self):
        """Validation"""
        if self.spacy_enabled and not self.spacy_require_gpu:
            print("[WARN] spaCy enabled without GPU requirement - will use CPU if GPU unavailable")


@dataclass
class PDFScoringSettings:
    """PDF Content Scoring Configuration (sum = 100 points)

    6 weighted signals that sum to 100 points:
    1. Metadata Completeness (max 25)
    2. Date Recency (max 10)
    3. Domain Trust (max 20)
    4. Content Length (max 20)
    5. Document Structure (max 12)
    6. Words-per-Page (max 8)
    7. Named Entities (max 5)

    Quality Classifications:
    - 70-100: "legit" - High-quality, legitimate content
    - 40-69: "maybe" - Medium quality, potentially useful
    - 0-39: "skip" - Low quality, should be filtered
    """

    # ========== 1. Metadata Completeness (max 25) ==========
    metadata_title_min_chars: int = 4
    metadata_author_min_chars: int = 3

    # ========== 2. Date Recency (max 10) ==========
    date_recency_days: int = 730  # 2 years

    # ========== 3. Domain Trust (max 20) ==========
    # Trust levels configured in code (highly_trusted, trusted, good domains)

    # ========== 4. Content Length (max 20) ==========
    content_optimal_min: int = 600
    content_optimal_max: int = 10000
    content_long_min: int = 10001
    content_long_max: int = 30000
    content_short_min: int = 300
    content_short_max: int = 599

    # ========== 5. Document Structure (max 12) ==========
    structure_min_headings_high: int = 3  # For +12 points
    structure_min_headings_low: int = 1   # For +6 points

    # ========== 6. Words-per-Page (max 8) ==========
    wpp_optimal_min: int = 200
    wpp_optimal_max: int = 500
    wpp_acceptable_min: int = 100
    wpp_acceptable_max: int = 800

    # ========== 7. Named Entities (max 5) ==========
    entities_min_count: int = 2  # Minimum proper nouns in opening paragraph

    # ========== Quality Classification Thresholds ==========
    threshold_legit: int = 70   # >= 70 = "legit"
    threshold_maybe: int = 40   # 40-69 = "maybe"
    # < 40 = "skip"


@dataclass
class BackgroundProcessingSettings:
    """Background PDF processing settings for two-tier system

    Fast Lane: 6 second timeout for immediate results
    Background Queue: Unlimited time for slow PDFs, cached for future use
    """
    # ========== Feature Toggle ==========
    enabled: bool = True  # Enable two-tier processing system

    # ========== Fast Lane Timeouts (seconds) ==========
    fast_lane_timeout: int = 6  # Total timeout for fast lane processing
    download_timeout: int = 4   # Download timeout within fast lane
    processing_timeout: int = 4 # Processing timeout within fast lane

    # ========== Background Worker ==========
    worker_enabled: bool = True  # Enable background worker process
    worker_sleep_interval: int = 1  # Seconds between queue checks
    max_retry_attempts: int = 3  # Maximum retry attempts for failed PDFs

    # ========== Queue Management ==========
    queue_type: str = "sqlite"  # Queue storage: sqlite, redis, or file
    queue_path: str = "db/background_queue.db"  # Path to queue database

    # ========== Cache Integration ==========
    pdf_freshness_days: int = 30  # PDFs fresh for 30 days (no revalidation)

    # ========== Cleanup ==========
    cleanup_completed_days: int = 7  # Remove completed items after 7 days


@dataclass
class EmbeddingSettings:
    """Azure OpenAI embedding settings for semantic search

    Uses Azure OpenAI text-embedding-3-small model for document embedding
    Embeddings are stored in SQLite for semantic search
    """
    # ========== Feature Toggle ==========
    enabled: bool = True  # Enable embedding generation

    # ========== Azure OpenAI Configuration ==========
    azure_endpoint: str = ""
    api_key: str = ""
    model_name: str = "text-embedding-3-small"
    deployment_name: str = "text-embedding-3-small"
    api_version: str = "2024-12-01-preview"

    # ========== Batch Processing ==========
    max_chunk_batch_size: int = 500  # Max chunks to send in one API call (Azure limit: 500)

    # ========== Semantic Search ==========
    similarity_threshold: float = 0.7  # Minimum cosine similarity for results (0-1)
    max_search_results: int = 20  # Maximum results to return from search


@dataclass
class AppSettings:
    """Main application settings container"""
    search: SearchSettings = field(default_factory=SearchSettings)
    geographic: GeographicSettings = field(default_factory=GeographicSettings)
    results: ResultSettings = field(default_factory=ResultSettings)
    time_filter: TimeFilterSettings = field(default_factory=TimeFilterSettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    pdf: PDFSettings = field(default_factory=PDFSettings)
    pdf_scoring: PDFScoringSettings = field(default_factory=PDFScoringSettings)
    background: BackgroundProcessingSettings = field(default_factory=BackgroundProcessingSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)

    def to_dict(self) -> Dict:
        """Convert settings to dictionary"""
        return {
            'search': asdict(self.search),
            'geographic': asdict(self.geographic),
            'results': asdict(self.results),
            'time_filter': asdict(self.time_filter),
            'analysis': asdict(self.analysis),
            'cache': asdict(self.cache),
            'pdf': asdict(self.pdf),
            'pdf_scoring': asdict(self.pdf_scoring),
            'background': asdict(self.background),
            'embedding': asdict(self.embedding)
        }

    def to_json(self) -> str:
        """Convert settings to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> 'AppSettings':
        """Create settings from dictionary with backward compatibility"""
        # Migrate old cache settings format
        cache_data = data.get('cache', {})

        # Handle old field names
        if 'serper_freshness_days' in cache_data:
            # Convert days to hours (old default was 7 days = 168 hours)
            cache_data.pop('serper_freshness_days')

        if 'enable_processing_cache' in cache_data:
            # Rename to enable_html_cache
            cache_data['enable_html_cache'] = cache_data.pop('enable_processing_cache')

        if 'enable_pdf_cache' in cache_data:
            # Remove PDF cache setting
            cache_data.pop('enable_pdf_cache')

        # Migrate old revalidation fields to single threshold
        if 'recent_content_threshold_days' in cache_data:
            cache_data['revalidation_threshold_days'] = cache_data.pop('recent_content_threshold_days')
        if 'recent_news_revalidate_hours' in cache_data:
            cache_data.pop('recent_news_revalidate_hours')
        if 'normal_revalidate_days' in cache_data:
            cache_data.pop('normal_revalidate_days')

        # Convert MB to GB for cache size limit
        if 'max_cache_size_mb' in cache_data:
            mb_value = cache_data.pop('max_cache_size_mb')
            cache_data['max_cache_size_gb'] = max(1, mb_value // 1024)  # Convert to GB

        # Remove obsolete fields
        obsolete_fields = ['html_freshness_days', 'pdf_freshness_days', 'serper_freshness_hours']
        for field in obsolete_fields:
            cache_data.pop(field, None)

        # Valid cache fields in new version
        valid_cache_fields = {
            'enable_serper_cache', 'enable_html_cache',
            'enable_fuzzy_cache_matching', 'fuzzy_match_threshold',  # Fuzzy matching settings
            'serper_news_freshness_hours', 'serper_search_freshness_hours',
            'serper_videos_freshness_hours', 'serper_scholar_freshness_hours',
            'html_news_staleness_days', 'html_blog_staleness_days',
            'html_product_staleness_days', 'html_docs_staleness_days',
            'html_evergreen_staleness_days', 'html_unknown_staleness_days',
            'revalidation_threshold_days', 'error_cache_days', 'filtered_cache_days',
            'max_cache_size_gb'
        }
        cache_data = {k: v for k, v in cache_data.items() if k in valid_cache_fields}

        return cls(
            search=SearchSettings(**data.get('search', {})),
            geographic=GeographicSettings(**data.get('geographic', {})),
            results=ResultSettings(**data.get('results', {})),
            time_filter=TimeFilterSettings(**data.get('time_filter', {})),
            analysis=AnalysisSettings(**data.get('analysis', {})),
            cache=CacheSettings(**cache_data),
            pdf=PDFSettings(**data.get('pdf', {})),
            pdf_scoring=PDFScoringSettings(**data.get('pdf_scoring', {})),
            background=BackgroundProcessingSettings(**data.get('background', {})),
            embedding=EmbeddingSettings(**data.get('embedding', {}))
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'AppSettings':
        """Create settings from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def save(self, filepath: str):
        """Save settings to file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath: str) -> 'AppSettings':
        """Load settings from file"""
        if not os.path.exists(filepath):
            return cls()  # Return defaults
        with open(filepath, 'r') as f:
            return cls.from_json(f.read())


# Serper-supported values
# Source: https://serper.dev/playground

SUPPORTED_COUNTRIES = {
    "us": "United States",
    "uk": "United Kingdom",
    "ca": "Canada",
    "au": "Australia",
    "in": "India",
    "de": "Germany",
    "fr": "France",
    "es": "Spain",
    "it": "Italy",
    "nl": "Netherlands",
    "se": "Sweden",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "pl": "Poland",
    "ru": "Russia",
    "jp": "Japan",
    "cn": "China",
    "kr": "South Korea",
    "br": "Brazil",
    "mx": "Mexico",
    "ar": "Argentina",
    "za": "South Africa",
    "eg": "Egypt",
    "sa": "Saudi Arabia",
    "ae": "United Arab Emirates",
    "sg": "Singapore",
    "my": "Malaysia",
    "id": "Indonesia",
    "th": "Thailand",
    "ph": "Philippines",
    "vn": "Vietnam",
    "nz": "New Zealand",
    "ie": "Ireland",
    "at": "Austria",
    "ch": "Switzerland",
    "be": "Belgium",
    "pt": "Portugal",
    "gr": "Greece",
    "cz": "Czech Republic",
    "hu": "Hungary",
    "ro": "Romania",
    "ua": "Ukraine",
    "tr": "Turkey",
    "il": "Israel",
    "pk": "Pakistan",
    "bd": "Bangladesh",
    "ng": "Nigeria",
    "ke": "Kenya",
    "gh": "Ghana",
    "cl": "Chile",
    "co": "Colombia",
    "pe": "Peru",
    "ve": "Venezuela"
}

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ar": "Arabic",
    "hi": "Hindi",
    "bn": "Bengali",
    "pa": "Punjabi",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "ur": "Urdu",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "pl": "Polish",
    "uk": "Ukrainian",
    "ro": "Romanian",
    "el": "Greek",
    "cs": "Czech",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "hu": "Hungarian",
    "he": "Hebrew",
    "id": "Indonesian",
    "ms": "Malay",
    "fa": "Persian",
    "sw": "Swahili"
}

# Common locations (examples - users can enter any location)
EXAMPLE_LOCATIONS = [
    "New York, United States",
    "London, United Kingdom",
    "Toronto, Canada",
    "Sydney, Australia",
    "Mumbai, India",
    "Berlin, Germany",
    "Paris, France",
    "Tokyo, Japan",
    "Seoul, South Korea",
    "Singapore",
    "Dubai, United Arab Emirates",
    "San Francisco, United States",
    "Los Angeles, United States",
    "Chicago, United States",
    "Boston, United States",
    "Seattle, United States",
    "Austin, United States",
    "Miami, United States",
]


# Default settings instance
DEFAULT_SETTINGS = AppSettings()


# Settings file path
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "user_settings.json")
