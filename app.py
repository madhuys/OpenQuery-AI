"""
OpenQuery AI Search & Content Analyzer
Main application entry point - Orchestration only
"""
import streamlit as st

# Page config - MUST be first Streamlit command
st.set_page_config(
    page_title="OpenQuery AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for consistent navigation
if 'initialized' not in st.session_state:
    st.session_state.initialized = True

# Import and render home page
from pages.home import render_home

# Always render home page
render_home()
