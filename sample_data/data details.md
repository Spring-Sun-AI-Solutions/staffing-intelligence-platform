# Staffing Intelligence Platform — Data Dictionary

Complete reference for every data entity in the platform: storage type, keys, consumers, and business outcomes.

---
![System Architecture](staffing_platform_architecture.jpg)

---
## Summary table

| Data Entity | Type | Primary Key | Used By | End Result |
|-------------|------|-------------|---------|------------|
| Users | PostgreSQL | `id` | streamlit-authenticator, sidebar routing | Correct pages shown per role; secure login |
| Candidates | PostgreSQL | `id` | Matcher, parser, attrition model, RAG index | Ranked candidates, attrition alerts, searchable talent pool |
| Jobs | PostgreSQL | `id` | Matcher, JD tools, RAG index | Job-candidate matches, cleaned job descriptions |
| Clients | PostgreSQL | `id` | Churn model, margin analysis, RAG index | Churn warnings, account health visibility |
| Recruiters | PostgreSQL | `id` | KPI queries, activity recommender | Performance leaderboard, daily priority list |
| Placements | PostgreSQL | `id` | Funnel analytics, submission model, margin analysis | Conversion metrics, placement predictions |
| Timesheets | PostgreSQL | `id` | Anomaly detector, bench cost query | Flagged fraud / duplicates, billing leak prevention |
| Payroll | PostgreSQL | `id` | Revenue forecast, margin leakage | 12-month revenue projection, low-margin alerts |
| Predictions | PostgreSQL | `id` | All ML models (write), dashboards (read) | Historical scoring record, model drift tracking |
| Resume embeddings | pgvector | `candidates.id` | Matcher cosine similarity, RAG retrieval | Semantic candidate matching beyond keywords |
| Job embeddings | pgvector | `jobs.id` | Matcher cosine similarity | Semantic job-candidate similarity score |
| Match cache | Redis | `match:job_{id}` | Job match page | Sub-second page reload instead of re-scoring |
| Chat history | Redis | `chat:{session_id}` | AI assistant | Multi-turn conversation memory |
| Scheduler log | Redis | `job_last_run:{name}` | Admin monitoring | Confirmation nightly jobs ran |
| Placement funnel | DuckDB | aggregate | Funnel chart, executive summary | Stage-by-stage conversion percentages |
| Recruiter KPIs | DuckDB | aggregate | Performance page | Leaderboard ranking and conversion rates |
| Revenue by client | DuckDB | aggregate | Revenue forecast, executive summary | Client revenue trends over time |
| Margin leakage | DuckDB | aggregate | Margin leakage page | List of accounts operating below threshold |
| Bench cost | DuckDB | aggregate | Margin analysis | Idle contractor cost exposure |
| Submission model | ML file | n/a | Job match page | Interview / hire probability per submission |
| Attrition model | ML file | n/a | Attrition risk page | Early warning for contractor exits |
| Churn model | ML file | n/a | Client churn page | Proactive account management triggers |
| Anomaly model | ML file | n/a | Timesheet page | Fraud and billing error detection |
| Resume files | Disk | file path | Parser, candidate profile | Structured data extracted from unstructured docs |
| Training resumes | Disk | file path | Batch importer | Populated candidate database from real files |
| RAG index | Disk | doc IDs | AI assistant | Grounded answers with source citations |
| MLflow runs | Disk | run ID | Model training | Reproducible experiments, metric comparison |
| DuckDB file | Disk | n/a | Analytics queries | Fast aggregation without hitting Postgres |
| Log files | Disk | n/a | Debugging, monitoring | Traceable errors and slow operation detection |

---

## Storage layers

| Layer | Technology | What lives here | Persistence |
|-------|-----------|-----------------|-------------|
| Relational core | PostgreSQL 16 | 9 tables — all structured business data | Permanent |
| Vector search | pgvector extension | 384-dim embeddings on candidates + jobs | Permanent |
| Analytics | DuckDB | Aggregate queries reading live from Postgres | Cached, rebuilt nightly |
| Cache | Redis 7 | Query results, chat history, job timestamps | Ephemeral (TTL 3 min – 2 days) |
| LLM inference | Ollama | Llama 3 model weights | Docker volume |
| Model artefacts | Local disk | 4 trained `.pkl` files | Permanent, regenerable |
| File storage | Local disk | Resumes, RAG index, MLflow runs, logs | Permanent |

---

## PostgreSQL schema detail

### `users`
Platform login accounts.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `username` | varchar(64) | Unique, indexed |
| `name` | varchar(128) | Display name |
| `email` | varchar(256) | Unique |
| `role` | enum | `recruiter` \| `manager` \| `exec` \| `compliance` |
| `is_active` | boolean | Soft delete flag |

### `candidates`
Candidate profiles, mostly populated by the resume parser.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `name`, `email`, `phone` | varchar | Contact details |
| `skills` | text[] | Normalised skill names |
| `visa_status` | enum | `citizen` \| `gc` \| `h1b` \| `opt` \| `stem_opt` \| `ead` \| `unknown` |
| `location` | varchar(128) | City, State format |
| `yoe` | float | Years of experience |
| `rate` | float | Desired hourly rate |
| `resume_path` | varchar(512) | Path to file on disk |
| `resume_text` | text | Extracted plain text |
| `embedding` | vector(384) | pgvector semantic embedding |
| `is_active_contractor` | boolean | Currently placed |
| `tenure_days` | integer | Attrition signal |
| `comms_gap_days` | integer | Attrition signal |
| `overtime_pct` | float | Attrition signal |
| `client_feedback_score` | float | Attrition signal (0–5) |
| `attrition_risk_score` | float | ML output (0–1) |

### `jobs`
Open requisitions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `client_id` | integer | FK → clients |
| `title` | varchar(256) | Job title |
| `jd_text` | text | Full job description |
| `required_skills` | text[] | Required skills list |
| `location`, `remote_ok` | varchar, boolean | Location matching |
| `rate_min`, `rate_max` | float | Budget range |
| `visa_requirement` | enum | Null = no restriction |
| `min_yoe`, `max_yoe` | float | Experience window |
| `status` | enum | `open` \| `on_hold` \| `filled` \| `closed` |
| `embedding` | vector(384) | pgvector semantic embedding |

### `clients`
Staffing client accounts.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `name`, `industry` | varchar | Account identity |
| `contact_name`, `contact_email` | varchar | Primary contact |
| `status` | varchar(32) | `active` \| `inactive` \| `churned` |
| `req_volume` | integer | Active requisition count |
| `margin_pct` | float | Average margin across placements |

### `recruiters`
Internal recruiters.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `user_id` | integer | FK → users (optional link to login) |
| `name`, `email`, `team` | varchar | Recruiter identity |

### `placements`
Central join table — candidate submitted to a job.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `candidate_id` | integer | FK → candidates |
| `job_id` | integer | FK → jobs |
| `recruiter_id` | integer | FK → recruiters |
| `client_id` | integer | FK → clients |
| `stage` | enum | `submitted` \| `interview` \| `offer` \| `hire` \| `rejected` |
| `match_score` | float | Composite score 0–100 |
| `skill_gap` | json | `{missing: [], severity: ""}` |
| `bill_rate`, `pay_rate`, `margin` | float | Financials |
| `submitted_at` | timestamp | Funnel timing |

### `timesheets`
Weekly hours per active contractor.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `contractor_id` | integer | FK → candidates |
| `week_start` | date | Monday of the week |
| `hours`, `overtime_hours` | float | Logged time |
| `status` | enum | `pending` \| `approved` \| `rejected` \| `flagged` |
| `anomaly_flag` | boolean | Set by anomaly detector |
| `anomaly_score` | float | Isolation Forest score |
| `anomaly_reason` | varchar(256) | Human-readable explanation |

### `payroll`
Monthly billing per contractor.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `contractor_id` | integer | FK → candidates |
| `period` | date | First day of month |
| `bill_rate`, `pay_rate` | float | Client bill vs contractor pay |
| `margin`, `margin_pct` | float | Profit per hour and percentage |

### `predictions`
Polymorphic store for all ML model outputs.

| Column | Type | Notes |
|--------|------|-------|
| `id` | integer | Primary key |
| `entity_type` | varchar(32) | `candidate` \| `client` \| `placement` |
| `entity_id` | integer | ID of the scored entity |
| `model_name` | varchar(64) | Which model produced this |
| `score` | float | Prediction output |
| `features` | json | Input features, for explainability |
| `created_at` | timestamp | For drift tracking |

---

## Redis key patterns

| Key pattern | Value | TTL | Purpose |
|-------------|-------|-----|---------|
| `sip:match:job_{id}` | Ranked candidate list (JSON) | 3 min | Avoid re-scoring on page reload |
| `sip:chat:{session_id}` | Message array `[{role, content}]` | 1 hour | AI assistant conversation memory |
| `sip:job_last_run:{name}` | ISO timestamp | 2 days | Scheduler health monitoring |
| `sip:{query_key}` | Serialised query result | 5 min | General page caching |

---

## DuckDB analytics queries

| Function | Source tables | Output |
|----------|--------------|--------|
| `get_placement_funnel()` | placements | Stage counts and conversion percentages |
| `get_recruiter_kpis()` | recruiters, placements | Submissions, interviews, placements, conversion rate |
| `get_revenue_by_client()` | payroll, placements, clients | Monthly revenue and headcount per client |
| `get_margin_leakage()` | payroll, placements, clients | Accounts below margin threshold |
| `get_bench_cost()` | candidates, timesheets | Idle contractors and weekly cost exposure |

---

## ML model files

| File | Algorithm | Input features | Output |
|------|-----------|----------------|--------|
| `submission_success.pkl` | XGBoost classifier | match score, skill overlap, visa, YOE, rate, location | Interview / shortlist / hire probability |
| `attrition_risk.pkl` | XGBoost classifier | tenure, comms gap, overtime %, feedback score | Exit risk 0–1 |
| `client_churn.pkl` | LightGBM classifier | req volume trend, response time, margin, rejection rate | Churn risk 0–1 |
| `timesheet_anomaly.pkl` | PyOD Isolation Forest | hours z-score, overtime ratio, duplicate flags | Anomaly score |

---

## File storage layout

```
data/
├── uploads/
│   ├── resumes/          # Uploaded via UI, path stored in candidates.resume_path
│   └── training/         # Sample resumes for batch import and parser testing
│       └── _manifest.json  # Ground truth for test assertions
├── models/               # 4 trained .pkl files (gitignored)
├── index/                # LlamaIndex vector store for RAG
├── mlruns/               # MLflow experiment tracking (gitignored)
└── analytics.duckdb      # DuckDB embedded database (gitignored)

logs/
├── app.log               # Root logger catch-all
├── ml.log                # Parser, embedder, matcher, predictor
├── data.log              # Scheduler, file store, DuckDB, Redis
├── events.log            # Structured analytics events
└── slow_ops.log          # Operations exceeding 1 second
```

---

## Generating dummy data

Populate every data source at once:

```bash
python -m scripts.generate_dummy_data --reset
```

Run individual steps:

```bash
python -m scripts.generate_dummy_data --only postgres
python -m scripts.generate_dummy_data --only resumes,embeddings
python -m scripts.generate_dummy_data --skip index,models
```

Available steps: `postgres`, `resumes`, `embeddings`, `models`, `redis`, `duckdb`, `index`, `logs`

Default volumes: 80 candidates, 30 jobs, 12 clients, 6 recruiters, 150 placements, 16 weeks of timesheets per active contractor, 6 months of payroll, 18 sample resume files.
