# REFERENCE.md — Talk to Data
## Complete Codebase Reference for AI Assistants & Developers

> **Purpose of this file:** Any AI assistant, new developer, or team member
> can read this single document and fully understand the project — what it is,
> what has been built, what remains, every file's role, all known conflicts,
> version constraints, and exact NatWest submission rules.
>
> **Hackathon:** NatWest Code for Purpose 2026 — India
> **Theme:** Theme 1 — Talk to Data: Seamless Self-Service Intelligence
> **GitHub:** https://github.com/abhayjeet5465/talk-to-data
> **License:** Apache 2.0 (mandatory — all dependencies must be compatible)
> **Last updated:** After Stage 2 completion (schema extractor + 12 passing tests)

---

## Table of Contents

1. [Project Mission](#1-project-mission)
2. [NatWest Requirements — Non-Negotiable Rules](#2-natwest-requirements)
3. [System Architecture](#3-system-architecture)
4. [Data Flow — Plain English](#4-data-flow)
5. [Current File Structure](#5-current-file-structure)
6. [Every File Explained](#6-every-file-explained)
7. [Technology Stack — Exact Versions](#7-technology-stack)
8. [Known Conflicts & Gotchas](#8-known-conflicts--gotchas)
9. [Free-Tier API Details](#9-free-tier-api-details)
10. [Build Progress — Stage by Stage](#10-build-progress)
11. [Stages Remaining](#11-stages-remaining)
12. [Coding Conventions](#12-coding-conventions)
13. [Git Rules — DCO Compliance](#13-git-rules)
14. [Environment Variables](#14-environment-variables)
15. [Running the Project](#15-running-the-project)
16. [Testing](#16-testing)
17. [Pre-Submission Checklist](#17-pre-submission-checklist)

---

## 1. Project Mission

**What it does:**
A web app where anyone — regardless of technical skill — uploads a CSV or
Excel file, types a plain-English question, and instantly receives a trusted,
sourced, visual answer. No SQL knowledge needed. No complicated tools.

**The problem it solves (directly from NatWest problem statement):**
- Too many steps to get answers from data
- Unclear terminology and lack of confidence in results
- Pressure to respond fast with no good tooling
- No transparency about where answers come from

**Three pillars every feature must satisfy:**

| Pillar | Meaning | How we satisfy it |
|--------|---------|------------------|
| Clarity | Non-experts can understand every answer | Plain English explanation, no jargon |
| Trust | Source transparency, consistent metrics | SQL shown to user, filename cited |
| Speed | Near-instant, minimal steps | Groq LPU inference, DuckDB in-memory |

**Four use cases the solution must cover:**
1. **Understand what changed** — "Why did revenue drop last month?"
2. **Compare** — "Region A vs Region B", "This week vs last week"
3. **Breakdown** — "What makes up total sales?"
4. **Summarize** — "Give me a weekly summary of customer metrics"

**Intended users:** Non-technical business users, analysts, team leads —
anyone who has data but cannot write SQL or use BI tools.

---

## 2. NatWest Requirements

These are hard rules from the submission guidelines. Violating any of them
risks disqualification.

### 2.1 Mandatory README sections
README.md must include ALL of:
- Overview (2–5 sentences: what, problem, who)
- Features (only working features — no planned features listed as done)
- Install and run instructions (step-by-step)
- Tech stack (languages, frameworks, databases, cloud, AI/ML)
- Usage examples (sample inputs/outputs, screenshots)
- Architecture notes (optional but strongly recommended)
- Limitations (honest — incomplete features must be labelled)

### 2.2 Codebase requirements
- All source files present and importable
- `requirements.txt` works with `pip install -r requirements.txt`
- `.env.example` lists all required env vars (no real keys)
- No single-file project — use proper folder structure
- No unused files, debug prints, or stray logs at submission

### 2.3 Feature honesty (critical — disqualification risk)
- Every feature listed in README must exist and be usable
- Partial features must say: "Basic version implemented; X not yet supported"
- Never claim work that has not been done

### 2.4 Code quality
- Descriptive variable/function/file names (no temp1, x2, data1)
- Docstrings on all public functions and classes
- Comments explaining WHY, not just WHAT
- No hardcoded API keys, passwords, or tokens anywhere
- Use environment variables for all secrets

### 2.5 Apache 2.0 + DCO compliance (mandatory)
- `LICENSE` file at root containing full Apache 2.0 text
- Every commit must be signed off: `git commit -s -m "message"`
  (This adds `Signed-off-by: Name <email>` to the commit)
- One email address for ALL commits throughout the hackathon
- Repository must stay PRIVATE during the hackathon
- No fake identities, no shared corporate GitHub accounts

### 2.6 Repository visibility
- Private during hackathon
- May be made public after submission and review

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER (Browser)                          │
│            Uploads CSV/Excel  |  Types question              │
└──────────────────┬────────────┴─────────────────────────────┘
                   │ HTTPS (Streamlit Community Cloud)
┌──────────────────▼──────────────────────────────────────────┐
│                  app.py  (Streamlit Frontend)                │
│  • File upload widget                                        │
│  • Chat input box                                            │
│  • Answer display (text + Plotly chart)                      │
│  • Collapsible SQL source panel                              │
└──────────────────┬──────────────────────────────────────────┘
                   │ Python function call (same process)
┌──────────────────▼──────────────────────────────────────────┐
│             src/orchestrator.py  (Pipeline Controller)       │
│                                                              │
│  Step 1: schema_extractor.py  ◄── uploaded file              │
│          • reads CSV/Excel via Pandas                        │
│          • infers column names + types                       │
│          • picks 3 sample rows                               │
│          • builds schema string for LLM                      │
│          • FULL DATA STAYS HERE — never sent to API          │
│                                                              │
│  Step 2: sql_executor.py  ◄── full DataFrame                 │
│          • loads DataFrame into DuckDB in-memory table       │
│          • table name is always: data                        │
│          • persists in Streamlit session_state               │
│                                                              │
│  Step 3: sql_generator.py  ◄── schema string + question      │
│          • LLM CALL #1 → Groq (primary)                     │
│          • sends: schema string + user question              │
│          • receives: SQL SELECT query string                 │
│                                                              │
│  Step 4: sql_executor.py  ◄── SQL string                     │
│          • safety validator (blocklist check)                │
│          • executes SQL against DuckDB                       │
│          • returns small result DataFrame                    │
│                                                              │
│  Step 5: answer_generator.py  ◄── result rows + question     │
│          • LLM CALL #2 → Groq (primary)                     │
│          • sends: question + result rows + filename          │
│          • receives: 2-3 sentence plain English explanation  │
│                                                              │
│  Step 6: chart_selector.py  ◄── result DataFrame            │
│          • rule-based chart type selection                   │
│          • renders Plotly Express figure                     │
└──────┬───────────────────────────────────────┬──────────────┘
       │ Groq API (primary)                    │ Gemini API (fallback)
       │ llama-3.3-70b-versatile               │ gemini-2.5-flash
       │ api.groq.com/openai/v1                │ generativelanguage.googleapis.com
       │ No credit card · Apache 2.0           │ No credit card · Apache 2.0
       └───────────────────────────────────────┘
```

### Privacy model
- The full dataset is loaded into DuckDB in Streamlit session state
- **Only schema metadata** (column names, types, 3 sample rows) is sent to LLM API
- **Only result rows** (small aggregated output, never raw data) go to LLM #2
- No raw user data ever reaches an external API
- SQL is validated before execution — LLM output is never trusted blindly

---

## 4. Data Flow

```
USER uploads sales_data.csv
        │
        ▼
schema_extractor.py reads file
  → columns: [date, region, product, revenue, units]
  → types:   [datetime, text, text, float, integer]
  → sample:  first 3 rows
  → schema_str built (this is all the LLM sees of the data)
        │
        ▼
DuckDB loads full DataFrame into in-memory table called 'data'
(full data stays here — never leaves)
        │
        ▼
USER types: "Why did revenue drop last month?"
        │
        ▼
LLM CALL #1 — sql_generator.py
  INPUT:  schema_str + user question
  OUTPUT: SELECT region, SUM(revenue) AS total
          FROM data
          WHERE date >= '2026-03-01' AND date < '2026-04-01'
          GROUP BY region ORDER BY total ASC
        │
        ▼
Safety validator — sql_executor.py
  Checks for: DROP, DELETE, INSERT, UPDATE, ALTER, CREATE,
              TRUNCATE, EXEC, EXECUTE, PRAGMA, ATTACH
  If unsafe → return error message to UI, do not execute
        │
        ▼
DuckDB executes query against in-memory table
  Result: [("South", 45000.0), ("North", 82000.0), ...]
        │
        ▼
LLM CALL #2 — answer_generator.py
  INPUT:  user question + result rows + filename
  OUTPUT: "Revenue fell 11% in March. The South region contributed
           the most to the decline, dropping 22%. (Source: sales_data.csv,
           24 rows analysed)"
        │
        ▼
chart_selector.py
  Sees: 2 columns, one text + one numeric → bar chart
  Renders: Plotly Express bar chart
        │
        ▼
app.py assembles and displays:
  • Plain English answer
  • Plotly chart
  • Collapsible SQL panel (source transparency — NatWest Trust pillar)
  • Row count + columns referenced
        │
        ▼
USER asks another question → back to LLM CALL #1
USER uploads new file → back to schema_extractor.py
```

---

## 5. Current File Structure

```
talk-to-data/
│
├── src/
│   ├── __init__.py              ✅ DONE — package marker
│   ├── config.py                ✅ DONE — all env vars, constants, blocklist
│   ├── schema_extractor.py      ✅ DONE — Stage 2 complete, 12 tests passing
│   ├── llm_client.py            ⏳ TODO — Stage 3
│   ├── sql_generator.py         ⏳ TODO — Stage 4
│   ├── sql_executor.py          ⏳ TODO — Stage 4
│   ├── answer_generator.py      ⏳ TODO — Stage 4
│   ├── chart_selector.py        ⏳ TODO — Stage 5
│   └── orchestrator.py          ⏳ TODO — Stage 6 (after all above done)
│
├── tests/
│   ├── __init__.py              ✅ DONE
│   └── test_schema_extractor.py ✅ DONE — 12 tests, all passing
│
├── assets/
│   ├── sample_data/
│   │   ├── sales_sample.csv     ✅ DONE — 24 rows, 6 cols
│   │   └── customer_sample.csv  ✅ DONE — 12 rows, 7 cols
│   └── screenshots/             ⏳ Empty — fill before submission
│
├── docs/
│   ├── architecture.md          ✅ DONE
│   └── prompt_engineering.md    ✅ DONE
│
├── scripts/
│   ├── README.md                ⏳ TODO — create
│   └── verify_setup.py          ⏳ TODO — create
│
├── app.py                       ⏳ TODO — Stage 6
├── requirements.txt             ✅ DONE — 8 packages, all pinned
├── .env.example                 ✅ DONE — 8 variables, no real keys
├── .gitignore                   ✅ DONE — covers .env, pycache, venv, logs
├── LICENSE                      ✅ DONE — Apache 2.0 full text
├── README.md                    ⏳ PLACEHOLDER — full version at Stage 8
└── CLAUDE.md                    ✅ DONE — AI/team reference (this project's rules)
```

---

## 6. Every File Explained

### `src/config.py` ✅
**Role:** Single source of all configuration. Every other module imports
from here. No module reads `os.environ` directly.

**Key exports:**
```python
GROQ_API_KEY          # Groq API key from .env
GROQ_MODEL_PRIMARY    # "llama-3.3-70b-versatile"
GROQ_MODEL_FALLBACK   # "llama-3.1-8b-instant"
GEMINI_API_KEY        # Gemini API key from .env
GEMINI_MODEL          # "gemini-2.5-flash"
MAX_SAMPLE_ROWS       # 3 — rows sent to LLM for schema context
DUCKDB_TABLE_NAME     # "data" — always this name in all SQL
SQL_BLOCKLIST         # list of forbidden SQL keywords
validate_config()     # returns list of warning strings if keys missing
```

**Why it exists:** Prevents hardcoded values scattered across files.
Makes config changes a one-file operation.

---

### `src/schema_extractor.py` ✅
**Role:** Stage 2. Reads uploaded file, infers schema, builds LLM context.

**Key exports:**
```python
extract_schema(file) -> dict
# Returns:
# {
#   "df": pd.DataFrame,        # full data for DuckDB
#   "schema_str": str,         # sent to LLM (schema only, no raw data)
#   "column_types": dict,      # col_name -> "text"|"integer"|"float"|"datetime"|"boolean"
#   "filename": str,           # original filename
#   "row_count": int,
#   "col_count": int,
# }

SchemaExtractionError          # raised for bad files, empty files, wrong format
```

**Privacy guarantee:** `df` (full data) stays in the returned dict and
goes into DuckDB. Only `schema_str` (column names + types + 3 sample values)
ever goes to the LLM API.

**Supported formats:** `.csv`, `.xlsx`, `.xls`

**Auto-detection:** String columns that look like dates (≥80% parse rate)
are automatically converted to datetime type.

---

### `src/llm_client.py` ⏳ TO BE BUILT — Stage 3
**Planned role:** Handles all LLM API calls with automatic fallback.

**Planned logic:**
```
call_llm(system_prompt, user_message) -> str
  → try Groq llama-3.3-70b-versatile
  → on 429 (rate limit) → retry with Groq llama-3.1-8b-instant
  → on 429 again → fallback to Gemini gemini-2.5-flash
  → on all fail → raise LLMError with user-friendly message
```

---

### `src/sql_generator.py` ⏳ TO BE BUILT — Stage 4
**Planned role:** LLM Call #1. Converts natural language + schema → SQL.

**Planned system prompt key rules:**
- Output ONLY the SQL query, no markdown, no backticks
- Table name is always `data`
- SELECT only — no mutations
- If unanswerable: output exactly `CANNOT_ANSWER`

---

### `src/sql_executor.py` ⏳ TO BE BUILT — Stage 4
**Planned role:** Safety validation + DuckDB execution.

**Planned safety check:**
```python
# Checks SQL against SQL_BLOCKLIST from config.py
# Raises SafetyError if any blocked keyword found
# Executes against DuckDB only if safe
```

**DuckDB setup:** Loads Pandas DataFrame into in-memory DuckDB connection.
Table name always `data` (from `config.DUCKDB_TABLE_NAME`).

---

### `src/answer_generator.py` ⏳ TO BE BUILT — Stage 4
**Planned role:** LLM Call #2. Converts result rows → plain English.

**Planned system prompt key rules:**
- 2–3 sentences maximum
- Plain English, no jargon
- Must include actual numbers from results
- Must end with: `(Source: {filename}, {n} rows analysed)`
- Do not infer causes not present in the data

---

### `src/chart_selector.py` ⏳ TO BE BUILT — Stage 5
**Planned role:** Rule-based chart type selection + Plotly rendering.

**Planned logic:**
```
result has 1 row, 1 numeric col  → metric card (big number display)
result has date + numeric col    → line chart
result has text + numeric col    → bar chart
result has 2-6 text rows, %s     → pie chart
result has many columns          → table
```

---

### `src/orchestrator.py` ⏳ TO BE BUILT — Stage 6
**Planned role:** Wires all stages into one callable function.

```python
def run_query(question: str, session_state: dict) -> AnswerResult:
    # session_state contains: df, schema_str, filename
    # returns: AnswerResult(answer, sql, chart, source_info)
```

---

### `app.py` ⏳ TO BE BUILT — Stage 6
**Planned role:** Streamlit frontend. UI only — no business logic here.

**Planned sections:**
- Sidebar: file uploader + dataset info panel
- Main: chat-style question input
- Main: answer text + Plotly chart
- Main: collapsible "SQL used" panel (Trust pillar)

---

### `assets/sample_data/sales_sample.csv` ✅
24 rows × 6 columns: `date, region, product, revenue, units_sold, ad_spend`
- Covers 3 months (Jan–Mar 2026), 4 regions, 2 products
- Designed to answer all 4 NatWest use cases:
  - Change: revenue drops in South region over time
  - Compare: Region A vs B, Product A vs B
  - Breakdown: revenue by region/product
  - Summarize: weekly/monthly totals

### `assets/sample_data/customer_sample.csv` ✅
12 rows × 7 columns: `week_start, signups, churned, active_users,
avg_handle_time_seconds, support_tickets, satisfaction_score`
- 12 weeks of data (Jan–Mar 2026)
- Shows improving trends (growing signups, falling handle time)

---

## 7. Technology Stack

### Exact versions (from requirements.txt)

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| streamlit | 1.45.0 | Apache 2.0 | Web UI framework |
| pandas | 2.2.3 | BSD-3 | Data reading + manipulation |
| openpyxl | 3.1.5 | MIT | Excel file support (.xlsx) |
| duckdb | 1.2.2 | MIT | In-memory SQL engine |
| groq | 0.23.1 | Apache 2.0 | Primary LLM API client |
| google-generativeai | 0.8.5 | Apache 2.0 | Fallback LLM API client |
| plotly | 6.0.1 | MIT | Interactive charts |
| python-dotenv | 1.1.0 | BSD-3 | Load .env variables |

**Python version:** 3.10.2 (confirmed on dev machine — Windows)
**OS:** Windows 11 (dev), Linux (Streamlit Cloud deployment)

### Installed transitive dependencies (auto-installed, not in requirements.txt)
```
altair-5.5.0              # Streamlit dependency
cachetools-5.5.2          # Google auth dependency
cryptography-46.0.7       # Google auth dependency
google-ai-generativelanguage-0.6.15
google-api-core-2.30.0
google-api-python-client-2.194.0
google-auth-2.49.2
googleapis-common-protos-1.74.0
groq-0.23.1
grpcio-1.80.0
grpcio-status-1.71.2
httplib2-0.31.2
proto-plus-1.27.2
```

---

## 8. Known Conflicts & Gotchas

### 8.1 Python version
- **Dev machine:** Python 3.10.2
- **Streamlit Cloud:** Python 3.11+ (may behave differently)
- **Risk:** Type hint syntax `list[str]` works in 3.10+ but `dict[str, str]`
  as a return annotation requires 3.10+. We use `from __future__ import annotations`
  if targeting 3.9.
- **Action:** If Streamlit Cloud deployment fails, add `python_requires>=3.10`
  note to README.

### 8.2 google-generativeai version
- `google-generativeai==0.8.5` uses the older `genai.GenerativeModel` API
- The newer `google-genai` SDK (1.x) has a breaking different API
- **Do NOT upgrade** to `google-genai` 1.x — it will break the fallback client
- If you see import errors like `cannot import name 'GenerativeModel'`,
  you have the wrong package installed

### 8.3 DuckDB and Pandas compatibility
- DuckDB 1.2.2 accepts Pandas DataFrames directly via `duckdb.connect()`
- Do NOT use `duckdb.from_df()` — deprecated in 1.x
- Correct pattern:
  ```python
  conn = duckdb.connect()
  conn.register("data", df)      # register DataFrame as table
  result = conn.execute(sql).df() # returns Pandas DataFrame
  ```

### 8.4 Streamlit session state
- DuckDB connection and DataFrame must be stored in `st.session_state`
- A new DuckDB connection is created on each file upload, not on each query
- If session state is cleared (page refresh), user must re-upload the file
- **Do not** create a DuckDB connection at module level — it won't persist

### 8.5 Groq rate limits (free tier)
- `llama-3.3-70b-versatile`: ~30 RPM, ~14,400 RPD
- `llama-3.1-8b-instant`: higher RPD but lower quality
- Rate limits are per **organisation**, not per API key
- Creating multiple API keys under the same org does NOT multiply limits
- On 429: wait and retry, then fall back to Gemini

### 8.6 Gemini 2.0 Flash deprecation
- `gemini-2.0-flash` was **deprecated March 2026**, shutdown September 2026
- Always use `gemini-2.5-flash` — already set in config.py default
- If you see `model not found` errors, check GEMINI_MODEL in .env

### 8.7 Windows vs Linux path separators
- All file paths in code use `pathlib.Path` or forward slashes
- Never hardcode backslashes — breaks on Streamlit Cloud (Linux)

### 8.8 Git credential on Windows
- GitHub no longer accepts account passwords for git push
- Must use a **Personal Access Token** as the password
- Generate at: GitHub → Settings → Developer settings →
  Personal access tokens → Tokens (classic)
- Scope needed: `repo` (full repository access)
- Token expires — set to 90 days and note the expiry date

### 8.9 DCO sign-off — easy to forget
- EVERY commit needs `git commit -s -m "message"`
- The `-s` flag adds `Signed-off-by: Name <email>` automatically
- If you forget on a commit, fix it with:
  ```bash
  git commit --amend -s
  git push --force-with-lease
  ```
- NatWest can check commit history — unsigned commits may disqualify

### 8.10 .env file — never commit
- `.env` is in `.gitignore` ✅
- But if you accidentally stage it: `git rm --cached .env`
- Then immediately rotate your API keys (they are compromised)

---

## 9. Free-Tier API Details

### Groq (Primary)
- **Sign up:** https://console.groq.com (no credit card)
- **Free tier:** Access to all models, rate-limited
- **Model used:** `llama-3.3-70b-versatile`
- **Speed:** 300–1,000 tokens/sec (LPU hardware — fastest free inference)
- **Free limits:** ~30 RPM, ~14,400 RPD on 70B model
- **Fallback model:** `llama-3.1-8b-instant` (~14,400+ RPD, faster)
- **Endpoint:** `https://api.groq.com/openai/v1` (OpenAI-compatible)
- **License:** Apache 2.0 ✅

### Google Gemini (Fallback)
- **Sign up:** https://aistudio.google.com (no credit card)
- **Model used:** `gemini-2.5-flash`
- **Free limits:** 10 RPM, 500 RPD, 250,000 TPM
- **Important:** `gemini-2.0-flash` deprecated March 2026 — use 2.5 only
- **License:** Apache 2.0 ✅

### Fallback trigger logic
```
Primary call  → Groq llama-3.3-70b-versatile
On 429 error  → Groq llama-3.1-8b-instant (same provider, smaller model)
On 429 again  → Gemini gemini-2.5-flash
On all fail   → Return user-friendly error, never crash
```

---

## 10. Build Progress

### ✅ Stage 1 — Project setup (COMPLETE)
**Commit:** `chore: stage 1 project setup and structure`

Files created:
- `requirements.txt` — 8 packages, pinned, all Apache/MIT/BSD
- `.env.example` — 8 environment variables, no real keys
- `.gitignore` — covers .env, pycache, venv, OS files
- `LICENSE` — Apache 2.0 full text
- `src/__init__.py` — package marker
- `src/config.py` — central config loader
- `tests/__init__.py` — test package marker
- `docs/architecture.md` — architecture reference
- `docs/prompt_engineering.md` — LLM prompt documentation
- `assets/sample_data/sales_sample.csv` — 24 rows demo data
- `assets/sample_data/customer_sample.csv` — 12 rows demo data

---

### ✅ Stage 2 — Schema Extractor (COMPLETE)
**Commit:** `feat: add schema extractor with full test coverage`
**Test result:** 12/12 tests passing in 1.38s

Files created:
- `src/schema_extractor.py` — full implementation
- `tests/test_schema_extractor.py` — 12 unit tests

**What it does:**
- Reads CSV (via pandas.read_csv) and Excel (via pandas.read_excel + openpyxl)
- Strips whitespace from column names
- Infers column types: datetime, boolean, integer, float, text
- Auto-detects date strings (≥80% parse rate heuristic)
- Builds schema string for LLM (column names + types + 3 sample values)
- Returns dict with df, schema_str, column_types, filename, row_count, col_count
- Raises `SchemaExtractionError` for: unsupported format, empty file, no columns

**Tests cover:**
- CSV reading returns correct DataFrame
- Unsupported format raises SchemaExtractionError
- Empty CSV raises SchemaExtractionError
- Column names are stripped of whitespace
- Integer and float type inference
- Text type inference
- Datetime type inference
- Schema string contains filename
- Schema string contains all column names
- Schema string contains row count
- extract_schema returns all required keys
- extract_schema returns correct row and col counts

---

### ⏳ Stage 3 — LLM Client (TODO)
**File:** `src/llm_client.py`

Must implement:
- `call_llm(system_prompt: str, user_message: str) -> str`
- Groq client using `groq.Groq(api_key=GROQ_API_KEY)`
- Gemini client using `google.generativeai`
- Automatic fallback on 429 errors
- Graceful error handling (never crash, always return string)
- `LLMError` custom exception class

---

### ⏳ Stage 4 — SQL Pipeline (TODO)
**Files:** `src/sql_generator.py`, `src/sql_executor.py`, `src/answer_generator.py`

sql_generator.py must implement:
- `generate_sql(question: str, schema_str: str) -> str`
- Uses LLM Call #1 with SQL_SYSTEM_PROMPT
- Returns SQL string or "CANNOT_ANSWER" sentinel
- `SQLGenerationError` custom exception

sql_executor.py must implement:
- `load_dataframe(df: pd.DataFrame) -> duckdb.DuckDBPyConnection`
- `is_safe_sql(sql: str) -> bool` — checks against SQL_BLOCKLIST
- `execute_query(conn, sql: str) -> pd.DataFrame`
- `SafetyError` custom exception

answer_generator.py must implement:
- `generate_answer(question: str, result_df: pd.DataFrame, filename: str) -> str`
- Uses LLM Call #2 with ANSWER_SYSTEM_PROMPT
- Always includes source reference in output

---

### ⏳ Stage 5 — Chart Selector (TODO)
**File:** `src/chart_selector.py`

Must implement:
- `select_and_render(result_df: pd.DataFrame, question: str) -> plotly.Figure | None`
- Rule-based chart type selection (no LLM needed here)
- Returns None for single-value results (shown as metric card in UI)

---

### ⏳ Stage 6 — Orchestrator + Streamlit UI (TODO)
**Files:** `src/orchestrator.py`, `app.py`

orchestrator.py must implement:
- `run_query(question: str, schema_str: str, conn, filename: str) -> AnswerResult`
- `AnswerResult` dataclass with: answer, sql, chart, source_info, error

app.py must implement:
- Streamlit page config and layout
- File uploader (sidebar)
- Schema info display after upload
- Chat-style question input
- Answer + chart display
- Collapsible SQL panel (mandatory for Trust pillar)
- Config warnings if API keys missing

---

### ⏳ Stage 7 — Tests + Sample Data (TODO)
Additional tests needed:
- `tests/test_sql_executor.py` — safety validator tests (critical)
- `tests/test_answer_generator.py` — output format tests

---

### ⏳ Stage 8 — README + Deployment (TODO)
- Complete README.md with all NatWest required sections
- Deploy to Streamlit Community Cloud
- Add screenshots to `assets/screenshots/`
- Run pre-submission checklist
- Final DCO sign-off audit

---

## 11. Stages Remaining

```
Stage 3 → llm_client.py       (Groq + Gemini with fallback)
Stage 4 → sql pipeline         (generator + executor + answer)
Stage 5 → chart_selector.py   (Plotly chart rendering)
Stage 6 → orchestrator.py     (pipeline wiring)
Stage 6 → app.py              (Streamlit UI)
Stage 7 → more tests
Stage 8 → README + deploy + submit
```

---

## 12. Coding Conventions

### Python style
- Python 3.10+ syntax
- Type hints on ALL function signatures
- Google-style docstrings on ALL public functions and classes
- Max line length: 88 characters
- Run `black .` before every commit
- No `print()` statements in src/ — use proper error returns

### Naming
| Type | Convention | Example |
|------|-----------|---------|
| Files | snake_case | `schema_extractor.py` |
| Classes | PascalCase | `SchemaExtractionError` |
| Functions | snake_case | `extract_schema()` |
| Constants | UPPER_SNAKE | `SQL_BLOCKLIST` |
| Variables | snake_case | `column_types` |
| Tests | test_*.py | `test_schema_extractor.py` |

### Error handling
- Every public function has a custom exception class
- Never let exceptions bubble up to Streamlit as a traceback
- Always return a user-friendly string on failure

### LLM prompt discipline
- System prompts documented in `docs/prompt_engineering.md`
- AND defined as constants in the relevant src/ file
- Always include: "Output ONLY [X]. No explanation, no markdown."
- Never send full dataset rows to LLM — schema + sample only
- SQL prompt must include: "Use only DuckDB-compatible SQL. SELECT only."
- Answer prompt must include: "Always reference the data source filename."

---

## 13. Git Rules

### Every commit
```bash
git commit -s -m "type: short description"
# -s is MANDATORY — adds DCO sign-off
```

### Commit types
```
feat     new feature
fix      bug fix
docs     documentation only
refactor code restructure, no behaviour change
test     adding or fixing tests
chore    dependencies, config, setup
```

### One email rule
```bash
# Set once, use for ALL commits
git config user.name "Abhay Jeet"
git config user.email "your@email.com"
```

### Branch
- `main` is always deployable
- Work directly on main for hackathon speed
- If branching: `feature/stage-3-llm-client`

---

## 14. Environment Variables

Full list — all must be in `.env` locally, in Streamlit secrets for deployment:

```bash
# Required — get from console.groq.com (free, no credit card)
GROQ_API_KEY=gsk_...

# Optional — defaults shown below
GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile
GROQ_MODEL_FALLBACK=llama-3.1-8b-instant

# Required — get from aistudio.google.com (free, no credit card)
GEMINI_API_KEY=AIza...

# Optional — defaults shown below
GEMINI_MODEL=gemini-2.5-flash

# Optional — all have sensible defaults
MAX_FILE_SIZE_MB=50
MAX_SAMPLE_ROWS=3
SQL_TIMEOUT_SECONDS=10
ENABLE_DEBUG_SQL=false
```

### Streamlit Cloud deployment secrets
In Streamlit Cloud, go to App → Settings → Secrets and paste:
```toml
GROQ_API_KEY = "gsk_..."
GEMINI_API_KEY = "AIza..."
```

---

## 15. Running the Project

### First time setup
```bash
# Clone
git clone https://github.com/abhayjeet5465/talk-to-data.git
cd talk-to-data

# Virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Configure keys
copy .env.example .env       # Windows
cp .env.example .env         # Mac/Linux
# Edit .env and add real GROQ_API_KEY and GEMINI_API_KEY
```

### Run the app (once app.py is built in Stage 6)
```bash
streamlit run app.py
```

### Run tests
```bash
pytest tests/ -v
```

### Verify setup
```bash
python scripts/verify_setup.py
```

---

## 16. Testing

### Current test status
```
tests/test_schema_extractor.py    12 tests    ✅ ALL PASSING (1.38s)
```

### Running tests
```bash
pytest tests/ -v                  # all tests with detail
pytest tests/ -v --tb=short       # shorter traceback on failure
pytest tests/test_schema_extractor.py -v   # single file
```

### Test conventions
- Tests in `tests/` directory
- Files named `test_*.py`
- Functions named `test_*`
- Use `pytest.raises` for exception testing
- No empty placeholder tests — NatWest requires "real and meaningful" tests
- Use `io.BytesIO` with `.name` attribute to mock Streamlit file uploads

---

## 17. Pre-Submission Checklist

Run through every item before submitting the GitHub URL to NatWest.

### Code
- [ ] `pip install -r requirements.txt` works from fresh clone
- [ ] `streamlit run app.py` starts without errors
- [ ] `pytest tests/ -v` — all tests pass
- [ ] No hardcoded API keys anywhere in source
- [ ] `.env` is NOT committed (check `git log -- .env`)
- [ ] `.env.example` lists all required variables
- [ ] No `print()` debug statements in `src/`
- [ ] No unused files or stray logs

### Features (NatWest honesty rule)
- [ ] Every feature in README exists and works
- [ ] Partial features clearly labelled in README
- [ ] All 4 use cases work with sample datasets
- [ ] SQL always shown to user (source transparency)
- [ ] Graceful error shown if LLM fails (no crash)
- [ ] Rate limit fallback works (Groq → Gemini)

### README
- [ ] Overview section (2–5 sentences)
- [ ] Features section (working only)
- [ ] Install and run instructions
- [ ] Tech stack listed
- [ ] Usage examples with sample questions
- [ ] Architecture notes
- [ ] Limitations section (honest)
- [ ] Screenshots in assets/screenshots/

### Git / NatWest compliance
- [ ] Every commit has `-s` sign-off
  (`git log --format="%H %s %b" | grep -c "Signed-off-by"`)
- [ ] All commits use same email address
- [ ] `LICENSE` file contains Apache 2.0 full text
- [ ] Repository is PRIVATE on GitHub
- [ ] Deployed on Streamlit Community Cloud
- [ ] Deployed URL works and is in README

---

*End of REFERENCE.md*
*Maintained by: Talk-to-Data team*
*Hackathon: NatWest Code for Purpose 2026 — India*
*License: Apache 2.0*
