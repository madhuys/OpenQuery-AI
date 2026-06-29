"""
Tab 3: PDF Scoring Settings
Configuration interface for PDF quality scoring
"""
import streamlit as st
import json
import time
from config.settings import AppSettings, SETTINGS_FILE, PDFScoringSettings


def render_scoring_tab(app_settings: AppSettings):
    """Render the PDF Scoring Settings tab"""
    
    st.header("⚙️ PDF Content Scoring Configuration")

    st.markdown("""
    **PDF Scoring System**: 6 weighted signals summing to **100 points**

    **Quality Classifications:**
    - 🟢 **70-100**: "legit" - High-quality, legitimate content
    - 🟡 **40-69**: "maybe" - Medium quality, potentially useful
    - 🔴 **0-39**: "skip" - Low quality, should be filtered
    """)

    st.divider()

    # Load current settings
    scoring_settings = app_settings.pdf_scoring

    # Render scoring configuration UI
    settings_values = _render_scoring_settings(scoring_settings)

    # Save button
    _render_save_controls(app_settings, settings_values)

    # Export/Import controls
    _render_export_import_controls(app_settings)


def _render_scoring_settings(scoring_settings) -> dict:
    """Render scoring settings inputs and return all values"""
    
    col_left, col_right = st.columns(2)

    with col_left:
        left_values = _render_left_column_settings(scoring_settings)

    with col_right:
        right_values = _render_right_column_settings(scoring_settings)

    st.divider()

    # Quality classification thresholds
    st.subheader("📊 Quality Classification Thresholds")

    thresh_col1, thresh_col2 = st.columns(2)
    with thresh_col1:
        threshold_legit = st.number_input(
            "🟢 Legit threshold (min score)",
            min_value=50,
            max_value=100,
            value=scoring_settings.threshold_legit,
            help="Scores ≥ this value are classified as 'legit'"
        )

    with thresh_col2:
        threshold_maybe = st.number_input(
            "🟡 Maybe threshold (min score)",
            min_value=0,
            max_value=80,
            value=scoring_settings.threshold_maybe,
            help="Scores ≥ this value but < legit threshold are classified as 'maybe'"
        )

    st.info(f"🔴 Skip: < {threshold_maybe} points | 🟡 Maybe: {threshold_maybe}-{threshold_legit-1} points | 🟢 Legit: {threshold_legit}+ points")

    # Combine all values
    all_values = {**left_values, **right_values, 
                  'threshold_legit': threshold_legit, 
                  'threshold_maybe': threshold_maybe}
    
    return all_values


def _render_left_column_settings(scoring_settings) -> dict:
    """Render left column settings (Metadata, Date, Domain, Content Length)"""
    
    # 1. Metadata Completeness
    st.subheader("1️⃣ Metadata Completeness (max 25)")
    st.caption("Title ≥ min chars = +8 | Author ≥ min chars = +7 | Subject = +5 | Keywords = +5")

    metadata_title_min = st.number_input(
        "Minimum title length (chars)",
        min_value=1,
        max_value=20,
        value=scoring_settings.metadata_title_min_chars,
        help="Title with ≥ this many characters gets +8 points"
    )

    metadata_author_min = st.number_input(
        "Minimum author length (chars)",
        min_value=1,
        max_value=20,
        value=scoring_settings.metadata_author_min_chars,
        help="Author with ≥ this many characters gets +7 points"
    )

    st.divider()

    # 2. Date Recency
    st.subheader("2️⃣ Date Recency (max 10)")
    st.caption("Recent documents = +10 | Old documents = +0")

    date_recency_days = st.number_input(
        "Recent threshold (days)",
        min_value=30,
        max_value=3650,
        value=scoring_settings.date_recency_days,
        step=30,
        help="Documents created/modified within this many days get +10 points"
    )

    st.divider()

    # 3. Domain Trust
    st.subheader("3️⃣ Domain Trust (max 20)")
    st.markdown("""
    **Trust levels (configured in code):**
    - **Highly Trusted (+20)**: .gov, .mil, whitehouse.gov, un.org, worldbank.org, imf.org, nber.org
    - **Trusted (+15)**: .edu, arxiv.org, nature.com, science.org, microsoft.com, mckinsey.com, stanford.edu, mit.edu
    - **Good (+8)**: reuters.com, bloomberg.com, bbc.com, generic .org
    - **Unknown (+0)**: All other domains
    """)

    st.divider()

    # 4. Content Length
    st.subheader("4️⃣ Content Length (max 20)")
    st.caption("Different word count ranges receive different scores")

    content_values = _render_content_length_settings(scoring_settings)

    return {
        'metadata_title_min': metadata_title_min,
        'metadata_author_min': metadata_author_min,
        'date_recency_days': date_recency_days,
        **content_values
    }


def _render_content_length_settings(scoring_settings) -> dict:
    """Render content length settings"""
    
    content_col1, content_col2 = st.columns(2)
    
    with content_col1:
        st.markdown("**Optimal (+20 points)**")
        content_optimal_min = st.number_input(
            "Min words",
            min_value=100,
            max_value=5000,
            value=scoring_settings.content_optimal_min,
            key="optimal_min"
        )
        content_optimal_max = st.number_input(
            "Max words",
            min_value=1000,
            max_value=50000,
            value=scoring_settings.content_optimal_max,
            key="optimal_max"
        )

    with content_col2:
        st.markdown("**Long (+14 points)**")
        content_long_min = st.number_input(
            "Min words",
            min_value=5000,
            max_value=50000,
            value=scoring_settings.content_long_min,
            key="long_min"
        )
        content_long_max = st.number_input(
            "Max words",
            min_value=10000,
            max_value=100000,
            value=scoring_settings.content_long_max,
            key="long_max"
        )

    st.markdown("**Short (+8 points)**")
    content_short_col1, content_short_col2 = st.columns(2)
    with content_short_col1:
        content_short_min = st.number_input(
            "Min words",
            min_value=50,
            max_value=1000,
            value=scoring_settings.content_short_min,
            key="short_min"
        )
    with content_short_col2:
        content_short_max = st.number_input(
            "Max words",
            min_value=200,
            max_value=5000,
            value=scoring_settings.content_short_max,
            key="short_max"
        )

    return {
        'content_optimal_min': content_optimal_min,
        'content_optimal_max': content_optimal_max,
        'content_long_min': content_long_min,
        'content_long_max': content_long_max,
        'content_short_min': content_short_min,
        'content_short_max': content_short_max
    }


def _render_right_column_settings(scoring_settings) -> dict:
    """Render right column settings (Structure, WPP, Entities)"""
    
    # 5. Document Structure
    st.subheader("5️⃣ Document Structure (max 12)")
    st.caption("Well-structured documents have clear headings")

    structure_min_high = st.number_input(
        "Min headings for +12 points",
        min_value=1,
        max_value=10,
        value=scoring_settings.structure_min_headings_high,
        help="Documents with ≥ this many headings get +12 points"
    )

    structure_min_low = st.number_input(
        "Min headings for +6 points",
        min_value=1,
        max_value=10,
        value=scoring_settings.structure_min_headings_low,
        help="Documents with ≥ this many headings get +6 points"
    )

    st.divider()

    # 6. Words-per-Page Density
    st.subheader("6️⃣ Words-per-Page Density (max 8)")
    st.caption("Professional PDFs have 200-500 words per page")

    wpp_values = _render_wpp_settings(scoring_settings)

    st.divider()

    # 7. Named Entities
    st.subheader("7️⃣ Named Entities (max 5)")
    st.caption("Quality content references specific people, places, organizations early")

    entities_min_count = st.number_input(
        "Min proper nouns in opening paragraph",
        min_value=1,
        max_value=10,
        value=scoring_settings.entities_min_count,
        help="Documents with ≥ this many proper nouns in opening get +5 points"
    )

    return {
        'structure_min_high': structure_min_high,
        'structure_min_low': structure_min_low,
        'entities_min_count': entities_min_count,
        **wpp_values
    }


def _render_wpp_settings(scoring_settings) -> dict:
    """Render words-per-page settings"""
    
    wpp_col1, wpp_col2 = st.columns(2)
    
    with wpp_col1:
        st.markdown("**Optimal (+8 points)**")
        wpp_optimal_min = st.number_input(
            "Min words/page",
            min_value=50,
            max_value=500,
            value=scoring_settings.wpp_optimal_min,
            key="wpp_opt_min"
        )
        wpp_optimal_max = st.number_input(
            "Max words/page",
            min_value=200,
            max_value=1000,
            value=scoring_settings.wpp_optimal_max,
            key="wpp_opt_max"
        )

    with wpp_col2:
        st.markdown("**Acceptable (+3 points)**")
        wpp_acceptable_min = st.number_input(
            "Min words/page",
            min_value=10,
            max_value=300,
            value=scoring_settings.wpp_acceptable_min,
            key="wpp_acc_min"
        )
        wpp_acceptable_max = st.number_input(
            "Max words/page",
            min_value=300,
            max_value=2000,
            value=scoring_settings.wpp_acceptable_max,
            key="wpp_acc_max"
        )

    return {
        'wpp_optimal_min': wpp_optimal_min,
        'wpp_optimal_max': wpp_optimal_max,
        'wpp_acceptable_min': wpp_acceptable_min,
        'wpp_acceptable_max': wpp_acceptable_max
    }


def _render_save_controls(app_settings: AppSettings, settings_values: dict):
    """Render save button and handle saving"""
    
    st.divider()
    
    col_save1, col_save2, col_save3 = st.columns([1, 1, 1])

    with col_save2:
        if st.button("💾 Save PDF Scoring Settings", type="primary", use_container_width=True):
            _save_settings(app_settings, settings_values)


def _save_settings(app_settings: AppSettings, settings_values: dict):
    """Save all PDF scoring settings"""
    
    # Update settings
    app_settings.pdf_scoring.metadata_title_min_chars = settings_values['metadata_title_min']
    app_settings.pdf_scoring.metadata_author_min_chars = settings_values['metadata_author_min']
    app_settings.pdf_scoring.date_recency_days = settings_values['date_recency_days']
    app_settings.pdf_scoring.content_optimal_min = settings_values['content_optimal_min']
    app_settings.pdf_scoring.content_optimal_max = settings_values['content_optimal_max']
    app_settings.pdf_scoring.content_long_min = settings_values['content_long_min']
    app_settings.pdf_scoring.content_long_max = settings_values['content_long_max']
    app_settings.pdf_scoring.content_short_min = settings_values['content_short_min']
    app_settings.pdf_scoring.content_short_max = settings_values['content_short_max']
    app_settings.pdf_scoring.structure_min_headings_high = settings_values['structure_min_high']
    app_settings.pdf_scoring.structure_min_headings_low = settings_values['structure_min_low']
    app_settings.pdf_scoring.wpp_optimal_min = settings_values['wpp_optimal_min']
    app_settings.pdf_scoring.wpp_optimal_max = settings_values['wpp_optimal_max']
    app_settings.pdf_scoring.wpp_acceptable_min = settings_values['wpp_acceptable_min']
    app_settings.pdf_scoring.wpp_acceptable_max = settings_values['wpp_acceptable_max']
    app_settings.pdf_scoring.entities_min_count = settings_values['entities_min_count']
    app_settings.pdf_scoring.threshold_legit = settings_values['threshold_legit']
    app_settings.pdf_scoring.threshold_maybe = settings_values['threshold_maybe']

    # Save to file
    app_settings.save(SETTINGS_FILE)

    st.success("✅ PDF scoring settings saved successfully!")
    st.balloons()
    time.sleep(1)
    st.rerun()


def _render_export_import_controls(app_settings: AppSettings):
    """Render export/import controls"""
    
    st.divider()
    st.subheader("📤 Export / Import Settings")

    export_col1, export_col2 = st.columns(2)

    with export_col1:
        # Export current settings as JSON
        current_scoring_json = json.dumps(app_settings.pdf_scoring.__dict__, indent=2)
        st.download_button(
            label="📥 Download PDF Scoring Config (JSON)",
            data=current_scoring_json,
            file_name="pdf_scoring_config.json",
            mime="application/json",
            use_container_width=True
        )

    with export_col2:
        # Reset to defaults
        if st.button("🔄 Reset to Default Values", use_container_width=True):
            app_settings.pdf_scoring = PDFScoringSettings()
            app_settings.save(SETTINGS_FILE)
            st.success("✅ Reset to default PDF scoring settings!")
            time.sleep(1)
            st.rerun()
