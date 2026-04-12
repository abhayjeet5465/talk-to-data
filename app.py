

"""
app.py — Streamlit frontend for Talk to Data.
"""
from __future__ import annotations
import streamlit as st

st.set_page_config(
    page_title="Talk to Data | NatWest",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config import validate_config
from src.orchestrator import AnswerResult, run_query, run_query_multi
from src.schema_extractor import SchemaExtractionError, build_unified_schema, extract_schema
from src.sql_executor import ExecutionError, load_dataframe, load_multiple_dataframes

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call in the file
# ---------------------------------------------------------------------------

# st.set_page_config(
#     page_title="Talk to Data | NatWest",
#     page_icon="📊",
#     layout="wide",
#     initial_sidebar_state="expanded",
# )

# ---------------------------------------------------------------------------
# Custom CSS — NatWest enterprise styling
#
# Injects Inter font, removes Streamlit chrome (menu/footer/header),
# and adds card-based layouts with the NatWest brand colours.
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      /* ── Typography ──────────────────────────────────────────────── */
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
      html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

      /* ── Remove default Streamlit chrome ─────────────────────────── */
      #MainMenu  { visibility: hidden; }
      footer     { visibility: hidden; }
      header     { visibility: hidden; }

      /* ── NatWest sidebar gradient ─────────────────────────────────── */
      [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #401664 0%, #1a0a2e 100%);
      }
      [data-testid="stSidebar"] * { color: #f0e8ff !important; }
      [data-testid="stSidebar"] .stButton > button {
        background: rgba(238,32,51,0.2);
        border: 1px solid #EE2033;
        color: #F78E99 !important;
        border-radius: 8px;
      }
      
      /* ── File uploader dropzone fix ─────────────────────────────── */
      [data-testid="stFileUploaderDropzone"] * {
        color: #401664 !important;
      }

      /* ── Answer card ──────────────────────────────────────────────── */
      .answer-card {
        background: rgba(30, 20, 50, 0.85);
        color: #f0e8ff;
        border-radius: 12px;
        border-left: 4px solid #EE2033;
        padding: 1.2rem 1.5rem;
        margin: 0.5rem 0 1rem 0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
      }

      /* ── Question badge ───────────────────────────────────────────── */
      .question-badge {
        display: inline-block;
        background: rgba(238,32,51,0.12);
        border: 1px solid rgba(238,32,51,0.4);
        border-radius: 20px;
        padding: 0.25rem 0.9rem;
        font-size: 0.85rem;
        font-weight: 600;
        color: #F78E99;
        margin-bottom: 0.6rem;
      }

      /* ── Self-corrected notice ────────────────────────────────────── */
      .self-corrected {
        font-size: 0.78rem;
        color: #F78E99;
        opacity: 0.75;
        margin-top: 0.3rem;
      }

      /* ── Main title ───────────────────────────────────────────────── */
      h1 { font-size: 2rem !important; font-weight: 700 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

if "schema_info" not in st.session_state:
    st.session_state.schema_info = None      # dict from extract_schema() — single-file
if "conn" not in st.session_state:
    st.session_state.conn = None             # duckdb.DuckDBPyConnection
if "history" not in st.session_state:
    st.session_state.history = []            # list of (question, AnswerResult)
if "clarification_context" not in st.session_state:
    st.session_state.clarification_context = None
# Multi-file state
if "datasets" not in st.session_state:
    st.session_state.datasets = {}           # table_name -> schema_info dict
if "unified_schema" not in st.session_state:
    st.session_state.unified_schema = ""

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    # NatWest logo (inline SVG cube — no external request needed)
    st.markdown(
        """
        <div style="text-align:center; padding: 1rem 0 0.5rem 0;">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="4" width="18" height="18" rx="3" fill="#EE2033"/>
            <rect x="26" y="4" width="18" height="18" rx="3" fill="#F78E99"/>
            <rect x="4" y="26" width="18" height="18" rx="3" fill="#F78E99"/>
            <rect x="26" y="26" width="18" height="18" rx="3" fill="#C20000"/>
          </svg>
          <div style="font-size:1.1rem; font-weight:700; margin-top:0.3rem;">Talk to Data</div>
          <div style="font-size:0.75rem; opacity:0.7;">NatWest Code for Purpose 2026</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Config warnings ────────────────────────────────────────────────────
    warnings = validate_config()
    for w in warnings:
        st.warning(w)

    # ── File uploader ──────────────────────────────────────────────────────
    # ── File uploader — accepts up to 3 files ─────────────────────────────
    st.markdown("**1. Upload your dataset(s)**")
    uploaded_files = st.file_uploader(
        "CSV or Excel files (max 3)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        help="Upload up to 3 files. Your data never leaves your session.",
    )

    if uploaded_files:
        # Limit to 3 files
        if len(uploaded_files) > 3:
            st.warning("Maximum 3 files allowed. Only the first 3 will be used.")
            uploaded_files = uploaded_files[:3]

        # Detect which files were removed since last run
        from src.config import slugify_table_name
        current_names = {slugify_table_name(f.name) for f in uploaded_files}
        stale_keys = set(st.session_state.datasets.keys()) - current_names
        if stale_keys:
            for k in stale_keys:
                del st.session_state.datasets[k]
            st.session_state.history = []

        # Process only newly added files (delta processing)
        for uf in uploaded_files:
            table_name = slugify_table_name(uf.name)
            if table_name not in st.session_state.datasets:
                with st.spinner(f"Reading {uf.name}…"):
                    try:
                        info = extract_schema(uf)
                        st.session_state.datasets[table_name] = info
                        st.session_state.history = []  # reset chat on new file
                        st.session_state.clarification_context = None
                        st.success(f"✅ Loaded **{uf.name}**")
                    except SchemaExtractionError as exc:
                        st.error(f"Could not read {uf.name}: {exc}")

        # Rebuild unified schema and DuckDB connection from all loaded datasets
        if st.session_state.datasets:
            st.session_state.unified_schema = build_unified_schema(st.session_state.datasets)
            try:
                if len(st.session_state.datasets) == 1:
                    # Single-file: use existing load_dataframe path
                    single_info = next(iter(st.session_state.datasets.values()))
                    st.session_state.conn = load_dataframe(single_info["df"])
                    st.session_state.schema_info = single_info
                else:
                    # Multi-file: register all DataFrames
                    st.session_state.conn = load_multiple_dataframes(st.session_state.datasets)
                    st.session_state.schema_info = next(iter(st.session_state.datasets.values()))
            except ExecutionError as exc:
                st.error(f"Could not load data: {exc}")
    elif not uploaded_files and st.session_state.datasets:
        # User cleared all files
        st.session_state.datasets = {}
        st.session_state.unified_schema = ""
        st.session_state.schema_info = None
        st.session_state.conn = None
        st.session_state.history = []

    # ── Dataset info panel ────────────────────────────────────────────────
    if st.session_state.datasets:
        st.divider()
        st.markdown("**Loaded datasets**")
        for tname, info in st.session_state.datasets.items():
            st.caption(f"📄 `{tname}` — {info['row_count']:,} rows · {info['col_count']} cols")
            with st.expander(f"Columns in {info['filename']}", expanded=False):
                for col, dtype in info["column_types"].items():
                    st.markdown(f"- `{col}` — {dtype}")

    st.divider()
    st.caption("🔒 Privacy: only column names and sample values are sent to the AI. Your full data stays local.")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.markdown("## 📊 Talk to Data")
st.caption("Ask plain-English questions about any dataset — instant, trustworthy answers.")

if st.session_state.schema_info is None:
    st.info("👈 Upload a CSV or Excel file in the sidebar to get started.")
    st.stop()

# ── Sample questions ───────────────────────────────────────────────────────
with st.expander("💡 Example questions (click to expand)", expanded=False):
    info = st.session_state.schema_info
    st.markdown(
        "- Why did revenue drop last month?\n"
        "- Compare performance across regions.\n"
        "- What makes up total sales?\n"
        "- Give me a weekly summary of key metrics.\n"
        f"- Show the breakdown of values in {info['filename']}."
    )

st.divider()

# ---------------------------------------------------------------------------
# Process a question and store the result in history
# ---------------------------------------------------------------------------

def _run_and_store(q: str) -> None:
    """Run the full pipeline and store the result in history."""
    is_multi = len(st.session_state.datasets) > 1

    with st.status("🔍 Analysing your question...", expanded=True) as status:
        st.write("Reading dataset schema and column structure...")
        if is_multi:
            st.write("Planning JOIN across multiple files...")
        st.write("Translating natural language into an optimised DuckDB query...")
        st.write("Executing calculations locally — your data never leaves this session...")
        st.write("Synthesising results into a plain-English explanation...")

        if is_multi:
            result: AnswerResult = run_query_multi(
                question=q,
                unified_schema=st.session_state.unified_schema,
                conn=st.session_state.conn,
                datasets=st.session_state.datasets,
            )
        else:
            info = st.session_state.schema_info
            result: AnswerResult = run_query(
                question=q,
                schema_str=info["schema_str"],
                conn=st.session_state.conn,
                filename=info["filename"],
            )

        if result.is_ambiguous:
            status.update(label="🤔 Clarification needed", state="error", expanded=False)
            st.session_state.clarification_context = (q, result.clarification_needed)
            st.rerun()
            return

        if result.error:
            status.update(label="❌ Could not complete analysis", state="error", expanded=False)
        else:
            status.update(label="✅ Analysis complete!", state="complete", expanded=False)

    st.session_state.history.append((q, result))

# ── Clarification flow — handles ambiguous questions ──────────────────────
# Shown inline above the chat input. History stays visible below.
if st.session_state.clarification_context:
    original_q, clarification_msg = st.session_state.clarification_context
    st.warning(f"🤔 **Clarification needed:** {clarification_msg}")
    st.caption(f"Original question: *{original_q}*")
    refined = st.text_input(
        "Please refine your question to include the missing detail:",
        key="clarification_input",
        placeholder="e.g. Show top products by total revenue.",
    )
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Ask", key="ask_clarification"):
            if refined.strip():
                st.session_state.clarification_context = None
                _run_and_store(refined.strip())
                # Rerun immediately so the new answer renders in the history section
                st.rerun()
    with col2:
        if st.button("Cancel", key="cancel_clarification"):
            st.session_state.clarification_context = None
            st.rerun()
    # NOTE: No st.stop() here — old chat history continues to display below.

# ── Question input ─────────────────────────────────────────────────────────
st.markdown("**2. Ask your question**")
question = st.chat_input("e.g. Which region had the highest revenue last month?")


# ── Run the pipeline when the user submits a question ─────────────────────
if question:
    _run_and_store(question)

# ---------------------------------------------------------------------------
# Display history — most recent answer shown first
# ---------------------------------------------------------------------------

for q, result in reversed(st.session_state.history):

    # Question badge
    st.markdown(f'<div class="question-badge">❓ {q}</div>', unsafe_allow_html=True)

    if result.error:
        st.error(result.error)

    else:
        # ── Answer card ────────────────────────────────────────────────
        answer_html = (
            f'<div class="answer-card">'
            f'<div style="font-size:1rem; line-height:1.6;">{result.answer}</div>'
        )
        if result.self_corrected:
            answer_html += (
                '<div class="self-corrected">⚡ Answer was auto-corrected by the AI</div>'
            )
        answer_html += "</div>"
        st.markdown(answer_html, unsafe_allow_html=True)

        # ── Chart or summary metrics ────────────────────────────────────
        if result.chart is not None:
            st.plotly_chart(result.chart, use_container_width=True)

        elif result.row_count == 1 and result.col_count > 1:
            # Summary result (e.g. "summarise data") — 1 row, many numeric columns.
            # Show each value as a labelled metric tile in a horizontal grid.
            if result.result_df is not None:
                row = result.result_df.iloc[0]
                cols_to_show = result.result_df.columns.tolist()
                metric_cols = st.columns(min(len(cols_to_show), 4))
                for i, col_name in enumerate(cols_to_show):
                    raw_val = row[col_name]
                    # Format numbers nicely: integers without decimals, floats to 2dp
                    try:
                        val = f"{int(raw_val):,}" if float(raw_val) == int(float(raw_val)) else f"{float(raw_val):,.2f}"
                    except (ValueError, TypeError):
                        val = str(raw_val)
                    metric_cols[i % 4].metric(label=col_name.replace("_", " ").title(), value=val)

        elif result.row_count == 1 and result.col_count == 1:
            # True single value — show as a big metric card extracted from the raw data
            val = "—"
            if result.result_df is not None and not result.result_df.empty:
                raw_val = result.result_df.iloc[0, 0]
                try:
                    val = f"{int(raw_val):,}" if float(raw_val) == int(float(raw_val)) else f"{float(raw_val):,.2f}"
                except (ValueError, TypeError):
                    val = str(raw_val)
            st.metric(label="Result", value=val)

        # ── Source info ────────────────────────────────────────────────
        if result.source_info:
            note = " (aggregated summary)" if result.row_count == 1 and result.col_count > 1 else ""
            st.caption(f"📁 {result.source_info}{note}")

    # ── XAI "How was this calculated?" expander ────────────────────────
    # This is the Trust pillar — mandatory for NatWest submission.
    # Shows the SQL, columns used, assumptions made, and the actual data table.
    if result.sql:
        with st.expander("🔬 How was this calculated? (Source transparency)"):
            left, right = st.columns([1, 2])

            with left:
                if result.columns_used:
                    st.markdown("**📊 Columns used in this answer**")
                    for col in result.columns_used:
                        st.markdown(f"- `{col}`")
                else:
                    st.markdown("*Column data not available*")

            with right:
                st.markdown("**📋 SQL query executed locally**")
                st.code(result.sql, language="sql")

            if result.assumptions:
                st.info(f"💡 **Assumption made:** {result.assumptions}")

            # Show the actual result data table so users can verify the raw numbers
            if result.result_df is not None and not result.result_df.empty:
                st.markdown("**🔢 Raw query result (exact numbers)**")
                st.dataframe(result.result_df, use_container_width=True, hide_index=True)

    # ── Data Lineage expander (multi-file only) ────────────────────────
    if len(st.session_state.datasets) > 1 and result.sql and "JOIN" in result.sql.upper():
        with st.expander("📂 Data Lineage — files joined in this answer"):
            st.markdown("This answer combined data from:")
            for tname, info in st.session_state.datasets.items():
                st.markdown(f"- **`{tname}`** → `{info['filename']}`")

    st.divider()

# ── Empty state — file loaded but no questions yet ─────────────────────────
if st.session_state.schema_info and not st.session_state.history:
    st.markdown(
        '<div style="text-align:center; opacity:0.5; padding: 2rem 0;">'
        "Type a question above to get started ↑"
        "</div>",
        unsafe_allow_html=True,
    )