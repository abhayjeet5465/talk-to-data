# **Strategic Analysis of Multi-File Architectural Expansions for the Conversational Data Intelligence Platform**

## **Scope Analysis and Alignment with the Organizational Directives**

The transition from a single-file analytical environment to a multi-file, cross-relational architecture represents a significant evolution in conversational data intelligence. The foundational requirement of evaluating this architectural expansion is to determine its alignment with the core problem statement and the prescribed operational pillars of the NatWest Code for Purpose 2026 Hackathon. An exhaustive analysis of the foundational documentation indicates that a multi-file architecture is not merely permissible but highly congruent with the stated objectives, pushing the boundaries of what is expected from a robust, production-ready submission.  
The primary problem statement explicitly utilizes the plural formulation, directing developers to build solutions that "work with datasets" and enable users to ask natural language questions about "any dataset". The semantic implication of the plural form suggests an expectation that the platform can handle disparate data sources simultaneously. In modern enterprise data environments, particularly within financial institutions like NatWest, users rarely derive holistic, actionable answers from a single, perfectly denormalized flat file. Transactional data is inherently relational, requiring the synthesis of factual records with dimension tables containing hierarchical or categorical metadata.  
Furthermore, the specified use cases inherently demand multi-dimensional, and often multi-file, relational capabilities. For instance, the directive to "Compare (time, region, product, segment) — This week vs last week" frequently necessitates joining a central factual transaction table with various disparate dimensional files. A user might upload a massive sales.csv containing raw transaction identifiers alongside a highly specific regional\_hierarchies.xlsx document containing updated, user-maintained mapping configurations. Without the capacity to ingest and logically join these two distinct entities, the platform forces the user to manually merge data externally in software like Microsoft Excel before utilizing the platform. This directly violates the core mandate to "remove friction" and eliminate "too many steps or complicated tools". Consequently, enabling multi-file ingestion directly addresses the fundamental pain points outlined in the hackathon brief.  
The platform must adhere to three non-negotiable pillars: Clarity, Trust, and Speed. The integration of multi-file capability interacts with these pillars in complex ways that require careful orchestration. The pillar of Clarity demands answers simple enough for non-experts. Multi-table SQL JOIN operations have the potential to produce convoluted output datasets and highly technical internal reasoning that might confuse a layperson. However, by leveraging an advanced natural language generation layer to synthesize cross-file insights into single, digestible narratives, the architecture can amplify clarity by abstracting away the complex relational algebra.  
The pillar of Trust relies on clear definitions, consistent metrics, and source transparency. Allowing multiple files introduces the negative risk that the Large Language Model (LLM) may hallucinate foreign keys or perform Cartesian products (cross joins) that artificially inflate numerical metrics, entirely destroying analytical trust. To mitigate this and amplify the Trust pillar, strict Explainable AI (XAI) metadata must be surfaced within the user interface. The system must explicitly reveal the exact SQL ON clauses used, proving the data lineage and demonstrating precisely how the files were connected.  
The Speed pillar requires near-instant responses without complex workflows. Multi-file architectures theoretically introduce latency due to increased parsing times and more complex query execution plans. However, the architectural foundation of the platform—an in-memory DuckDB instance—is optimized for vectorized execution and can handle multi-table queries with extreme efficiency. DuckDB's in-memory zero-copy integration with Pandas and Polars DataFrames allows the system to bypass disk input/output operations entirely during multi-file registration, ensuring that the latency introduced by relational complexity remains imperceptible to the end user.  
Finally, the organizational guidelines for the hackathon impose strict adherence to open-source compliance and the Developer Certificate of Origin (DCO) terms, referencing the Linux Foundation courses on open-source contribution in finance (LFD137) and beginner's guide to open-source software development (LFD102). LFD102 emphasizes strategic, legal, and collaboration practices, highlighting the necessity of modular, maintainable architectures. Expanding the architecture to support multiple files forces a necessary refactoring of the codebase into a more modular, robust structure, aligning perfectly with the advanced engineering practices advocated by the Linux Foundation and expected by the hackathon judges.

## **Value Assessment and Competitive Differentiation**

The inclusion of multi-file upload capabilities fundamentally alters the trajectory of the hackathon submission from a basic technological wrapper to an enterprise-grade analytical engine. The hackathon evaluation guidelines explicitly reward "Technical Depth" (Section 6), encouraging solutions that tackle advanced data pipelines and system complexity, while also requiring robust documentation of system architecture and data flow diagrams to help reviewers understand this complexity.  
A standard single-file Text-to-SQL application using an LLM API and a database backend is a solved problem in the current technological landscape. It demonstrates basic proficiency with API integrations but does not showcase advanced engineering or deep understanding of database mechanics. Transitioning to an autonomous relational query agent that can ingest an arbitrary number of unmapped files, dynamically deduce their relationships, construct valid relational algebra, and execute it locally without data egress demonstrates a profound degree of technical depth.

| Value Dimension | Impact of Multi-File Relational Architecture | Anticipated Scoring Advantage |
| :---- | :---- | :---- |
| **Algorithmic Complexity** | Moves beyond simple SELECT mapping to dynamic foreign-key inference and multi-table routing problem-solving. | High. Demonstrates advanced NLP and schema engineering not typically found in baseline submissions. |
| **State Management** | Requires transitioning from simple monolithic session variables to complex dictionary-based session states with cleanup lifecycles. | Medium. Showcases proficiency in Streamlit application lifecycles and memory optimization. |
| **Real-World Utility** | Mirrors actual corporate environments where dimensional data (product catalogs, employee rosters) is managed separately from transactional fact tables. | Very High. directly targets the "remove friction" mandate by eliminating external data-prep steps. |
| **Architectural Robustness** | Necessitates the implementation of pre-execution guardrails and Abstract Syntax Tree (AST) validators to handle complex join failures. | High. Fulfills the security and robust engineering requirements expected in financial sector open-source contributions. |

Effectively solving the multi-file architecture directly addresses the problem of fragmented organizational knowledge. Users are no longer burdened with understanding how vlookup or xlookup functions operate in Excel to bridge datasets before querying them. By offloading the relational mapping to the AI, the platform achieves the ultimate goal of "Seamless self-service intelligence". The risk-to-reward ratio strongly favors implementation, provided that strict engineering guardrails are established to maintain the operational speed and accuracy of the underlying models.

## **Comprehensive Architectural Implementation Blueprint**

To transition the existing single-file architecture to a multi-file paradigm without triggering regressions, systematic modifications are required across the entire orchestration pipeline. The current system relies on rigid single-variable assumptions, notably a DUCKDB\_TABLE\_NAME \= "data" constant, and assumes a strict one-to-one mapping between the user interface upload event and the database connection initialization. This paradigm must be dismantled and replaced with a dynamic, dictionary-driven state architecture.

### **1\. Configuration and Virtual Table Naming Strategy**

**Target Module:** src/config.py  
The hardcoded table name constraint must be eliminated entirely. When a user uploads multiple files, each file must be assigned a programmatic, SQL-compliant table name derived from its original filename. Injecting raw user filenames directly into SQL execution contexts introduces severe vulnerabilities, even when operating entirely in-memory, as special characters or spaces will inevitably cause DuckDB parser failures.  
The configuration module must be updated to include a robust text-slugification utility. SQL identifiers must be rigorously sanitized to prevent syntax errors and obscure SQL injection vectors. The standard and most reliable approach in Python involves utilizing Unicode normalization to decompose complex characters, followed by regular expressions to replace spaces and non-alphanumeric characters with underscores.  
Furthermore, standard SQL mandates that table identifiers cannot begin with numerical digits. The slugification algorithm must account for files named 2026\_sales\_data.csv by conditionally prepending alphabetical strings.  
`import re`  
`import unicodedata`

`def slugify_table_name(filename: str) -> str:`  
    `"""`  
    `Converts a raw filename into a safe, valid SQL table identifier.`  
    `Strips extensions, normalizes unicode, and replaces non-alphanumeric characters.`  
    `"""`  
    `# Isolate the core filename by dropping the extension`  
    `name = filename.rsplit('.', 1)`  
      
    `# Normalize unicode characters to their closest ASCII equivalents (e.g., naïve -> naive)`  
    `name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')`  
      
    `# Strip any remaining characters that are not alphanumeric, whitespace, or hyphens`  
    `name = re.sub(r'[^\w\s-]', '', name).strip().lower()`  
      
    `# Replace all whitespace and hyphens with single underscores`  
    `name = re.sub(r'[-\s]+', '_', name)`  
      
    `# Ensure the SQL identifier does not violate starting-character rules`  
    `if re.match(r'^[0-9]', name):`  
        `name = 'tbl_' + name`  
          
    `return name`

This utility guarantees that the downstream LLM will have access to clean, distinct, and syntactically valid table references, drastically reducing the probability of parser rejection during the execution phase.

### **2\. State Management and Interface Orchestration**

**Target Module:** app.py  
The Streamlit frontend currently captures a single file and stores a singular schema\_info and conn variable within the application session state. Streamlit executes via a reactive, top-down rerun model upon every user interaction; therefore, persistent memory structures are mandatory to prevent file data from being lost, re-processed repeatedly, or inducing memory leaks upon subsequent reruns.  
The primary widget, st.file\_uploader, must be modified to accept an array of files via the accept\_multiple\_files=True configuration parameter. The session state architecture must undergo a paradigm shift, transitioning from singular scalar variables to structured dictionaries keyed by the standardized SQL table names generated by the slugification utility.  
The implementation logic must follow a rigorous lifecycle pattern:

1. **State Initialization:** The application must initialize st.session\_state.datasets \= {} and st.session\_state.unified\_schema \= "" upon the first user visit.  
2. **Upload Handling via Callbacks:** To optimize performance and prevent blocking the main thread during heavy I/O operations, Streamlit callbacks should be utilized via the on\_change parameter. When the user modifies the uploader widget, the callback iterates over the list of UploadedFile objects.  
3. **Delta Processing:** For each uploaded file, the application computes its slugified table name. It then checks if this table already exists in the datasets dictionary. If it does not, it triggers the schema extraction module. This delta processing ensures that if a user uploads a third file, the application does not waste computational resources re-extracting schemas for the first two files.  
4. **Memory Cleanup:** Intelligent cleanup mechanisms are non-negotiable for stable architectures. If a user removes a file from the multi-uploader widget, the application must detect the deletion by comparing the current widget output with the keys in st.session\_state.datasets. It must subsequently drop the corresponding DataFrame from the dictionary to free up system memory and trigger an update to the unified\_schema string.

### **3\. Multi-Schema Extraction and Synthesis**

**Target Module:** src/schema\_extractor.py  
The current schema extraction module reads one file and generates a flat, uncontextualized string containing column names, types, and sample data. In a relational setting, the language model requires a unified Data Definition Language (DDL) representation that allows it to infer complex relationships—specifically Primary Keys and Foreign Keys—across different tables without explicit human instruction.  
The extraction function must be vectorized to iterate over the dictionary of active DataFrames. The output must structurally delineate each table to prevent the LLM from hallucinating column provenance or conflating distinct domains. Supplying the LLM with a massive, unorganized list of columns from multiple tables triggers "Lost in the Middle" attention degradation, confusing the routing logic.  
The resulting schema\_str should adopt a highly structured format that maximizes the LLM's attention mechanism on the relational boundaries. Furthermore, advanced implementations (often referred to as X-Linking components) actively scan the DataFrames during extraction to identify columns with identical names and highly overlapping data profiles across different tables, explicitly feeding these hints to the LLM.  
A recommended schema output format for injection into the prompt is as follows:  
DATABASE SCHEMA: The database contains 2 active tables.  
Table 1: sales\_data Source File: sales\_data.csv Rows: 15000 Columns:

* transaction\_id (BIGINT): Unique identifier. Samples:  
* product\_id (VARCHAR): Samples:  
* revenue (DOUBLE): Numeric range: min=5.0, max=1200.0  
* transaction\_date (TIMESTAMP): Samples: \['2026-01-01', '2026-01-02'\]

Table 2: product\_catalog Source File: product\_catalog.xlsx Rows: 45 Columns:

* product\_id (VARCHAR): Samples:  
* category (VARCHAR): Samples: \['Electronics', 'Apparel'\]  
* unit\_cost (DOUBLE): Numeric range: min=2.5, max=800.0

SYSTEM INFERRED JOIN KEYS:

* sales\_data.product\_id appears to map directly to product\_catalog.product\_id (100% type match).

Providing explicit structural boundaries and programmatically suggesting potential join keys heavily mitigates the risk of the model failing to discover the relational schema on its own, offloading the most error-prone aspect of Text-to-SQL tasks from the LLM to deterministic Python logic.

### **4\. Enhanced Prompt Engineering for Relational Queries**

**Target Module:** src/sql\_generator.py  
The existing prompt architecture instructs the LLM to query a single table generically named "data". This prompt must undergo a massive paradigm shift to support multi-table operations. The sql\_generator.py represents the most vulnerable point in the new architecture. Research indicates that models—particularly the open-weight Llama 3.3 70B architecture targeted by this implementation—suffer severe accuracy degradation when transitioning from basic single-table queries to complex multi-table Text-to-SQL tasks requiring JOINs.  
The system prompt must enforce strict adherence to standard SQL practices while accommodating DuckDB's specific dialect optimizations. The revised prompt instructions must mandate several absolute rules:

1. **Explicit Table Aliasing:** The model must use aliases for all tables (e.g., SELECT s.revenue, p.category FROM sales\_data s JOIN product\_catalog p ON s.product\_id \= p.product\_id). Omitting aliases leads to ambiguous column references when multiple tables share column names (e.g., id, created\_at), which causes fatal Binder Exceptions in DuckDB.  
2. **Strict Schema Binding:** The LLM must be explicitly forbidden from inventing tables, hallucinating columns, or assuming the existence of external data dimensions that were not explicitly provided in the unified schema string.  
3. **Optimal Join Utilization:** The LLM should be instructed to default to LEFT JOIN semantics when computing analytical aggregations. Relying on INNER JOIN operations frequently results in silent data loss if the dimension tables are incomplete, violating the Trust pillar by providing mathematically incorrect aggregations.

To leverage the Chain-of-Thought reasoning capabilities of the Groq Llama 3.3 70B Versatile model, the prompt must command the model to output its internal logic within designated XML tags prior to writing the SQL. The prompt should enforce a \<step\_by\_step\_logic\> block where the model explicitly states which tables it plans to query, identifies the exact overlapping columns to be used for the JOIN condition, and explains its filtering strategy before finally generating the \<sql\> block.

### **5\. In-Memory Database Execution and Registration**

**Target Modules:** src/sql\_executor.py and src/orchestrator.py  
The underlying analytical engine, DuckDB, is exquisitely engineered for this exact multi-file architecture. It natively allows the registration of multiple Pandas DataFrames, Polars DataFrames, or Apache Arrow objects as virtual tables within a single in-memory connection instance.  
The sql\_executor.py module must be refactored to iterate through the active datasets dictionary residing in the session state. Instead of executing a single static conn.register("data", df) command, the executor dynamically loops through all available datasets, registering each with its corresponding slugified table name.  
`import duckdb`

`def initialize_virtual_database(datasets_dict):`  
    `"""`  
    `Creates an in-memory DuckDB connection and registers all user-uploaded`   
    `DataFrames as highly optimized virtual tables.`  
    `"""`  
    `conn = duckdb.connect(database=':memory:')`  
      
    `# DuckDB utilizes replacement scans to query pandas dataframes`   
    `# directly from local python scope, but explicit registration is safer`  
    `for table_name, df in datasets_dict.items():`  
        `conn.register(table_name, df)`  
          
    `return conn`

A common concern in database engineering is concurrency. DuckDB utilizes Optimistic Concurrency Control (OCC) alongside Multi-Version Concurrency Control (MVCC). Because the application only issues SELECT statements—a constraint enforced rigorously by the Abstract Syntax Tree (AST) parsing blocklist in the existing architecture —executing complex multi-table joins will not create write-lock contention or threading issues. The tables operate purely as read-only virtual views mapped directly to the Python process memory space, enabling blistering query speeds without the latency associated with disk-based database ingestion.

### **6\. Answer Generation and Multi-Source XAI Citations**

**Target Module:** src/answer\_generator.py  
The conversational element of the platform must adapt to explain cross-relational logic. The Explainable AI (XAI) metadata built into the current platform is designed to cite a single source. When a user poses a complex breakdown question such as, "What makes up total sales by product category?", the plain English explanation generated by the secondary LLM call must transparently declare its sources to maintain user confidence.  
The prompt driving the answer\_generator.py module must receive the final generated SQL statement in addition to the result rows and the original question. It must be instructed to parse the FROM and JOIN clauses of the SQL string to synthesize accurate citation narratives.  
For example, the output should proactively state: *"This analysis was calculated by combining transactional data from the 'sales\_data.csv' file with categorical mappings from the 'product\_catalog.xlsx' reference table."* This fulfills the NatWest hackathon's "Trust" pillar by completely demystifying the cross-file calculations and demonstrating clear data lineage.

## **Empirical Risk Analysis and Mitigation Strategies**

While the theoretical value of a multi-file architecture is immense, expanding from strict single-table constraints to an unconstrained relational model introduces significant vectors for systemic failure. A critical evaluation of these risks dictates whether the feature should be implemented fully, constrained, or abandoned.

### **Model Competency and Multi-Table JOIN Degradation**

The most severe threat to the proposed architecture lies in the specific capabilities of the designated reasoning engine: Groq's Llama 3.3 70B model. While utilizing free-tier AI is a core constraint of the hackathon , open-weight models often struggle with complex relational algebra.  
Recent independent empirical benchmarks—such as the LLM SQL Generation Benchmark conducted by Tinybird—evaluated 19 state-of-the-art LLMs on Text-to-SQL tasks against a massive 200 million row dataset. The benchmark utilized 50 analytical questions to measure success rates, efficiency, and exactness (semantic correctness) using metrics like Jaccard Distance and Numeric RMSE.  
The results revealed deeply concerning metrics for the specific model architecture currently employed by the platform. While proprietary models like Anthropic's Claude 3.7 Sonnet and OpenAI's o4-mini achieved extremely high valid query generation rates (100%) and relatively high exactness scores (approaching 56 out of 100 on average) , the Llama 3.3 70B Instruct model ranked severely lower—placing 19th out of 19 models tested.

| Text-to-SQL Benchmark Metric | Claude 3.7 Sonnet | OpenAI o4-mini | Llama 3.3 70B |
| :---- | :---- | :---- | :---- |
| **Valid Query Execution Rate** | 100% | 100% | \~66% |
| **First Attempt Success Rate** | \>90% | \~88-92% | 52% |
| **Average Exactness Score** | \~52-56 | \~51-55 | 35.56 |
| **Cost Profile per 1000 Queries** | $5.97 | $0.64 | Free Tier / $5.25 |

The empirical data proves that when tasked with identifying foreign keys and writing multi-table JOIN operations, the Llama 3.3 70B model frequently generates invalid syntax or mathematically incorrect associations. The low 52% first-attempt success rate means that half of the queries generated for cross-file analysis will fail to execute or produce hallucinations on the first pass.

### **The "Bouncer" Guardrail and Self-Correction Loops**

To safely utilize Llama 3.3 70B for relational queries, the system must employ robust validation pipelines that anticipate failure. The existing sql\_executor.py already uses an Abstract Syntax Tree (AST) parser to block destructive commands. This mechanism must be dramatically expanded to serve as a pre-execution "Bouncer".  
Text-to-SQL fails quietly; models frequently write syntax that executes perfectly but returns incorrect numbers due to faulty join logic. If the model generates an invalid join (e.g., attempting to join on strings and integers without appropriate CAST functions) or references a non-existent column, DuckDB will throw an exception. The Bouncer must catch this database driver exception (duckdb.BinderException or duckdb.ParserException). Instead of surfacing a raw error trace to the user—which destroys the Clarity pillar —the Bouncer must automatically trigger an autonomous self-correction loop.  
The system feeds the exact database error message back into the LLM prompt history, instructing it to evaluate its mistake and attempt a revision. Because Groq's specialized inference hardware (LPU) provides unprecedented token generation speeds (up to 1600 tokens per second ), an automated, hidden retry loop will still complete its full cycle well within the mandated 3-second user latency constraint.

### **Prompt Token Expansion and Context Window Constraints**

Uploading multiple files exponentially increases the size of the injected schema payload, particularly if extensive statistical profiling data (minimums, maximums, distinct categorical value arrays) is appended for every column across every table.  
A rigorous analysis of the Groq Llama-3.3-70b-versatile architecture demonstrates a massive context window limit of 131,072 tokens. Consequently, raw token limits are not a technical constraint; the system can easily ingest DDL strings for hundreds of tables simultaneously without triggering an API rejection.  
However, modern language models suffer from a documented phenomenon known as "Lost in the Middle" attention degradation. While the context window is large, the model's ability to retrieve and reason over information located in the center of a massive prompt drops significantly. When provided with the schemas of ten massive uploaded files, the LLM will struggle to decipher which specific tables are actually relevant to a brief user query. This dilution of context leads directly to massive, inefficient cross-joins or hallucinations.  
The schema\_extractor.py must aggressively prune the volume of sample values injected per column. The system must prioritize sending column names and types, limiting categorical sample injections only to highly variable text fields, thereby keeping the context window dense, highly relevant, and focused entirely on structural relationships.

### **Architectural Complexity and State Regressions**

Modifying the fundamental data structure from a singular scalar df variable to a collection of DataFrames introduces critical state-management regression risks. If a user modifies a file locally but keeps the identical filename, and then uploads it a second time, the slugify\_table\_name function will create a namespace collision within the DuckDB registry. The orchestrator must be programmed to safely overwrite existing virtual tables when filename collisions occur.  
Furthermore, executing multi-table joins on arbitrary user datasets—which inherently lack standardized naming conventions and frequently exhibit mismatched data types (e.g., a zip code stored as an INTEGER in one file and a VARCHAR in another)—has a high probability of yielding null result sets. A user executing a query like "Compare sales vs marketing spend" might receive an empty chart because the underlying date fields could not be matched. This explicitly violates the "Trust" pillar , requiring the platform to implement sophisticated ambiguity detectors that warn the user when a cross-file query yields zero rows.

## **Strategic Alternatives and Delivery Recommendations**

Given the documented frailties of the Llama 3.3 70B inference engine when executing unconstrained relational mappings , several architectural compromises could deliver a semblance of multi-file operations while insulating the system from catastrophic failure modes.

### **Alternative 1: Automated Data Merging (Single-Table Abstraction)**

Rather than forcing the LLM to write complex SQL containing JOINs, the application could employ Pandas to auto-merge the files chronologically or horizontally *before* registering the table with DuckDB.  
If the uploaded files share identical schemas (e.g., January\_Sales.csv and February\_Sales.csv), the schema\_extractor.py could detect the symmetry and execute an automated pd.concat(). If they share a highly obvious index column (e.g., Customer\_ID), Pandas could perform an automated outer merge. The LLM is then presented with a single, massive, flattened table, bypassing the need for it to generate JOIN clauses.  
**Verdict:** This approach is highly fragile. Inferring the correct relational algebra (outer versus inner joins) via static Python logic without understanding the specific nuance of the user's natural language question inevitably destroys data integrity. Auto-concatenation is safe only for strictly identical file structures, severely limiting the analytical depth required by the complex hackathon use cases.

### **Alternative 2: Isolated Query Sandboxes (The Dropdown Method)**

The application accepts multiple files via the Streamlit multi-uploader, but the user interface includes a strict dropdown labeled "Select dataset to query."  
When the user selects sales.csv from the dropdown, the application only passes the schema for that specific file to the LLM. The underlying architecture remains a single-table execution, but the user has the convenience of loading multiple files into memory at once.  
**Verdict:** This alternative completely neuters the cross-relational power of the system. While it technically satisfies the semantic definition of "working with datasets" (plural) , it entirely prevents users from asking critical decomposition questions like "Why did revenue drop compared to the marketing spend in the other file?" It minimizes technical depth and provides almost zero competitive differentiation over a basic single-file platform.

### **Alternative 3: The Intermediate "Simplified Schema" Agentic Pipeline**

Instead of forcing the LLM to process complex schemas and write complex SQL containing JOINs in a single pass, the system utilizes a multi-agent workflow paradigm (similar to LangGraph or X-SQL architectures).  
First, a lightweight LLM call maps the natural language query to the relevant tables and determines the optimal connection keys based on a simplified abstract schema. The orchestration layer then constructs a dynamically "flattened" view within DuckDB based on those instructions. A second LLM call is then tasked with writing a simple SELECT statement against this flattened, single-table view.  
**Verdict:** While theoretically the most robust method for handling schema complexity , chaining multiple sequential LLM calls adds massive compounding latency. To maintain the mandated sub-3-second response time required by the Speed pillar , the architecture must avoid deep serial LLM dependency chains.

### **Final Recommendation: The Constrained Relational MVP**

The multi-file upload capability is incontrovertibly in scope and represents a high-value competitive differentiator for the hackathon submission. The technical depth required to parse disparate schemas, slugify namespaces safely, and orchestrate DuckDB virtual tables directly addresses the judging criteria.  
However, the documented statistical limitations of the Groq Llama 3.3 70B inference engine on multi-table relational SQL tasks represent an acute threat to the system's operational stability.  
The development team should pursue the multi-file architecture using a **Constrained Relational MVP** approach to aggressively mitigate risk while maximizing the technical evaluation score. The recommended implementation strategy is as follows:

1. **Execute the File-by-File Blueprint:** Implement the config.py slugification logic, the app.py dictionary state management system, and the sql\_executor.py looped DuckDB registration exactly as detailed in the comprehensive architectural blueprint section of this report.  
2. **Impose a Strict File Limit:** Cap the st.file\_uploader widget to a maximum of three concurrent datasets. This decisively prevents context window attention dilution and mathematically restricts the complexity of potential join permutations, vastly improving the LLM's baseline accuracy and semantic exactness.  
3. **Deploy Deterministic Relationship Profiling:** Do not rely on the language model to blindly guess join keys. Enhance the Python-based schema\_extractor.py to deterministically identify columns with identical names and overlapping data types across the uploaded dataframes. Hardcode these explicit hints directly into the system prompt structure (e.g., *"System Note: 'sales.client\_id' and 'clients.client\_id' share a 100% data type match. Prioritize these for relational JOIN operations."*).  
4. **Implement the Error-Correction Bouncer:** Utilize Groq's extreme throughput capabilities to mask intermediate failures from the user. Wrap the DuckDB execution sequence in a strict try/except block. If a multi-table query throws a database execution exception, catch the error, append it silently to the prompt history, and execute an immediate rapid retry. If the retry fails, fallback gracefully by informing the user that the files lack a mathematically clear relationship.  
5. **Amplify UI Transparency for XAI:** When multiple files are actively detected in the session state, the interface must deploy a prominent "Data Lineage" expander widget. If the executed SQL contains any relational clause, the UI must visually display the specific files joined and the exact keys utilized by the engine, ensuring the solution complies flawlessly with the Explainable AI (XAI) and Trust directives of the NatWest hackathon.

By adopting this phased, guardrail-protected approach, the system unlocks the immense analytical value of cross-file queries without succumbing to the hallucination mechanics inherent in free-tier open-weight language models. This strategic execution delivers an enterprise-grade, highly verifiable conversational intelligence platform capable of fundamentally changing how non-technical users interact with complex organizational data.

#### **Works cited**

1\. I built a specific-domain Text-to-SQL Agent using Llama-3-70B (via Groq). It handles Railway IoT logs with 96% accuracy using strict schema binding and a custom 'Bouncer' guardrail \- Reddit, https://www.reddit.com/r/LocalLLaMA/comments/1q12lzm/i\_built\_a\_specificdomain\_texttosql\_agent\_using/ 2\. Concurrency \- DuckDB, https://duckdb.org/docs/current/connect/concurrency.html 3\. Data Ingestion \- DuckDB, https://duckdb.org/docs/current/clients/python/data\_ingestion 4\. Python API \- DuckDB, https://duckdb.org/docs/current/clients/python/overview.html 5\. python-slugify \- PyPI, https://pypi.org/project/python-slugify/ 6\. Issue 11685: possible SQL injection into db APIs via table names... sqlite3 \- Python tracker, https://bugs.python.org/issue11685 7\. slug \- String slugification in Python \- Stack Overflow, https://stackoverflow.com/questions/5574042/string-slugification-in-python 8\. Turn a string into a valid filename? \- python \- Stack Overflow, https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename 9\. Session State \- Streamlit Docs, https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session\_state 10\. How to keep my uploaded file while navigating to different pages and refreshing the web app, https://discuss.streamlit.io/t/how-to-keep-my-uploaded-file-while-navigating-to-different-pages-and-refreshing-the-web-app/63833 11\. FileUploader uploads file multiple times · Issue \#7097 \- GitHub, https://github.com/streamlit/streamlit/issues/7097 12\. st.file\_uploader \- Streamlit Docs, https://docs.streamlit.io/develop/api-reference/widgets/st.file\_uploader 13\. How to maintain session state with multiple file uploads one after another? \- Using Streamlit, https://discuss.streamlit.io/t/how-to-maintain-session-state-with-multiple-file-uploads-one-after-another/54863 14\. X-SQL: Expert Schema Linking and Understanding of Text-to-SQL with Multi-LLMs \- arXiv, https://arxiv.org/html/2509.05899v1 15\. Text-to-SQL with extremely complex schema : r/LangChain \- Reddit, https://www.reddit.com/r/LangChain/comments/1amlftk/texttosql\_with\_extremely\_complex\_schema/ 16\. Context Length in LLMs: Optimize Business AI Performance | Groq is fast, low cost inference., https://groq.com/blog/the-crucial-role-of-context-length-in-large-language-models-for-business-applications 17\. \\methodName: Enhancing Multi-Table Text-to-SQL Generation via Schema Simplification, https://arxiv.org/html/2505.18122v1 18\. Which LLM writes the best analytical SQL? \- Tinybird, https://www.tinybird.co/blog/which-llm-writes-the-best-sql 19\. FROM and JOIN Clauses \- DuckDB, https://duckdb.org/docs/current/sql/query\_syntax/from 20\. Build a LangChain SQL Agent with DuckDB and MotherDuck, https://motherduck.com/blog/langchain-sql-agent-duckdb-motherduck 21\. SQL Introduction \- DuckDB, https://duckdb.org/docs/current/sql/introduction 22\. Whats the difference in these DuckDB joins : r/SQL \- Reddit, https://www.reddit.com/r/SQL/comments/1g9vvih/whats\_the\_difference\_in\_these\_duckdb\_joins/ 23\. Llama-3.3-70B-Versatile \- GroqDocs, https://console.groq.com/docs/model/llama-3.3-70b-versatile 24\. Text-to-SQL Errors and Fixes: Why Systems Still Fail \- August Infotech, https://www.augustinfotech.com/blogs/text-to-sql-ai-failures-vs-fixes-a-short-guide/ 25\. LLM-Based SQL Generation: Prompting, Self-Refinement, and Adaptive Weighted Majority Voting \- arXiv, https://arxiv.org/html/2601.17942v1 26\. System Prompts & LLM \- Models \- Hugging Face Forums, https://discuss.huggingface.co/t/system-prompts-llm/173290 27\. Llama-3.3-70B-SpecDec \- GroqDocs \- Groq Console, https://console.groq.com/docs/model/llama-3.3-70b-specdec 28\. Connect and use Llama 3.3 70B Versatile from Groq with API Key \- TypingMind, https://www.typingmind.com/guide/groq/llama-3.3-70b-versatile 29\. The Six Failures of Text-to-SQL (And How to Fix Them with Agents) | by Karl Weinmeister | Google Cloud \- Medium, https://medium.com/google-cloud/the-six-failures-of-text-to-sql-and-how-to-fix-them-with-agents-ef5fd2b74b68