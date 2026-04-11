from __future__ import annotations

"""
app.py — Streamlit frontend for Talk to Data.

UI only — no business logic lives here. All data processing is
delegated to src/orchestrator.py and the pipeline modules.

Layout:
  Sidebar  — file uploader + dataset info panel + config warnings
  Main     — chat-style question input
             answer text
             Plotly chart (if applicable)
             collapsible SQL panel (NatWest Trust pillar — mandatory)

Run with:
    streamlit run app.py
"""

import streamlit as st

from src.config import validate_config
from src.orchestrator import AnswerResult, run_query
from src.schema_extractor import SchemaExtractionError, extract_schema
from src.sql_executor import ExecutionError, load_dataframe

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Talk to Data",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "schema_info" not in st.session_state:
    st.session_state.schema_info = None      # dict from extract_schema()
if "conn" not in st.session_state:
    st.session_state.conn = None             # duckdb.DuckDBPyConnection
if "history" not in st.session_state:
    st.session_state.history = []            # list of (question, AnswerResult)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Talk to Data")
    st.caption("NatWest Code for Purpose 2026")
    st.divider()

    # ── Config warnings ────────────────────────────────────────────────────
    warnings = validate_config()
    if warnings:
        for w in warnings:
            st.warning(w)

    # ── File uploader ──────────────────────────────────────────────────────
    st.subheader("1. Upload your data")
    uploaded_file = st.file_uploader(
        "CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Your data never leaves your session — only column names are sent to the AI.",
    )

    if uploaded_file is not None:
        # Only re-process if a new file was uploaded
        current_name = getattr(st.session_state.schema_info, "__file__", None)
        if (
            st.session_state.schema_info is None
            or st.session_state.schema_info.get("filename") != uploaded_file.name
        ):
            with st.spinner("Reading file…"):
                try:
                    schema_info = extract_schema(uploaded_file)
                    conn = load_dataframe(schema_info["df"])
                    st.session_state.schema_info = schema_info
                    st.session_state.conn = conn
                    st.session_state.history = []   # reset chat on new file
                    st.success(f"✅ Loaded **{uploaded_file.name}**")
                except SchemaExtractionError as exc:
                    st.error(f"Could not read file: {exc}")
                    st.session_state.schema_info = None
                    st.session_state.conn = None
                except ExecutionError as exc:
                    st.error(f"Could not load data: {exc}")

    # ── Dataset info panel ─────────────────────────────────────────────────
    if st.session_state.schema_info:
        info = st.session_state.schema_info
        st.divider()
        st.subheader("Dataset info")
        st.markdown(f"**File:** {info['filename']}")
        st.markdown(f"**Rows:** {info['row_count']:,}  |  **Columns:** {info['col_count']}")
        with st.expander("Column types"):
            for col, dtype in info["column_types"].items():
                st.markdown(f"- `{col}` — {dtype}")

    st.divider()
    st.caption("Privacy: only column names and 3 sample rows are sent to the AI. Your data stays local.")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.header("Ask a question about your data")

if st.session_state.schema_info is None:
    st.info("👈 Upload a CSV or Excel file in the sidebar to get started.")
    st.stop()

# ── Sample questions ───────────────────────────────────────────────────────
with st.expander("💡 Example questions", expanded=False):
    info = st.session_state.schema_info
    st.markdown(
        "- Which row has the highest value?\n"
        "- Show me the total by category.\n"
        "- Compare values across groups.\n"
        "- What is the average for each group?\n"
        f"- Summarise the {info['filename']} data."
    )

# ── Question input ─────────────────────────────────────────────────────────
st.subheader("2. Ask your question")
question = st.chat_input("e.g. Which region had the highest revenue last month?")

# ── Process question ───────────────────────────────────────────────────────
if question:
    info = st.session_state.schema_info

    with st.spinner("Thinking…"):
        result: AnswerResult = run_query(
            question=question,
            schema_str=info["schema_str"],
            conn=st.session_state.conn,
            filename=info["filename"],
        )

    # Store in history
    st.session_state.history.append((question, result))

# ── Display history (most recent first) ───────────────────────────────────
for q, result in reversed(st.session_state.history):
    with st.container():
        st.markdown(f"**You:** {q}")
        st.divider()

        if result.error:
            st.error(result.error)
        else:
            # Answer text
            st.markdown(f"**Answer:** {result.answer}")

            # Chart
            if result.chart is not None:
                st.plotly_chart(result.chart, use_container_width=True)
            elif result.row_count == 1 and result.col_count == 1:
                # Single metric card — display as big number
                st.metric(label="Result", value=result.answer.split()[0])

            # Source info
            if result.source_info:
                st.caption(f"📁 {result.source_info}")

        # Collapsible SQL panel — mandatory for NatWest Trust pillar
        if result.sql:
            with st.expander("🔍 SQL used (source transparency)"):
                st.code(result.sql, language="sql")

        st.divider()

# ── Empty state after file loaded but no questions yet ─────────────────────
if st.session_state.schema_info and not st.session_state.history:
    st.markdown("Type a question above to get started ↑")