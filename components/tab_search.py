"""
Search & Analyze Tab Component - Orchestrator
Coordinates search_panel, progress_panel, and content_analysis_panel
"""
import streamlit as st
from components.search_panel import render_search_panel
from components.progress_panel import render_progress_panel
from components.content_analysis_panel import render_content_analysis_panel
from services.cache_service import CacheService
from config.settings import AppSettings


def render_search_tab(cache: CacheService, app_settings: AppSettings):
    """Render the Search & Analyze tab - orchestrates 3 sub-components"""
    
    # Left column: Search settings panel
    # Right column: Progress and content analysis
    col_left, col_right = st.columns([2, 3])

    with col_left:
        search_clicked, search_params = render_search_panel(app_settings)

    # Clear old results when new search is clicked
    if search_clicked:
        # Clear all old results immediately
        if "analysis_results" in st.session_state:
            del st.session_state["analysis_results"]
        if "analysis_status" in st.session_state:
            del st.session_state["analysis_status"]
        if "extracted_urls" in st.session_state:
            del st.session_state["extracted_urls"]
        if "search_results" in st.session_state:
            del st.session_state["search_results"]
        if "pdf_processing_results" in st.session_state:
            del st.session_state["pdf_processing_results"]
        if "processing_complete" in st.session_state:
            del st.session_state["processing_complete"]

    with col_right:
        # Show progress panel if processing or no results yet
        if st.session_state.get('processing', False) or "analysis_results" not in st.session_state:
            render_progress_panel(cache, app_settings, search_clicked, search_params)
        else:
            # Show content analysis panel when results are ready
            render_content_analysis_panel()
