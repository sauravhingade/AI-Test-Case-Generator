import time
import os
import json
import streamlit as st
import requests
import pandas as pd
from streamlit_local_storage import LocalStorage

API_BASE = st.secrets.get("API_BASE", os.getenv("API_BASE", "http://localhost:8000"))
local_storage = LocalStorage()

st.set_page_config(
    page_title="AI Test Case Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────
st.markdown(
    """
<style>
    .stApp { background-color: #0f1117; }
    [data-testid="metric-container"] {
        background: #1e2130;
        border: 1px solid #2d3250;
        border-radius: 10px;
        padding: 16px;
    }
    [data-testid="stExpander"] {
        background: #1e2130;
        border: 1px solid #2d3250;
        border-radius: 12px;
    }
    [data-testid="collapsedControl"] {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        background: #1e2130 !important;
        border: 1px solid #2d3250 !important;
        border-radius: 0 8px 8px 0 !important;
        width: 24px !important;
        height: 48px !important;
        top: 50% !important;
        left: 0 !important;
        transform: translateY(-50%) !important;
        position: fixed !important;
        z-index: 999999 !important;
        cursor: pointer !important;
    }
    [data-testid="collapsedControl"]:hover {
        background: #2d3250 !important;
        border-color: #4a90e2 !important;
    }
    [data-testid="collapsedControl"] svg {
        color: #a0aec0 !important;
        fill: #a0aec0 !important;
    }
    [data-testid="stSidebar"] {
        background: #13151f;
        border-right: 1px solid #2d3250;
    }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .block-container { padding-top: 2rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ── Session state ────────────────────────────────────────────
if "response_data" not in st.session_state:
    st.session_state.response_data = None

if "generated" not in st.session_state:
    st.session_state.generated = False

if "form_key" not in st.session_state:
    st.session_state.form_key = 0

if "ls_checked" not in st.session_state:
    st.session_state.ls_checked = False

# ── localStorage restore ─────────────────────────────────────
# On first render after browser reload, getItem returns None because
# the JS hasn't hydrated. We show a brief loading screen on that first
# render, then rerun ONCE. On the second render, getItem has the real value.
stored = local_storage.getItem("test_generator_results")

if not st.session_state.generated and not st.session_state.ls_checked:
    st.session_state.ls_checked = True
    if stored is None:
        # First render — JS not ready yet. Show loader and rerun once.
        with st.spinner("⏳ Restoring your session..."):
            time.sleep(0.4)
        st.rerun()
    elif stored and stored != "null":
        try:
            st.session_state.response_data = json.loads(stored)
            st.session_state.generated = True
        except Exception:
            pass
else:
    # Second render — JS is ready, try restore if still not generated
    if not st.session_state.generated and stored and stored != "null":
        try:
            st.session_state.response_data = json.loads(stored)
            st.session_state.generated = True
        except Exception:
            pass


# ── Constants ────────────────────────────────────────────────
PRIORITY_STYLES = {
    "critical": "background:#ff4c4c;color:white",
    "high": "background:#ff9900;color:white",
    "medium": "background:#ffd700;color:black",
    "low": "background:#90ee90;color:black",
}
PRIORITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
KEYWORD_COLORS = {
    "given": "#61dafb",
    "when": "#f7c948",
    "then": "#68d391",
    "and": "#b794f4",
    "but": "#fc8181",
}


# ── Helpers ──────────────────────────────────────────────────
def render_tc_card(tc: dict):
    priority = tc.get("priority", "high")
    is_edge = tc.get("is_edge_case", False)
    p_emoji = PRIORITY_EMOJI.get(priority, "🟠")
    p_style = PRIORITY_STYLES.get(priority, "background:#555;color:white")
    edge_label = "  ⚠️ Edge Case" if is_edge else ""

    with st.container():
        st.markdown(
            '<hr style="border:none;border-top:1px solid #2d3250;margin:4px 0 8px 0">',
            unsafe_allow_html=True,
        )
        col_meta, col_badge = st.columns([5, 1])
        with col_meta:
            st.markdown(
                f'<span style="color:#718096;font-size:12px;font-family:monospace"><b>{tc["id"]}</b></span>'
                f'<span style="color:#a0aec0;font-size:12px"> &nbsp;•&nbsp; {tc["test_type"].upper()}{edge_label}</span>',
                unsafe_allow_html=True,
            )
        with col_badge:
            st.markdown(
                f'<span style="{p_style};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;white-space:nowrap">'
                f"{p_emoji} {priority.upper()}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div style="font-size:15px;font-weight:600;color:#e2e8f0;margin:6px 0 10px 0">{tc["title"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div style="font-size:11px;color:#718096;text-transform:uppercase;margin-bottom:4px">Preconditions</div>',
            unsafe_allow_html=True,
        )
        for p in tc.get("preconditions", []):
            st.markdown(
                f'<div style="font-size:13px;color:#a0aec0;padding:1px 0">• {p}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;color:#718096;text-transform:uppercase;margin-bottom:4px">BDD Steps</div>',
            unsafe_allow_html=True,
        )
        for step in tc.get("steps", []):
            color = KEYWORD_COLORS.get(step["keyword"].lower(), "#b794f4")
            st.markdown(
                f'<div style="font-family:monospace;font-size:13px;padding:2px 0">'
                f'<span style="color:{color};font-weight:600">{step["keyword"]}</span> {step["action"]}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        st.markdown(
            '<div style="font-size:11px;color:#718096;text-transform:uppercase;margin-bottom:4px">Expected Result</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:13px;color:#68d391">✓ {tc["expected_result"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        tags_html = " ".join(
            f'<span style="background:#2d3250;color:#a0aec0;padding:2px 8px;border-radius:6px;font-size:11px;margin-right:4px">{t}</span>'
            for t in tc.get("tags", [])
        )
        st.markdown(tags_html, unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)


def get_rag_stats() -> int:
    try:
        r = requests.get(f"{API_BASE}/rag/stats", timeout=3)
        return r.json().get("indexed_test_cases", 0)
    except Exception:
        return 0


def check_api_health() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def clear_all_data():
    local_storage.deleteItem("test_generator_results")
    st.session_state.response_data = None
    st.session_state.generated = False
    st.session_state.ls_checked = False
    st.session_state.form_key += 1
    time.sleep(0.3)


# ── SIDEBAR ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧪 AI Test Generator")
    st.markdown("---")

    api_ok = check_api_health()

    if st.button("✨ New Test Generation", use_container_width=True, type="primary"):
        clear_all_data()
        st.toast("✨ Started a new session")
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ Configuration")

    test_types = st.multiselect(
        "Test Types",
        options=["functional", "negative", "edge_case", "regression", "performance"],
        default=["functional", "negative", "edge_case"],
    )
    bdd_format = st.selectbox(
        "BDD Format", options=["gherkin", "plain_english"], index=0
    )
    max_tc = st.slider("Max Test Cases per Story", min_value=1, max_value=15, value=5)

    st.markdown("---")
    st.markdown("### 📊 RAG Stats")
    rag_count = get_rag_stats()
    st.metric("Indexed Test Cases", rag_count)
    st.caption(
        "✨ RAG active — using past examples"
        if rag_count > 0
        else "⚪ RAG empty — first generation"
    )

    if rag_count > 0:
        if st.button("🗑️ Clear RAG", use_container_width=True):
            try:
                requests.delete(f"{API_BASE}/rag/clear")
                st.success("RAG cleared!")
                st.rerun()
            except Exception:
                st.error("Failed to clear RAG")

    st.markdown("---")

    if st.button("🗑️ Clear Session"):
        clear_all_data()
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.caption("GPT-4o + LangChain + ChromaDB RAG\nFastAPI + Streamlit")


# ── MAIN ─────────────────────────────────────────────────────
st.markdown("# 🧪 AI Test Case Generator")
st.markdown(
    "Upload a requirements document or paste text → Get structured BDD test cases instantly."
)
st.markdown("---")

input_tab, file_tab = st.tabs(["📝 Paste Text", "📄 Upload File"])
requirements_text = ""
uploaded_file = None

with input_tab:
    requirements_text = st.text_area(
        "Paste your requirements document here",
        height=200,
        placeholder="Example:\n1. User Registration\n   - Users can register with email and password\n   - Password must be minimum 8 characters",
        key=f"req_text_{st.session_state.form_key}",
    )

with file_tab:
    uploaded_file = st.file_uploader(
        "Upload requirements document",
        type=["pdf", "docx", "txt"],
        help="Supported: PDF, DOCX, TXT",
        key=f"file_upload_{st.session_state.form_key}",
    )
    if uploaded_file:
        st.success(
            f"✓ File loaded: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)"
        )

st.markdown("")
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    generate_btn = st.button(
        "⚡ Generate Test Cases",
        use_container_width=True,
        type="primary",
        disabled=not api_ok,
    )

if generate_btn:
    if not requirements_text.strip() and not uploaded_file:
        st.warning("Please paste requirements text or upload a file first.")
    elif not test_types:
        st.warning("Please select at least one test type.")
    else:
        with st.spinner("🤖 AI is analyzing requirements and generating test cases..."):
            try:
                if uploaded_file:
                    res = requests.post(
                        f"{API_BASE}/generate/file",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                        params={
                            "test_types": test_types,
                            "bdd_format": bdd_format,
                            "max_test_cases_per_story": max_tc,
                        },
                        timeout=120,
                    )
                else:
                    res = requests.post(
                        f"{API_BASE}/generate",
                        json={
                            "requirements_text": requirements_text,
                            "test_types": test_types,
                            "bdd_format": bdd_format,
                            "max_test_cases_per_story": max_tc,
                        },
                        timeout=120,
                    )

                if res.status_code == 200:
                    result = res.json()
                    st.session_state.response_data = result
                    st.session_state.generated = True
                    local_storage.setItem("test_generator_results", json.dumps(result))
                    st.rerun()
                else:
                    st.error(f"API Error {res.status_code}: {res.text}")
            except requests.exceptions.Timeout:
                st.error(
                    "Request timed out. Try shorter requirements or fewer test cases."
                )
            except Exception as e:
                st.error(f"Error: {str(e)}")


# ── RESULTS ───────────────────────────────────────────────────
if st.session_state.generated and st.session_state.response_data:
    data = st.session_state.response_data
    st.markdown("---")

    c1, c2, c3, c4, c5 = st.columns(5)
    total_critical = sum(s["critical_count"] for s in data["test_suites"])
    total_edge = sum(s["edge_case_count"] for s in data["test_suites"])

    with c1:
        st.metric("📋 Total Test Cases", data["total_test_cases"])
    with c2:
        st.metric("📖 User Stories", data["total_user_stories"])
    with c3:
        st.metric("🔴 Critical Cases", total_critical)
    with c4:
        st.metric("⚠️ Edge Cases", total_edge)
    with c5:
        st.metric("📁 Suites", len(data["test_suites"]))

    st.info(f"📄 **Summary:** {data['requirements_summary']}")
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["🧪 Test Cases", "📖 User Stories", "📥 Export"])

    with tab1:
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            filter_suite = st.selectbox(
                "Filter by Suite",
                ["All Suites"] + [s["suite_name"] for s in data["test_suites"]],
            )
        with fc2:
            filter_priority = st.selectbox(
                "Filter by Priority", ["All", "critical", "high", "medium", "low"]
            )
        with fc3:
            filter_edge = st.selectbox(
                "Filter by Type", ["All", "Edge Cases Only", "Non-Edge Cases"]
            )

        for suite in data["test_suites"]:
            if filter_suite != "All Suites" and suite["suite_name"] != filter_suite:
                continue
            st.markdown(f"### 📁 {suite['suite_name']}")
            st.caption(
                f"Coverage: {', '.join(suite['coverage_areas'])} | {suite['total_count']} test cases | {suite['critical_count']} critical | {suite['edge_case_count']} edge cases"
            )
            for tc in suite["test_cases"]:
                if filter_priority != "All" and tc["priority"] != filter_priority:
                    continue
                if filter_edge == "Edge Cases Only" and not tc.get("is_edge_case"):
                    continue
                if filter_edge == "Non-Edge Cases" and tc.get("is_edge_case"):
                    continue
                render_tc_card(tc)

    with tab2:
        for us in data["user_stories"]:
            with st.expander(f"**{us['id']}** — {us['title']}"):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"*{us['description']}*")
                with col_b:
                    st.markdown(
                        f'<span style="background:#2d3250;color:#a0aec0;padding:3px 10px;border-radius:8px;font-size:12px">{us["feature_area"]}</span>',
                        unsafe_allow_html=True,
                    )
                st.markdown("**Acceptance Criteria**")
                for c in us["acceptance_criteria"]:
                    st.markdown(f"- {c}")

    with tab3:
        st.markdown("### 📥 Export Test Cases")
        e1, e2, e3 = st.columns(3)

        for col, label, icon, fname, mime, endpoint in [
            (
                e1,
                "Excel",
                "📊",
                "test_cases.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "excel",
            ),
            (e2, "CSV", "📄", "test_cases.csv", "text/csv", "csv"),
            (e3, "JSON", "🔧", "test_cases.json", "application/json", "json"),
        ]:
            with col:
                st.markdown(f"#### {icon} {label}")
                try:
                    res = requests.get(f"{API_BASE}/export/{endpoint}", timeout=30)
                    if res.status_code == 200:
                        st.download_button(
                            f"⬇️ Download {label}",
                            data=res.content,
                            file_name=fname,
                            mime=mime,
                            use_container_width=True,
                        )
                except Exception:
                    st.error("Export failed")

        st.markdown("---")
        st.markdown("#### 👁️ Preview")
        rows = [
            {
                "ID": tc["id"],
                "Title": tc["title"],
                "Type": tc["test_type"],
                "Priority": tc["priority"],
                "Edge": "✅" if tc.get("is_edge_case") else "—",
                "Suite": suite["suite_name"],
            }
            for suite in data["test_suites"]
            for tc in suite["test_cases"]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
