# CLAUDE.md — NatWest Code for Purpose 2026
## Theme 1: Talk to Data — Seamless Self-Service Intelligence

> This file is the single source of truth for all contributors.
> Read it fully before writing any code, naming any file, or making any commit.
> It covers: project mission, architecture, free-tier stack, folder structure,
> coding conventions, Git rules, and NatWest submission requirements.

---

## 1. Project Mission

**What we are building:**
A self-service natural language analytics tool that lets anyone — regardless
of technical skill — upload a dataset and immediately ask plain-English
questions about it, receiving clear, trusted, and near-instant answers.

**The three NatWest pillars we must satisfy on every response:**

| Pillar | Definition | Implementation target |
|--------|-----------|----------------------|
| **Clarity** | Answers simple enough for non-experts | Plain English + visual |
| **Trust** | Source transparency, consistent metrics | Show SQL + data source |
| **Speed** | Near-instant, minimal steps | < 3 sec end-to-end |

**The four use cases every contributor must keep in mind:**
1. Understand what changed — "Why did X drop last month?"
2. Compare — "Region A vs Region B", "This week vs last week"
3. Breakdown — "What makes up total sales?"
4. Summarize — "Give me a weekly summary of customer metrics"

**What we must NOT do:**
- Over-predict or hallucinate data values
- Expose private or sensitive data
- Require technical knowledge to use
- Produce slow or complicated workflows

---

## 2. Free-Tier Technology Stack

All services below are **free tier, no credit card required**, and
**Apache 2.0 compatible**. Do not introduce any paid service without
team agreement and a note in this file.

### 2.1 AI / LLM Layer

#### Primary: Groq API — `llama-3.3-70b-versatile`
- **Why Groq:** Fastest free inference available in 2026 (300–1,000 tokens/sec
  on LPU hardware). OpenAI-compatible endpoint. No credit card needed.
- **Free tier limits:** ~30 RPM, ~14,400 requests/day on smaller models;
  Llama 3.3 70B is the recommended model for quality + speed balance.
- **Sign up:** https://console.groq.com — generate an API key immediately.
- **Models available free:** `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`,
  `llama4-scout-17b-16e-instruct` (use 70B as default, 8B as fallback if
  rate limited).
- **Endpoint:** `https://api.groq.com/openai/v1` (OpenAI-compatible).

#### Fallback: Google Gemini API — `gemini-2.5-flash`
- **Why Gemini fallback:** Free tier exists with no credit card for
  `gemini-2.5-flash` (10 RPM, 500 RPD) and `gemini-2.5-flash-lite`
  (15 RPM, 1,000 RPD). Use as fallback when Groq rate limits are hit.
- **Sign up:** https://aistudio.google.com — get API key instantly.
- **Important:** `gemini-2.0-flash` was deprecated March 2026. Use `2.5` series only.

#### Rate Limit Strategy
```
Primary call  → Groq (llama-3.3-70b-versatile)
On 429 error  → Retry with Groq (llama-3.1-8b-instant)
On 429 again  → Fall back to Gemini (gemini-2.5-flash)
On all fail   → Return cached result or graceful error message
```

### 2.2 Backend

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | **Python 3.11+** | Best AI/data ecosystem |
| Web framework | **FastAPI** | Async, fast, auto-docs |
| Data processing | **Pandas + DuckDB** | In-memory SQL on any CSV/Excel |
| NL → SQL bridge | **Custom prompt chain** | No paid lib dependency |
| SQL execution | **DuckDB** | Runs entirely local, no DB server needed |
| Schema inference | **Pandas `.dtypes` + LLM** | Auto-detects column semantics |

**Why DuckDB over SQLite:**
DuckDB handles analytical queries (GROUP BY, window functions, aggregations)
far faster than SQLite and requires zero configuration. Perfect for hackathon.

### 2.3 Frontend

| Component | Choice | Reason |
|-----------|--------|--------|
| UI framework | **Streamlit** | Python-native, deploys free on Streamlit Cloud |
| Charts | **Plotly Express** | Interactive, zero config |
| File upload | **Streamlit file_uploader** | Built-in drag-and-drop |

### 2.4 Hosting (Free)

| Service | What it hosts | Free tier |
|---------|--------------|-----------|
| **Streamlit Community Cloud** | Full app (frontend + backend) | Unlimited public apps |
| **GitHub** | Code repository | Free private repo |

Streamlit Community Cloud connects directly to GitHub. Push to `main` → auto-deploys.
No Docker, no server setup, works globally.

### 2.5 License Compliance

- Project license: **Apache 2.0** (required by NatWest)
- All dependencies must be Apache 2.0, MIT, or BSD compatible.
- Add a `LICENSE` file at repo root containing the Apache 2.0 text.
- Every commit must be signed off: `git commit -s -m "your message"`

#### Approved dependency licenses:
```
streamlit          → Apache 2.0  ✓
fastapi            → MIT         ✓
pandas             → BSD-3       ✓
duckdb             → MIT         ✓
plotly             → MIT         ✓
groq (SDK)         → Apache 2.0  ✓
google-generativeai → Apache 2.0  ✓
python-dotenv      → BSD-3       ✓
```

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER (Browser)                        │
│         Uploads CSV/Excel  │  Types question             │
└────────────────┬───────────┴────────────────────────────┘
                 │ HTTPS
┌────────────────▼───────────────────────────────────────┐
│              STREAMLIT FRONTEND                         │
│  • File upload widget                                   │
│  • Chat input box                                       │
│  • Answer display (text + Plotly chart)                 │
│  • Source reference panel (shows SQL used)              │
└────────────────┬───────────────────────────────────────┘
                 │ Python function call (same process)
┌────────────────▼───────────────────────────────────────┐
│              ORCHESTRATOR  (src/orchestrator.py)        │
│                                                         │
│  1. SCHEMA EXTRACTOR                                    │
│     └─ Reads uploaded file via Pandas                   │
│     └─ Infers column names, types, sample values        │
│     └─ Builds a schema context string                   │
│                                                         │
│  2. NL → SQL GENERATOR  (LLM call #1)                  │
│     └─ Sends: user question + schema context            │
│     └─ Receives: SQL query string                       │
│     └─ Validates SQL (no DROP/DELETE/INSERT)            │
│                                                         │
│  3. SQL EXECUTOR                                        │
│     └─ Runs query on DuckDB (in-memory)                 │
│     └─ Returns result DataFrame                         │
│                                                         │
│  4. ANSWER GENERATOR  (LLM call #2)                    │
│     └─ Sends: question + SQL results + schema           │
│     └─ Receives: plain-English explanation              │
│                                                         │
│  5. CHART SELECTOR                                      │
│     └─ Rule-based: picks bar/line/pie by query type     │
│     └─ Renders with Plotly Express                      │
│                                                         │
│  6. SOURCE TRANSPARENCY                                 │
│     └─ Returns SQL used, columns referenced, row count  │
└────┬─────────────────────────────────────────┬──────────┘
     │ Groq API (primary)                       │ Gemini API (fallback)
     │ llama-3.3-70b-versatile                  │ gemini-2.5-flash
     │ api.groq.com/openai/v1                   │ generativelanguage.googleapis.com
     └──────────────────────────────────────────┘
```

### Data Flow (step by step)

```
User uploads sales_data.csv
        │
        ▼
Schema extracted:
  columns: [date, region, product, revenue, units]
  types:   [datetime, str, str, float, int]
  sample:  first 3 rows shown to LLM
        │
        ▼
User asks: "Why did revenue drop last month?"
        │
        ▼
LLM Call #1 — NL to SQL
  prompt: "Given this schema [...], write a DuckDB SQL query to answer: [question]"
  output: SELECT region, SUM(revenue) FROM data
          WHERE date >= '2026-03-01' AND date < '2026-04-01'
          GROUP BY region ORDER BY SUM(revenue) ASC LIMIT 10
        │
        ▼
SQL Validation (blocklist check: DROP, DELETE, INSERT, UPDATE, ALTER)
        │
        ▼
DuckDB executes query on in-memory DataFrame
  result: [("South", 45000), ("North", 82000), ...]
        │
        ▼
LLM Call #2 — Result to Plain English
  prompt: "Explain this result in 2-3 sentences for a non-technical manager.
           Always mention which data source was used."
  output: "Revenue dropped 11% in March. The South region fell the most,
           contributing 62% of the decline, driven by lower unit sales.
           (Source: sales_data.csv, columns: date, region, revenue)"
        │
        ▼
Chart auto-selected: Bar chart (comparison result → bar)
        │
        ▼
User sees: Text answer + bar chart + collapsible SQL panel
```

### Security Model

- Dataset never leaves the user's session (Streamlit session state).
- Only schema metadata (column names + sample rows) is sent to the LLM API.
- Full row data is processed locally by DuckDB.
- SQL is validated before execution (read-only allowlist).
- API keys stored in `.env` only — never in source code.

---

## 4. Folder Structure

Follow this structure exactly. Do not create files outside it without
updating this file.

```
talk-to-data/
│
├── src/
│   ├── __init__.py
│   ├── orchestrator.py        # Main pipeline: schema → SQL → execute → explain
│   ├── schema_extractor.py    # Pandas-based schema + sample extractor
│   ├── sql_generator.py       # LLM prompt chain: NL → SQL
│   ├── sql_executor.py        # DuckDB wrapper + SQL safety validator
│   ├── answer_generator.py    # LLM prompt chain: result → plain English
│   ├── chart_selector.py      # Rule-based chart type picker + Plotly renderer
│   ├── llm_client.py          # Groq + Gemini client with fallback logic
│   └── config.py              # Load env vars, model names, constants
│
├── tests/
│   ├── test_schema_extractor.py
│   ├── test_sql_generator.py
│   ├── test_sql_executor.py
│   └── test_answer_generator.py
│
├── assets/
│   ├── sample_data/
│   │   ├── sales_sample.csv       # Demo dataset (no real data)
│   │   └── customer_sample.csv    # Second demo dataset
│   └── screenshots/               # UI screenshots for README
│
├── docs/
│   ├── architecture.md            # Expanded architecture notes
│   └── prompt_engineering.md      # LLM prompt templates documented
│
├── app.py                     # Streamlit entry point — UI only, no logic
├── requirements.txt           # All Python deps pinned to exact versions
├── .env.example               # Template — all required env vars, no real values
├── .gitignore                 # Includes .env, __pycache__, *.pyc, .DS_Store
├── LICENSE                    # Apache 2.0 full text
├── README.md                  # NatWest submission document
└── CLAUDE.md                  # This file — single source of truth
```

---

## 5. Environment Variables

Copy `.env.example` to `.env` and fill in your values locally.
**Never commit `.env`.**

```bash
# .env.example

# === PRIMARY LLM (Groq) ===
# Get free key at: https://console.groq.com
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile
GROQ_MODEL_FALLBACK=llama-3.1-8b-instant

# === FALLBACK LLM (Google Gemini) ===
# Get free key at: https://aistudio.google.com
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# === APP CONFIG ===
MAX_FILE_SIZE_MB=50
MAX_ROWS_TO_LLM=5          # Sample rows sent to LLM for schema context
SQL_TIMEOUT_SECONDS=10
ENABLE_DEBUG_SQL=false      # Set true to show SQL in UI always
```

---

## 6. Coding Conventions

Every contributor follows these rules. PRs that violate them will be
asked to fix before merge.

### 6.1 Python Style

- Python 3.11+ syntax only.
- Use type hints on all function signatures.
- Use docstrings on all public functions and classes (Google style).
- Max line length: 88 characters (Black formatter default).
- Run `black .` before every commit.
- Run `ruff check .` before every commit.

```python
# GOOD
def generate_sql(question: str, schema: dict) -> str:
    """
    Generate a DuckDB-compatible SQL query from a natural language question.

    Args:
        question: The user's plain-English question about their data.
        schema: Dict containing column names, types, and sample values.

    Returns:
        A valid, read-only SQL query string.

    Raises:
        SQLGenerationError: If the LLM fails to produce parseable SQL.
    """
    ...

# BAD — no type hints, no docstring, vague name
def gen(q, s):
    ...
```

### 6.2 No Hardcoded Values

```python
# GOOD
from src.config import GROQ_MODEL_PRIMARY, MAX_ROWS_TO_LLM

# BAD
model = "llama-3.3-70b-versatile"  # hardcoded
```

### 6.3 SQL Safety Rules

Every SQL string from the LLM must pass the validator before execution.

```python
# src/sql_executor.py — safety check (implement this)
BLOCKED_KEYWORDS = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
                    "CREATE", "TRUNCATE", "EXEC", "EXECUTE", "--", ";--"]

def is_safe_sql(query: str) -> bool:
    upper = query.upper()
    return not any(kw in upper for kw in BLOCKED_KEYWORDS)
```

### 6.4 LLM Prompt Discipline

- System prompts live in `docs/prompt_engineering.md` AND as constants
  in the relevant `src/` file.
- Every prompt must include: "Respond only with [X]. Do not add explanation."
- SQL prompt must include: "Use only DuckDB-compatible SQL. Read-only SELECT only."
- Answer prompt must include: "Always reference the data source filename."
- Do NOT send full dataset rows to the LLM — schema + sample only.

```python
SQL_SYSTEM_PROMPT = """
You are a data analyst assistant. Your ONLY job is to write a single,
valid DuckDB SQL SELECT query based on the user's question and schema.

Rules:
- Output ONLY the SQL query. No explanation, no markdown, no backticks.
- Use only SELECT statements. Never use DROP, DELETE, INSERT, or UPDATE.
- The table is always named 'data'. Reference columns by exact name.
- If the question is ambiguous, write the most conservative interpretation.
- If the question cannot be answered with SQL, output: CANNOT_ANSWER
"""
```

### 6.5 Error Handling

```python
# Always handle API errors gracefully — never crash the UI
try:
    sql = generate_sql(question, schema)
except Exception as e:
    logger.error(f"SQL generation failed: {e}")
    return AnswerResult(
        answer="I wasn't able to generate a query for that question. "
               "Could you try rephrasing it?",
        sql=None,
        chart=None,
        source="Error — no data accessed"
    )
```

### 6.6 Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files | `snake_case.py` | `sql_executor.py` |
| Classes | `PascalCase` | `SchemaExtractor` |
| Functions | `snake_case` | `extract_schema()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_ROWS_TO_LLM` |
| Variables | `snake_case` | `user_question` |
| Test files | `test_*.py` | `test_sql_executor.py` |

---

## 7. Git Workflow & Commit Rules

### 7.1 Required: DCO Sign-Off on Every Commit

NatWest requires Apache 2.0 + Developer Certificate of Origin compliance.

```bash
# Always use -s flag
git commit -s -m "feat: add schema extractor for CSV files"

# This adds the sign-off line automatically:
# Signed-off-by: Your Name <your@email.com>
```

**Use one email address for all commits throughout the hackathon.**
Configure it once:
```bash
git config user.name "Your Full Name"
git config user.email "your@email.com"
```

### 7.2 Commit Message Format

```
<type>: <short description>

Types:
  feat     → new feature
  fix      → bug fix
  docs     → documentation only
  refactor → code restructure, no behavior change
  test     → adding or fixing tests
  chore    → dependency updates, config changes

Examples:
  feat: add DuckDB SQL executor with safety validator
  fix: handle empty CSV upload gracefully
  docs: update README with Streamlit deployment steps
  test: add unit tests for schema extractor
```

### 7.3 Branch Strategy

```
main          → always deployable, protected
dev           → active development, merge PRs here first
feature/<name>  → individual features (e.g., feature/chart-selector)
fix/<name>      → bug fixes
```

### 7.4 Repository Rules (NatWest requirement)

- Repository must stay **private** during the hackathon.
- Do not push `.env`, API keys, or real datasets.
- Do not push `__pycache__/`, `*.pyc`, `.DS_Store`.

`.gitignore` must include:
```
.env
__pycache__/
*.pyc
*.pyo
.DS_Store
.venv/
venv/
*.egg-info/
.pytest_cache/
```

---

## 8. README.md Requirements (NatWest Checklist)

The README is the primary submission document. It must include all of
the following sections before submission.

```markdown
## Overview          ← 2-5 sentences: what, problem, who
## Features          ← bullet list of WORKING features only
## Install & Run     ← step-by-step, assume basic technical skill
## Tech Stack        ← languages, frameworks, AI APIs, services
## Usage Examples    ← sample questions + screenshots
## Architecture      ← link to docs/architecture.md + diagram
## Limitations       ← honest list of what doesn't work
## License           ← Apache 2.0
```

**Feature honesty rule (NatWest will disqualify otherwise):**
Only list features that are fully implemented and working.
Label partial features: "Basic version implemented; [X] not yet supported."

---

## 9. Pre-Submission Checklist

Complete every item before submitting the GitHub URL.

### Code Quality
- [ ] `black .` passes with no changes
- [ ] `ruff check .` passes with no errors
- [ ] No hardcoded API keys anywhere in source
- [ ] `.env` is in `.gitignore` and not committed
- [ ] `.env.example` exists and lists all required variables

### Functionality
- [ ] App runs from fresh clone using only README instructions
- [ ] CSV upload works with the sample datasets in `assets/sample_data/`
- [ ] All four use cases work: change, compare, breakdown, summarize
- [ ] SQL is always shown to user (source transparency)
- [ ] Graceful error shown if LLM fails (no crash)
- [ ] Rate limit fallback tested (Groq → Gemini)

### Submission Requirements (NatWest)
- [ ] README has all six required sections
- [ ] Only working features listed in README
- [ ] Every commit has `-s` sign-off (check with `git log --show-signature`)
- [ ] All commits use same email address
- [ ] `LICENSE` file contains full Apache 2.0 text
- [ ] Repository is private on GitHub
- [ ] `requirements.txt` is up to date (`pip freeze > requirements.txt`)
- [ ] App is deployed and accessible on Streamlit Community Cloud
- [ ] Deployed URL is included in README

---

## 10. Quick Start for New Contributors

```bash
# 1. Clone the repo
git clone https://github.com/your-team/talk-to-data.git
cd talk-to-data

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY and GEMINI_API_KEY

# 5. Run the app
streamlit run app.py

# 6. Run tests
pytest tests/ -v

# 7. Before every commit
black .
ruff check .
git add .
git commit -s -m "feat: your change here"
```

---

## 11. Design Decisions & Rationale

| Decision | Alternatives considered | Why we chose this |
|----------|------------------------|-------------------|
| Groq as primary LLM | OpenAI, Gemini | Fastest free tier (500+ tok/sec), no credit card, Apache-compatible |
| DuckDB for SQL | SQLite, PostgreSQL | Zero setup, analytical queries, runs in-memory from DataFrame |
| Streamlit for UI | React, Flask+HTML | Fastest to build, free hosting, Python-native |
| Two LLM calls | One combined call | Separation of concerns: SQL generation and explanation are different tasks |
| No vector DB / RAG | Pinecone, Weaviate | Overkill for tabular data; DuckDB SQL is more precise and auditable |
| Schema-only to LLM | Full data to LLM | Privacy — user data never leaves local execution |

---

*Last updated: April 2026 — NatWest Code for Purpose Round 2 submission*
*License: Apache 2.0*
*All AI services used are free-tier, no credit card required*
