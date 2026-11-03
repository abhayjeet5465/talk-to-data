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
import time
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
    (":material/show_chart:", "Show the main trend over time"),
    (":material/leaderboard:", "Top 5 categories by total value"),
    (":material/compare_arrows:", "Compare the groups side by side"),
    (":material/summarize:", "Give me a summary of the data"),
]

# ---------------------------------------------------------------------------
# Design tokens + component styles (see docs/DESIGN_SYSTEM.md)
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

      :root {
        /* Obsidian side panel */
        --tt-obsidian: #0a0a0b;
        --tt-obsidian-line: #232327;
        --tt-on-obsidian: #e7e7ea;
        --tt-on-obsidian-2: #8d8d96;
        /* Silver chrome */
        --tt-chrome: linear-gradient(135deg, #fbfbfc 0%, #d9dadd 28%, #9c9da3 50%, #e9e9ec 68%, #b4b5ba 100%);
        --tt-silver: #c3c4c9;
        /* White main, black ink */
        --tt-ink: #0a0a0b;
        --tt-ink-2: #52525b;
        --tt-ink-3: #8b8b94;
        --tt-surface: #ffffff;
        --tt-surface-2: #f7f7f8;
        --tt-border: #e6e6ea;
        --tt-radius: 12px;
        --tt-radius-lg: 18px;
        --tt-shadow: 0 1px 2px rgba(10,10,11,0.04), 0 4px 16px rgba(10,10,11,0.05);
        --tt-space-1: 4px; --tt-space-2: 8px; --tt-space-3: 12px; --tt-space-4: 16px; --tt-space-6: 24px;
      }

      html, body, [class*="css"], .stMarkdown, .stChatMessage, button, input, textarea {
        font-family: 'Inter', system-ui, sans-serif;
      }

      /* Keep the header (it holds the sidebar toggle) but make it quiet */
      #MainMenu, footer { visibility: hidden; }
      [data-testid="stHeader"] { background: transparent; }
      .block-container { max-width: 980px; padding-top: 2.2rem; padding-bottom: 7rem; }

      /* ── Obsidian side panel with a chrome sheen ─────────────────────── */
      [data-testid="stSidebar"] {
        background:
          radial-gradient(90% 32% at 105% -4%, rgba(255,255,255,0.20) 0%, rgba(255,255,255,0.05) 38%, transparent 60%),
          radial-gradient(70% 22% at -10% 102%, rgba(255,255,255,0.10) 0%, transparent 60%),
          linear-gradient(180deg, #121214 0%, var(--tt-obsidian) 55%, #050506 100%);
        border-right: 1px solid var(--tt-obsidian-line);
      }
      [data-testid="stSidebar"] hr { border-color: var(--tt-obsidian-line); }
      [data-testid="stSidebar"] .stButton button,
      [data-testid="stSidebar"] .stButton button > div { justify-content: flex-start; text-align: left; }
      [data-testid="stSidebar"] .stButton button p {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.9rem;
      }
      /* New chat: polished chrome */
      [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
        background: var(--tt-chrome); color: var(--tt-ink); border: 1px solid rgba(255,255,255,0.7);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 6px 18px rgba(0,0,0,0.45);
        border-radius: 12px; min-height: 44px;
      }
      [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] p,
      [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] span { font-weight: 650; color: var(--tt-ink); }
      [data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover { filter: brightness(1.06); }
      /* Chat list */
      [data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"] { color: var(--tt-on-obsidian); padding: 6px 10px; border-radius: 10px; }
      [data-testid="stSidebar"] button[data-testid="stBaseButton-tertiary"]:hover { background: rgba(255,255,255,0.06); color: #fff; }
      [data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
        background: rgba(255,255,255,0.07); color: #fff; border: 1px solid rgba(195,196,201,0.28); border-radius: 10px;
      }
      [data-testid="stSidebar"] [data-testid="stPopover"] button {
        background: transparent; color: var(--tt-on-obsidian); border: 1px solid var(--tt-obsidian-line); border-radius: 10px;
      }
      [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--tt-on-obsidian-2); }

      .tt-brand { display: flex; align-items: center; gap: 12px; padding: 2px 0 18px; }
      .tt-brand-name { font-weight: 700; font-size: 1.12rem; color: #fff; line-height: 1.1; }
      .tt-brand-sub { font-size: 0.75rem; color: var(--tt-on-obsidian-2); margin-top: 3px; }
      .tt-section { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
                    color: var(--tt-ink-3); margin: var(--tt-space-4) 0 var(--tt-space-1); }
      [data-testid="stSidebar"] .tt-section { color: var(--tt-on-obsidian-2); }
      .tt-when { color: var(--tt-on-obsidian-2); font-size: 0.72rem; text-align: right; white-space: nowrap; }

      /* ── White main: hero ────────────────────────────────────────────── */
      .tt-hero { text-align: center; padding: 1rem 0 1.6rem; }
      .tt-pill { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px;
                 border: 1px solid var(--tt-border); background: var(--tt-surface-2); font-size: 0.82rem;
                 font-weight: 600; color: var(--tt-ink); box-shadow: inset 0 1px 0 #fff; }
      .tt-hero .tt-h1 { font-size: 3.4rem; font-weight: 800; letter-spacing: -0.035em;
                        color: var(--tt-ink); margin: 18px 0 6px; line-height: 1.1; }
      .tt-underline { position: relative; display: inline-block; }
      .tt-underline svg { position: absolute; left: 0; bottom: -12px; width: 100%; height: 16px; }
      .tt-hero p { color: var(--tt-ink-2); font-size: 1.05rem; line-height: 1.6; max-width: 600px; margin: 22px auto 0; }

      /* Upload zone: dashed silver frame, black pill button */
      [data-testid="stFileUploaderDropzone"] {
        border: 1.5px dashed #c7c8cd; border-radius: var(--tt-radius-lg); background: #fcfcfd;
        padding: 2.2rem 1.5rem; flex-direction: column; align-items: center; justify-content: center; gap: 14px; text-align: center;
      }
      [data-testid="stFileUploaderDropzone"] button {
        background: var(--tt-ink); color: #fff; border: 0; border-radius: 999px; padding: 0.55rem 1.5rem; font-weight: 600;
        box-shadow: 0 4px 14px rgba(10,10,11,0.18);
      }
      [data-testid="stFileUploaderDropzone"] button:hover { background: #26262a; color: #fff; }

      /* Suggestion cards */
      [class*="st-key-starter_"] button {
        background: var(--tt-surface); border: 1px solid var(--tt-border); border-radius: var(--tt-radius);
        min-height: 56px; box-shadow: var(--tt-shadow); color: var(--tt-ink);
      }
      [class*="st-key-starter_"] button:hover:enabled { border-color: #a9aab0; color: var(--tt-ink); }
      [class*="st-key-starter_"] button p,
      [class*="st-key-starter_"] button [data-testid="stMarkdownContainer"] {
        font-weight: 600; font-size: 0.86rem; white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.35;
      }

      /* Chat input: floating card, black send */
      [data-testid="stChatInput"] { border-radius: 16px; box-shadow: var(--tt-shadow); }
      [data-testid="stChatInputSubmitButton"] { background: var(--tt-ink) !important; color: #fff !important; border-radius: 10px; }
      [data-testid="stChatInputSubmitButton"]:disabled { background: #d4d4d8 !important; }

      /* Chat title + data chips */
      .tt-title { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.01em; color: var(--tt-ink); margin: 0 0 6px; }
      .tt-chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--tt-border);
                 background: var(--tt-surface-2); border-radius: 999px; padding: 4px 11px; margin: 0 6px 6px 0;
                 font-size: 0.8rem; color: var(--tt-ink-2); }
      .tt-chip b { color: var(--tt-ink); font-weight: 600; }

      /* Messages + answers */
      [data-testid="stChatMessageAvatarCustom"] { background: var(--tt-ink); border: 0; }
      [data-testid="stChatMessageAvatarCustom"] * { color: #fff !important; fill: #fff; }
      .tt-meta { color: var(--tt-ink-3); font-size: 0.8rem; margin-top: var(--tt-space-1); }
      [data-testid="stMetric"] { background: var(--tt-surface-2); border: 1px solid var(--tt-border);
                                  border-radius: var(--tt-radius); padding: var(--tt-space-3) var(--tt-space-4); }
      [data-testid="stExpander"] details { border-radius: var(--tt-radius); border-color: var(--tt-border); }
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
        "created": time.time(),
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


def _ago(ts: float) -> str:
    secs = time.time() - ts
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return time.strftime("%b %d", time.localtime(ts))


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
        if f != f:  # NaN: the query matched nothing
            return "No data"
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
          <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
            <defs>
              <linearGradient id="tt-chrome" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#fbfbfc"/><stop offset="0.45" stop-color="#9c9da3"/>
                <stop offset="0.7" stop-color="#e9e9ec"/><stop offset="1" stop-color="#b4b5ba"/>
              </linearGradient>
            </defs>
            <rect x="3" y="17" width="7" height="14" rx="2" fill="url(#tt-chrome)"/>
            <rect x="13.5" y="10" width="7" height="21" rx="2" fill="url(#tt-chrome)"/>
            <rect x="24" y="3" width="7" height="28" rx="2" fill="url(#tt-chrome)"/>
          </svg>
          <div><div class="tt-brand-name">Talk to Data</div><div class="tt-brand-sub">AI Data Analysis</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("New chat", icon=":material/edit_square:", type="primary", width="stretch"):
        if not _is_blank(chat):
            _new_chat()
        st.rerun()

    st.markdown('<div class="tt-section">Recent chats</div>', unsafe_allow_html=True)
    for chat_id in reversed(list(st.session_state.chats)):
        c = st.session_state.chats[chat_id]
        is_active = chat_id == st.session_state.active_chat
        name_col, when_col = st.columns([4, 1.3], gap="small", vertical_alignment="center")
        with name_col:
            clicked = st.button(
                c["title"],
                key=f"open_{chat_id}",
                type="secondary" if is_active else "tertiary",
                icon=":material/chat_bubble_outline:",
                width="stretch",
            )
        with when_col:
            st.markdown(f'<div class="tt-when">{_ago(c["created"])}</div>', unsafe_allow_html=True)
        if clicked and not is_active:
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


def _render_answer(result: AnswerResult, key: str) -> None:
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
            result.chart.update_layout(title_text="", margin_t=12)
            st.plotly_chart(result.chart, width="stretch", key=key)
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
        <div class="tt-hero">
          <span class="tt-pill">✦ AI Data Analyst</span>
          <div class="tt-h1">Talk to <span class="tt-underline">Your Data
            <svg viewBox="0 0 300 16" preserveAspectRatio="none" aria-hidden="true">
              <defs><linearGradient id="tt-swoosh" x1="0" x2="1">
                <stop offset="0" stop-color="#0a0a0b" stop-opacity="0.05"/>
                <stop offset="0.5" stop-color="#8e8f95"/>
                <stop offset="1" stop-color="#0a0a0b" stop-opacity="0.05"/>
              </linearGradient></defs>
              <path d="M4 11 C 80 3, 210 3, 296 9" stroke="url(#tt-swoosh)" stroke-width="4" fill="none" stroke-linecap="round"/>
            </svg></span></div>
          <p>Upload your data, ask questions in plain English, and get instant insights,
             charts and the exact SQL behind every answer.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _uploader("Upload your data to get started · CSV or Excel · up to 3 files")
else:
    st.markdown(f'<p class="tt-title">{html.escape(chat["title"])}</p>', unsafe_allow_html=True)
    if has_data:
        _data_panel()
    else:
        st.caption("This chat has no data. Upload a file to keep asking.")
        _uploader("Upload data for this chat")

for i, (q, result) in enumerate(chat["history"]):
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(_md_safe(q))
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        _render_answer(result, f"chart_{st.session_state.active_chat}_{i}")

pending = None
if not chat["history"]:
    st.markdown('<div class="tt-section">Try asking something like</div>', unsafe_allow_html=True)
    for col, (icon, suggestion) in zip(st.columns(len(STARTER_QUESTIONS)), STARTER_QUESTIONS):
        with col:
            if st.button(suggestion, key=f"starter_{suggestion}", icon=icon, width="stretch",
                         disabled=not has_data, help=None if has_data else "Upload a file first"):
                pending = suggestion

typed = st.chat_input(
    "Ask a question about your data…" if has_data else "Upload a file to start asking",
    disabled=not has_data,
)
question = (typed or pending or "").strip()

if question:
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(_md_safe(question))
    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        with st.spinner("Analysing…"):
            result = _ask(chat, question)
    chat["history"].append((question, result))
    if chat["title"] == "New chat":
        chat["title"] = question[:48] + ("…" if len(question) > 48 else "")
    st.rerun()
