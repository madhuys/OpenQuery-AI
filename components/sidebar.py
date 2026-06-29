"""
Sidebar component for displaying app information and system status
"""
import streamlit as st
import multiprocessing
import psutil
from components import api_client


def render_sidebar():
    """Render the application sidebar with info and system stats"""
    
    with st.sidebar:
        _render_about_section()
        st.divider()
        _render_api_status()
        st.divider()
        _render_system_resources()
        st.divider()
        st.caption("ℹ️ Web scraping is I/O-bound (network requests), not compute-bound. CPU multi-threading is optimal for this task.")


def _render_about_section():
    """Render about section"""
    st.header("ℹ️ About")
    st.markdown("""
    Intelligent search with automatic content analysis.

    **Features:**
    - 🔍 **Search**: Google (Serper) & DuckDuckGo engines
    - ⚡ **Parallel Processing**: Multi-threaded content extraction
    - 🧹 **Clean Content**: AI-powered content cleaning

    **Search Types:**
    - 🌐 Web Search
    - 📰 News
    - 🎥 Videos
    - 🎓 Scholar
    """)


def _render_api_status():
    """Render API status section"""
    st.header("🔧 API Status")
    
    # Check API connection
    is_running, status_code = api_client.check_api_status()
    if is_running:
        st.success("✅ API is running")
    else:
        st.error("❌ Cannot connect to API")

    st.caption("FastAPI server on port 8000")

    # GPU Status - DISABLED (not using GPU for processing)
    # gpu_data = api_client.get_gpu_status()
    # if gpu_data:
    #     if gpu_data.get("cuda_available"):
    #         st.success(f"🚀 GPU: {gpu_data.get('device_name', 'Unknown')}")
    #         st.caption(f"CUDA {gpu_data.get('cuda_version', 'N/A')} | spaCy GPU: {'✅' if gpu_data.get('spacy_gpu_enabled') else '❌'}")
    #     else:
    #         st.warning("⚠️ GPU: CPU only")
    #         if "error" in gpu_data:
    #             st.caption(f"Reason: {gpu_data['error']}")


def _render_system_resources():
    """Render system resources section with real-time updates"""
    import time
    
    st.header("⚡ System Resources")

    # Get real-time data (force fresh reading)
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = multiprocessing.cpu_count()
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    memory_used_gb = memory.used / (1024**3)
    memory_total_gb = memory.total / (1024**3)
    process = psutil.Process()
    thread_count = process.num_threads()
    net_io = psutil.net_io_counters()

    # CPU Usage
    st.metric("CPU Usage", f"{cpu_percent}%", help=f"{cpu_count} cores available")
    st.progress(cpu_percent / 100.0)
    
    # Memory Usage
    st.metric("Memory Usage", f"{memory_percent}%",
              help=f"{memory_used_gb:.1f}GB / {memory_total_gb:.1f}GB")
    st.progress(memory_percent / 100.0)
    
    # Thread count and Network I/O
    st.caption(f"🔧 Active Threads: {thread_count}")
    st.caption(f"📡 Network: ↑{net_io.bytes_sent / (1024**2):.1f}MB ↓{net_io.bytes_recv / (1024**2):.1f}MB")
    
    # Show last update time
    st.caption(f"🕐 Updated: {time.strftime('%H:%M:%S')}")
    
    # Auto-refresh during processing
    if st.session_state.get('processing', False):
        time.sleep(1)  # Wait 1 second before rerunning
        st.rerun()
