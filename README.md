# Talk to Data — Seamless Self-Service Intelligence

![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)

## Overview
**Talk to Data** is an enterprise-grade, privacy-preserving conversational analytics application built for the NatWest Code for Purpose Hackathon. 

![Graph Output Showcase](assets/image1.png)

![Talk to Data UI Showcase](assets/image2.png)

Many non-technical users struggle to get quick, trustworthy answers from their data due to complex tools and unclear terminology. This project democratizes data access by allowing users to upload any CSV or Excel file and ask questions in plain English. By prioritizing **Clarity**, **Trust**, and **Speed**, the application bridges the gap between raw data and actionable business insights.

## Features
- **Instant Conversational Analytics**: Ask complex analytical questions (e.g., "Why did revenue drop last month?") and receive plain-English, jargon-free explanations.
- **Multi-File Cross-Dataset Analysis**: Upload up to **3 CSV or Excel files simultaneously**. The system automatically detects matching columns across files (e.g., a shared `product_id`) and uses them as JOIN keys — no manual data preparation needed.
- **Privacy-First Local Execution**: Uses in-memory `DuckDB` to query data locally on your machine. **Your raw data never leaves the session;** only schema metadata (like column names) is sent to the LLM APIs.
- **Explainable AI (XAI) with Data Lineage**: Every answer includes a "How was this calculated?" transparency expander. For cross-file queries, an additional **"Data Lineage"** panel explicitly lists which files were joined and on which keys.
- **Enterprise Security**: Implements a strict two-layer defense mechanism (AST parsing via `sqlparse` + keyword blocklists) to guarantee safety from SQL injection or data mutation.
- **Resilient Data Ingestion**: Automatically handles both standard UTF-8 and legacy Excel/Windows-1252 (`latin-1`) encodings to effortlessly read tricky CSV exports without crashing.
- **Ambiguity Detection**: If a user asks a vague question (e.g., "Show top products"), the system automatically intercepts it and asks for clarification ("Top by what metric?") instead of guessing.
- **AI Self-Correction**: When a generated SQL query fails (e.g., hallucinated column name or bad JOIN), the orchestrator silently retries with the error message fed back to the LLM — the user never sees the failure.
- **Dynamic Visualizations**: Automatically selects and renders beautiful Plotly charts (bar, line, pie) styled in the official NatWest brand palette.

## Tech Stack
- **Frontend Framework**: Streamlit (Python)
- **Data Engine**: DuckDB, Pandas
- **Visualization**: Plotly Express, Plotly Graph Objects
- **LLM Orchestration**: Groq API (Primary), Google Gemini API (Fallback)
- **Security & Parsing**: `sqlparse`

## Installation and Run Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/abhayjeet5465/talk-to-data
   cd talk-to-data
   ```

2. **Set up your environment:**
   We recommend using a virtual environment (optional but best practice):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API keys:**
   Copy the example environment variables file and add your free tier API keys for Groq and Gemini.
   ```bash
   cp .env.example .env
   ```
   *(Note: The system acts resiliently and will warn you via the UI if keys are missing.)*

5. **Run the application:**
   ```bash
   streamlit run app.py
   ```

## Usage Examples

### Single-file mode
1. **Upload your file:** Use the sidebar to upload a `sales.csv` or `.xlsx` file (up to 50 MB). A dataset info panel will appear with rows, columns, and data types.
2. **Ask a question:** Type into the chat input:
   > *"What is the breakdown of units sold by region?"*
3. **View the analysis:** The system displays a plain-English summary and a NatWest-branded Plotly chart.
4. **Source Transparency:** Click the **"How was this calculated?"** expander to verify the exact SQL executed.

### Multi-file cross-dataset mode
1. **Upload 2 or 3 files** (e.g., `sales.csv` and `product_catalog.xlsx`). Each file is assigned a safe SQL table name automatically.
2. **The system auto-detects join keys** — if both files share a `product_id` column, it tells the LLM to JOIN on it.
3. **Ask a cross-file question:**
   > *"What is the total revenue broken down by product category?"*
4. **View the Data Lineage panel** to see exactly which files were combined and how.

## Architecture & Technical Depth

Building a text-to-SQL pipeline that doesn't hallucinate requires strict boundaries. We utilized the following advanced techniques:

- **Chain-of-Thought (CoT) Prompting:** The SQL generator forces the model to write a step-by-step reasoning plan inside `<logic>` XML tags *before* outputting SQL. For multi-file queries, the model explicitly reasons about which tables to join and which key to use.
- **Deterministic Join-Key Inference:** Rather than relying on the LLM to guess foreign keys, `schema_extractor.py` scans all uploaded DataFrames for columns with identical names and compatible types, then injects these as explicit hints (`SYSTEM INFERRED JOIN KEYS`) into the prompt. This dramatically increases JOIN accuracy.
- **Multi-Table DuckDB Registration:** All uploaded DataFrames are registered as separate named virtual tables in a single in-memory DuckDB connection via `load_multiple_dataframes()`. Each filename is slugified into a safe SQL identifier (e.g., `2026 Sales.xlsx` → `tbl_2026_sales`).
- **AST Security Validation:** All AI-generated queries pass through an AST validator (`sqlparse`) to guarantee the root operation is strictly a `SELECT` before DuckDB executes it.
- **Orchestrator Self-Correction:** When a query fails (bad column name or invalid JOIN), the orchestrator silently feeds the DuckDB error back to the LLM for one hidden retry attempt — works for both single-file and multi-file pipelines.

## Development & Testing
The project uses `pytest` heavily to guarantee pipeline stability.
To run the full suite:
```bash
python -m pytest tests/ -v
```

## Limitations
- **File size**: Because `DuckDB` runs in-memory, file uploads are capped at 50 MB each to prevent memory exhaustion on local hardware.
- **Max 3 files**: The multi-file uploader is intentionally capped at 3 concurrent datasets to prevent LLM context dilution and maintain JOIN accuracy.
- **JOIN accuracy**: The underlying Llama 3.3 70B model has ~52% first-attempt accuracy on multi-table SQL. The self-correction loop mitigates this, but complex cross-file queries may occasionally require rephrasing.

## Future Improvements
- **Semantic Dictionary Integration**: Allow companies to upload a JSON dictionary of defined metrics (e.g. `{"active_user": "logged in within 30 days"}`) and inject this dynamically into the LLM prompt.
- **Export to PDF**: Add a button to export the generated narrative and Plotly chart into a downloadable PDF report for management.
- **Streaming answers**: Stream the LLM response token-by-token into the UI for a faster perceived response time.

## Licensing & Compliance
This project is licensed under the Apache License 2.0. All commits are signed off under the Developer Certificate of Origin (DCO).
