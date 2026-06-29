"""
Home Page - Main landing page with all tabs
"""
import streamlit as st
from services.cache_service import CacheService
from services.helpers.date_provenance import DateProvenanceDetector
from config.settings import AppSettings, SETTINGS_FILE
from components.sidebar import render_sidebar
from components.tab_search import render_search_tab
from components.tab_failed_pdfs import render_failed_pdfs_tab
from components.tab_scoring import render_scoring_tab


# Initialize cache service (singleton)
@st.cache_resource
def get_cache_service():
    return CacheService()


@st.cache_resource
def get_date_detector():
    return DateProvenanceDetector()


@st.cache_resource
def get_app_settings():
    """Load app settings (cached)"""
    return AppSettings.load(SETTINGS_FILE)


def render_home():
    """Render the main home page with all tabs"""

    # Page config is set in app.py - don't set it here to avoid conflicts
    # Get cached resources
    cache = get_cache_service()
    date_detector = get_date_detector()
    app_settings = get_app_settings()

    # Title
    st.title("🔍 OpenQuery AI Search & Content Analyzer")

    # Render sidebar
    render_sidebar()

    # Create tabs for different sections
    tab1, tab2, tab3 = st.tabs(["🔍 Search & Analyze", "📋 Failed PDF Downloads", "⚙️ PDF Scoring Settings"])

    # Render each tab
    with tab1:
        render_search_tab(cache, app_settings)

    with tab2:
        render_failed_pdfs_tab()

    with tab3:
        render_scoring_tab(app_settings)


if __name__ == "__main__":
    render_home()
