"""
app.py — Streamlit frontend for Talk to Data.

Chat-style analysis workspace:
  - The sidebar lists chats. "New chat" starts a fresh one; the open chat
    can be renamed or deleted.
  - Each chat owns its uploaded files, DuckDB connection and history, so data
    uploaded in one chat is never visible to another.
  - Recent turns are passed to the pipeline as context, so follow-ups such as
    "what about the West?" or a reply to a clarifying question just work.

Chats live in this browser session only (nothing is persisted), which keeps
uploaded data private but means a page refresh starts over.
"""
from __future__ import annotations

import html
import uuid

import streamlit as st

st.set_page_config(
    page_title="Talk to Data",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config import slugify_table_name, validate_config
from src.orchestrator import AnswerResult, run_query, run_query_multi
from src.schema_extractor import SchemaExtractionError, build_unified_schema, extract_schema
from src.sql_executor import ExecutionError, load_dataframe, load_multiple_dataframes

MAX_FILES_PER_CHAT = 3
CONTEXT_TURNS = 4  # earlier turns sent with each question for follow-ups
STARTER_QUESTIONS = [
    "Give me a summary of the key numbers in this data",
    "What are the top 5 categories by total value?",
    "How has the main metric changed over time?",
]

# ---------------------------------------------------------------------------
# Design tokens + component styles (see docs/DESIGN_SYSTEM.md)
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      :root {
        --tt-ink: #18181b;          /* primary text */
        --tt-ink-2: #52525b;        /* secondary text */
        --tt-ink-3: #8b8b94;        /* muted text, captions */
        --tt-surface: #ffffff;      /* page */
        --tt-surface-2: #f6f6f8;    /* sidebar, subtle panels */
        --tt-border: #e4e4e7;
        --tt-accent: #2a78d6;
        --tt-accent-soft: #eaf2fc;
        --tt-radius: 10px;
        --tt-space-1: 4px; --tt-space-2: 8px; --tt-space-3: 12px; --tt-space-4: 16px; --tt-space-6: 24px;
      }

      html, body, [class*="css"], .stMarkdown, .stChatMessage { font-family: 'Inter', system-ui, sans-serif; }

      /* Chrome: keep the header (it holds the sidebar toggle) but make it quiet */
      #MainMenu, footer { visibility: hidden; }
      [data-testid="stHeader"] { background: transparent; }

      /* Readable chat column, like ChatGPT/Claude */
      .block-container { max-width: 880px; padding-top: 2.5rem; padding-bottom: 7rem; }

      /* Sidebar */
      [data-testid="stSidebar"] { background: var(--tt-surface-2); border-right: 1px solid var(--tt-border); }
      [data-testid="stSidebar"] .stButton button,
      [data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; text-align: left; }
      [data-testid="stSidebar"] .stButton button p {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.9rem;
      }
      .tt-brand { display: flex; align-items: center; gap: var(--tt-space-2);
                  font-weight: 700; font-size: 1.05rem; color: var(--tt-ink); padding: var(--tt-space-1) 0 var(--tt-space-3); }
      .tt-brand-mark { width: 26px; height: 26px; border-radius: 7px; background: var(--tt-ink);
                       display: grid; place-items: center; }
      .tt-section { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
                    color: var(--tt-ink-3); margin: var(--tt-space-4) 0 var(--tt-space-1); }

      /* Page title + data chips */
      .tt-title { font-size: 1.35rem; font-weight: 650; color: var(--tt-ink); margin: 0; }
      .tt-sub { color: var(--tt-ink-2); font-size: 0.92rem; margin: 2px 0 var(--tt-space-3); }
      .tt-chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--tt-border);
                 background: var(--tt-surface); border-radius: 999px; padding: 3px 10px; margin: 0 6px 6px 0;
                 font-size: 0.8rem; color: var(--tt-ink-2); }
      .tt-chip b { color: var(--tt-ink); font-weight: 600; }

      /* Empty state */
      .tt-empty { text-align: center; padding: 3rem 1rem 1.5rem; }
      .tt-empty h2 { font-size: 1.6rem; font-weight: 650; color: var(--tt-ink); margin-bottom: 0.4rem; }
      .tt-empty p { color: var(--tt-ink-2); margin: 0 auto; max-width: 520px; }

      /* Answer meta line */
      .tt-meta { color: var(--tt-ink-3); font-size: 0.8rem; margin-top: var(--tt-space-1); }

      /* Metrics */
      [data-testid="stMetric"] { background: var(--tt-surface-2); border: 1px solid var(--tt-border);
                                  border-radius: var(--tt-radius); padding: var(--tt-space-3) var(--tt-space-4); }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Chat state — every chat owns its data, connection and history
# ---------------------------------------------------------------------------


def _new_chat() -> None:
    chat_id = uuid.uuid4().hex[:8]
    st.session_state.chats[chat_id] = {
        "title": "New chat",
        "datasets": {},        # table_name -> schema_info
        "unified_schema": "",
        "conn": None,          # DuckDB connection for this chat only
        "history": [],         # list of (question, AnswerResult)
        "uploader_version": 0, # bumped to clear the uploader after ingest
    }
    st.session_state.active_chat = chat_id


if "chats" not in st.session_state:
    st.session_state.chats = {}
    _new_chat()

chat = st.session_state.chats[st.session_state.active_chat]


def _is_blank(c: dict) -> bool:
    return not c["datasets"] and not c["history"]


def _rebuild_connection(c: dict) -> None:
    """Re-register this chat's datasets in a fresh, locked-down DuckDB connection."""
    if not c["datasets"]:
        c["conn"], c["unified_schema"] = None, ""
        return
    c["unified_schema"] = build_unified_schema(c["datasets"])
    if len(c["datasets"]) == 1:
        c["conn"] = load_dataframe(next(iter(c["datasets"].values()))["df"])
    else:
        c["conn"] = load_multiple_dataframes(c["datasets"])


def _context(history: list) -> str:
    """Summarise recent turns so the model can resolve follow-up questions."""
    lines = []
    for q, r in history[-CONTEXT_TURNS:]:
        lines.append(f"User: {q}")
        if r.is_ambiguous:
            lines.append(f"Assistant asked for clarification: {r.clarification_needed}")
        elif r.error:
            lines.append("Assistant: could not answer that one.")
        else:
            lines.append(f"Assistant SQL: {r.sql}")
            lines.append(f"Assistant answer: {r.answer[:300]}")
    if not lines:
        return ""
    return (
        "Earlier in this conversation (use it only to resolve follow-ups, "
        "references like 'that' or 'the same', or answers to your clarifying question):\n"
        + "\n".join(lines)
    )


def _ask(c: dict, question: str) -> AnswerResult:
    context = _context(c["history"])
    if len(c["datasets"]) > 1:
        return run_query_multi(question, c["unified_schema"], c["conn"], c["datasets"], context=context)
    info = next(iter(c["datasets"].values()))
    return run_query(question, info["schema_str"], c["conn"], info["filename"], context=context)


def _fmt_number(raw) -> str:
    try:
        f = float(raw)
        return f"{int(f):,}" if f == int(f) else f"{f:,.2f}"
    except (ValueError, TypeError, OverflowError):
        return str(raw)


def _md_safe(text: str) -> str:
    """Stop '$' in currency values being rendered as LaTeX."""
    return text.replace("$", r"\$")


# ---------------------------------------------------------------------------
# Sidebar — brand, new chat, chat list, chat options
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="tt-brand">
          <span class="tt-brand-mark">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <rect x="1" y="7" width="3" height="6" rx="1" fill="#fff"/>
              <rect x="5.5" y="4" width="3" height="9" rx="1" fill="#fff"/>
              <rect x="10" y="1" width="3" height="12" rx="1" fill="#86b6ef"/>
            </svg>
          </span>
          Talk to Data
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("New chat", icon=":material/edit_square:", type="primary", width="stretch"):
        if not _is_blank(chat):
            _new_chat()
        st.rerun()

    st.markdown('<div class="tt-section">Chats</div>', unsafe_allow_html=True)
    for chat_id in reversed(list(st.session_state.chats)):
        c = st.session_state.chats[chat_id]
        is_active = chat_id == st.session_state.active_chat
        if st.button(
            c["title"],
            key=f"open_{chat_id}",
            type="secondary" if is_active else "tertiary",
            icon=":material/chat_bubble:" if is_active else None,
            width="stretch",
        ) and not is_active:
            st.session_state.active_chat = chat_id
            st.rerun()

    st.markdown('<div class="tt-section">This chat</div>', unsafe_allow_html=True)
    with st.popover("Rename or delete", icon=":material/more_horiz:", width="stretch"):
        new_title = st.text_input("Chat name", value=chat["title"], max_chars=60)
        if st.button("Save name", width="stretch") and new_title.strip():
            chat["title"] = new_title.strip()
            st.rerun()
        st.divider()
        if st.button("Delete chat", icon=":material/delete:", width="stretch"):
            del st.session_state.chats[st.session_state.active_chat]
            if st.session_state.chats:
                st.session_state.active_chat = next(reversed(list(st.session_state.chats)))
            else:
                _new_chat()
            st.rerun()

    for w in validate_config():
        st.warning(w)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        ":material/lock: Only column names, types and a few sample values are sent "
        "to the AI. Your full data stays in this session, inside this chat."
    )

# ---------------------------------------------------------------------------
# Data for this chat — upload, list, remove
# ---------------------------------------------------------------------------


def _uploader(label: str) -> None:
    """File picker scoped to the active chat. Only adds files; removal is explicit."""
    room = MAX_FILES_PER_CHAT - len(chat["datasets"])
    files = st.file_uploader(
        label,
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key=f"upload_{st.session_state.active_chat}_{chat['uploader_version']}",
        help=f"Up to {MAX_FILES_PER_CHAT} files per chat. Files stay in this chat only.",
        disabled=room <= 0,
    )
    if not files:
        return
    added = False
    for uf in files:
        table = slugify_table_name(uf.name)
        if table in chat["datasets"]:
            continue
        if len(chat["datasets"]) >= MAX_FILES_PER_CHAT:
            st.warning(f"Skipped {uf.name}: a chat can hold {MAX_FILES_PER_CHAT} files.")
            continue
        with st.spinner(f"Reading {uf.name}…"):
            try:
                chat["datasets"][table] = extract_schema(uf)
                added = True
            except SchemaExtractionError as exc:
                st.error(f"Could not read {uf.name}: {exc}")
    if added:
        try:
            _rebuild_connection(chat)
        except ExecutionError as exc:
            st.error(f"Could not load data: {exc}")
            return
        chat["uploader_version"] += 1  # clear the picker; data now lives on the chat
        st.rerun()


def _data_panel() -> None:
    chips = "".join(
        f'<span class="tt-chip">📄 <b>{html.escape(info["filename"])}</b> {info["row_count"]:,} rows · {info["col_count"]} cols</span>'
        for info in chat["datasets"].values()
    )
    st.markdown(chips, unsafe_allow_html=True)
    with st.expander(f"Data in this chat ({len(chat['datasets'])}/{MAX_FILES_PER_CHAT} files)"):
        for table, info in list(chat["datasets"].items()):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f"**{info['filename']}** · table `{table}`")
                st.caption(", ".join(f"{col} ({dtype})" for col, dtype in info["column_types"].items()))
            with right:
                if st.button("Remove", key=f"rm_{st.session_state.active_chat}_{table}"):
                    del chat["datasets"][table]
                    _rebuild_connection(chat)
                    st.rerun()
        if len(chat["datasets"]) < MAX_FILES_PER_CHAT:
            _uploader("Add another file to join with")


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------


def _render_answer(result: AnswerResult) -> None:
    if result.is_ambiguous:
        st.markdown(_md_safe(f"I need one detail to answer this precisely: {result.clarification_needed}"))
        st.caption("Reply below — I'll keep your original question in mind.")
        return
    if result.error:
        st.error(result.error, icon=":material/error:")
    else:
        st.markdown(_md_safe(result.answer))
        if result.self_corrected:
            st.caption(":material/auto_fix_high: The first query failed and was corrected automatically.")

        df = result.result_df
        if result.chart is not None:
            # The question sits right above, so the chart needs no title
            result.chart.update_layout(title_text=None, margin_t=12)
            st.plotly_chart(result.chart, width="stretch")
        elif df is not None and result.row_count == 1 and result.col_count == 1:
            st.metric(label=str(df.columns[0]).replace("_", " ").title(), value=_fmt_number(df.iloc[0, 0]))
        elif df is not None and result.row_count == 1:
            cols = st.columns(min(result.col_count, 4))
            for i, name in enumerate(df.columns):
                cols[i % 4].metric(label=str(name).replace("_", " ").title(), value=_fmt_number(df.iloc[0][name]))

        if result.source_info:
            st.markdown(f'<div class="tt-meta">{html.escape(result.source_info)}</div>', unsafe_allow_html=True)

    if result.sql:
        with st.expander("How this was calculated", icon=":material/manage_search:"):
            if result.columns_used:
                st.markdown("**Columns used:** " + ", ".join(f"`{c}`" for c in result.columns_used))
            st.code(result.sql, language="sql")
            if result.assumptions:
                st.info(_md_safe(f"Assumption: {result.assumptions}"))
            if result.result_df is not None and not result.result_df.empty:
                st.markdown("**Result rows**")
                st.dataframe(result.result_df, width="stretch", hide_index=True)
            if len(chat["datasets"]) > 1 and "JOIN" in result.sql.upper():
                st.markdown(
                    "**Files joined:** "
                    + ", ".join(f"`{t}` ← {i['filename']}" for t, i in chat["datasets"].items())
                )


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

has_data = bool(chat["datasets"])

if not has_data and not chat["history"]:
    st.markdown(
        """
        <div class="tt-empty">
          <h2>What would you like to analyse?</h2>
          <p>Upload up to three CSV or Excel files, then ask questions in plain English.
             You'll get an answer, a chart and the exact SQL behind it.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _uploader("Upload data for this chat")
else:
    st.markdown(f'<p class="tt-title">{html.escape(chat["title"])}</p>', unsafe_allow_html=True)
    if has_data:
        _data_panel()
    else:
        st.markdown('<p class="tt-sub">This chat has no data. Upload a file to keep asking.</p>', unsafe_allow_html=True)
        _uploader("Upload data for this chat")

for q, result in chat["history"]:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(_md_safe(q))
    with st.chat_message("assistant", avatar=":material/analytics:"):
        _render_answer(result)

pending = None
if has_data and not chat["history"]:
    st.markdown('<div class="tt-section">Try asking</div>', unsafe_allow_html=True)
    for i, suggestion in enumerate(STARTER_QUESTIONS):
        if st.button(suggestion, key=f"starter_{i}", type="tertiary", icon=":material/arrow_outward:"):
            pending = suggestion

typed = st.chat_input(
    "Ask a question about your data…" if has_data else "Upload a file to start asking",
    disabled=not has_data,
)
question = (typed or pending or "").strip()

if question:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(_md_safe(question))
    with st.chat_message("assistant", avatar=":material/analytics:"):
        with st.spinner("Analysing…"):
            result = _ask(chat, question)
    chat["history"].append((question, result))
    if chat["title"] == "New chat":
        chat["title"] = question[:48] + ("…" if len(question) > 48 else "")
    st.rerun()
