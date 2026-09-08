# 🧠 Staffing Intelligence Platform

An end-to-end AI system for recruiter productivity, placement intelligence, client analytics, compliance, and revenue forecasting.

**100% open source · 100% Python · Local install · No cloud required**

---

## What it does

| Module | Features |
|--------|----------|
| 🔍 **Talent Intelligence** | Resume–job matching, submission success prediction, attrition risk, resume parsing |
| 📈 **Sales & Client** | Revenue forecasting, client churn prediction, rate optimisation |
| 🤖 **Recruiter AI** | Performance KPIs, activity recommender, AI assistant chatbot |
| 🛂 **Compliance** | Visa expiry tracker, timesheet anomaly detection |
| 📊 **Executive BI** | Placement funnel, margin leakage analysis |

---

## Tech stack

| Layer | Tools |
|-------|-------|
| UI | Streamlit, Plotly, streamlit-aggrid |
| ML | XGBoost, LightGBM, Prophet, PyOD, MLflow |
| NLP | spaCy, sentence-transformers, LlamaIndex, Ollama (Llama 3) |
| Data | PostgreSQL + pgvector, DuckDB, Redis |
| Infra | Docker Compose, Alembic, APScheduler |

---

## Before you start — read this first

Two things cause most setup failures. Getting them right up front saves an hour.

### ⚠️ macOS: do NOT clone into Desktop, Documents, or Downloads

macOS sandboxes these folders (TCC protection). Docker cannot mount files from
them and Postgres will fail to start with:

```
Error response from daemon: error while creating mount source path
'/host_mnt/Users/you/Desktop/...': operation not permitted
```

**Clone into your home directory instead:**

```bash
cd ~                     # ✅ /Users/you/staffing-intelligence-platform
# NOT ~/Desktop          # ❌ will fail
```

### ⚠️ Never move the project folder after setup

Python virtual environments hardcode absolute paths. Moving the folder breaks
`.venv` with `bad interpreter: no such file or directory`. If you must move it,
delete and recreate the venv afterwards (see Troubleshooting).

---

## Prerequisites

| Tool | Version | Check with |
|------|---------|-----------|
| Docker Desktop | Latest, **running** | `docker --version` |
| Python | 3.10 – 3.12 | `python3 --version` |
| Git | Any | `git --version` |

Docker Desktop must be **open and running**, not just installed. The whale icon
in your menu bar should be steady, not animating.

**Disk space:** ~8 GB (5 GB of that is the Llama 3 model, which is optional).

---

## Quick start

Nine steps. Each one either works or tells you exactly what's wrong.

### 1. Clone into your home directory

```bash
cd ~
git clone https://github.com/YOUR_ORG/staffing-intelligence-platform
cd staffing-intelligence-platform
```

### 2. Create the environment file

```bash
cp .env.example .env
```

Defaults work for local development. No edits needed to get started.

### 3. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
```

Your prompt should now start with `(.venv)`. **Every command below assumes the
venv is active.** If you open a new terminal, re-run the `source` line.

### 4. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt --timeout 300 --retries 10
python -m spacy download en_core_web_sm
```

This pulls ~1.5 GB including PyTorch. Expect 5–15 minutes.

> **If it times out:** pip caches partial downloads, so just re-run the same
> command — it resumes where it stopped. On a slow connection, install the
> largest package on its own first: `pip install torch --timeout 600 --retries 20`

### 5. Start the data services

```bash
docker compose up -d
docker compose ps
```

All three containers must show `Up`:

```
sip_postgres   pgvector/pgvector:pg16   Up
sip_redis      redis:7-alpine           Up
sip_ollama     ollama/ollama:latest     Up
```

> **If `sip_postgres` is missing or restarting:** you are almost certainly in a
> protected folder. See the macOS warning above.

### 6. Create the database schema

```bash
alembic upgrade head
```

Expected output ends with:

```
Running upgrade 001_users -> 002_core_tables, create core tables: ...
```

### 7. Load the sample data

```bash
docker compose exec -T postgres psql -U sip -d staffing < sample_data/sql/seed_data.sql
```

Then copy the supporting artefacts into place:

```bash
mkdir -p data/models data/uploads/training data/fixtures logs
cp sample_data/models/*     data/models/
cp sample_data/resumes/*    data/uploads/training/
cp sample_data/fixtures/*   data/fixtures/
cp sample_data/logs/*       logs/
cp sample_data/analytics.duckdb data/
cp sample_data/load_redis_fixtures.py scripts/

python scripts/load_redis_fixtures.py
```

### 8. Generate embeddings

```bash
python -c "
from ml.embedder import embed_all_candidates, embed_all_jobs
print('candidates:', embed_all_candidates())
print('jobs:', embed_all_jobs())
"
```

Downloads a 22 MB model on first run, then takes about 30 seconds.
Expect `candidates: 80` and `jobs: 30`.

### 9. Launch

```bash
streamlit run app.py
```

Open **http://localhost:8501**

| Username | Password | Role |
|----------|----------|------|
| `recruiter1` | `recruit123` | Recruiter |
| `manager1` | `manage123` | Manager |
| `exec1` | `exec123` | Executive |
| `compliance1` | `comply123` | Compliance |

> Change these before any real use. See [docs/setup.md](docs/setup.md).

---

## Verify your install

```bash
docker compose exec postgres psql -U sip -d staffing -c "
SELECT 'candidates' t, COUNT(*) FROM candidates
UNION ALL SELECT 'jobs',        COUNT(*) FROM jobs
UNION ALL SELECT 'clients',     COUNT(*) FROM clients
UNION ALL SELECT 'placements',  COUNT(*) FROM placements
UNION ALL SELECT 'timesheets',  COUNT(*) FROM timesheets
UNION ALL SELECT 'payroll',     COUNT(*) FROM payroll
UNION ALL SELECT 'predictions', COUNT(*) FROM predictions;
"
```

| Table | Expected |
|-------|----------|
| candidates | 80 |
| jobs | 30 |
| clients | 12 |
| placements | 150 |
| timesheets | 624 |
| payroll | 234 |
| predictions | 92 |

```bash
# Embeddings written?
docker compose exec postgres psql -U sip -d staffing -c \
  "SELECT COUNT(*) FROM candidates WHERE embedding IS NOT NULL;"   # → 80

# Redis loaded?
docker compose exec redis redis-cli KEYS 'sip:*' | wc -l           # → 15

# Models in place?
ls data/models/                                                     # → 4 .pkl files
```

---

## Optional: enable the AI Assistant

Every other page works without this. The assistant needs a local LLM.

```bash
docker compose exec ollama ollama pull llama3     # ~4.7 GB
python -c "from ml.assistant import build_index; build_index(force=True)"
```

Lighter alternative — `mistral` is ~4.1 GB and works well here:

```bash
docker compose exec ollama ollama pull mistral
# then set OLLAMA_MODEL=mistral in .env
```

---

## Daily use

```bash
cd ~/staffing-intelligence-platform
source .venv/bin/activate
docker compose up -d
streamlit run app.py
```

Stopping:

```bash
# Ctrl+C to stop Streamlit
docker compose down          # stop services, keep data
docker compose down -v       # ⚠️ also deletes all data
```

---

## Troubleshooting

<details>
<summary><strong>Postgres won't start — "operation not permitted"</strong></summary>

The project is in a macOS-protected folder (Desktop, Documents, Downloads).

```bash
cd ~
mv ~/Desktop/staffing-intelligence-platform ~/staffing-intelligence-platform
cd ~/staffing-intelligence-platform
rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose down && docker compose up -d
```
</details>

<details>
<summary><strong>"No module named 'db'" or "No module named 'ml'"</strong></summary>

You are not in the project root, or the venv is inactive.

```bash
cd ~/staffing-intelligence-platform
source .venv/bin/activate
```

Run scripts as modules from the root, not from inside their folder:

```bash
python -m scripts.some_script     # ✅
cd scripts && python some_script.py   # ❌
```
</details>

<details>
<summary><strong>"No module named 'pgvector'"</strong></summary>

```bash
pip install pgvector
```
</details>

<details>
<summary><strong>Migration fails: type "visastatusenum" already exists</strong></summary>

Partial migration left enums behind. Reset and retry:

```bash
docker compose exec postgres psql -U sip -d staffing \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
alembic upgrade head
```
</details>

<details>
<summary><strong>"bad interpreter: no such file or directory"</strong></summary>

The folder moved after the venv was created. Recreate it:

```bash
deactivate 2>/dev/null
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
</details>

<details>
<summary><strong>"Port 8501 is not available"</strong></summary>

```bash
lsof -ti:8501 | xargs kill -9
streamlit run app.py
```
</details>

<details>
<summary><strong>Container name already in use</strong></summary>

Left over from a previous location or project name:

```bash
docker rm -f sip_postgres sip_redis sip_ollama
docker network rm sip_network
docker compose up -d
```
</details>

<details>
<summary><strong>pip install times out</strong></summary>

Re-run the same command — pip resumes from cache:

```bash
pip install -r requirements.txt --timeout 300 --retries 10
```

Or isolate the biggest package first:

```bash
pip install torch --timeout 600 --retries 20
```
</details>

<details>
<summary><strong>A page shows KeyError or a column is missing</strong></summary>

Streamlit caches imported modules. After editing any `.py` file outside
`pages/`, do a full restart rather than a browser refresh:

```bash
# Ctrl+C, then
streamlit run app.py
```
</details>

<details>
<summary><strong>Reset everything and start over</strong></summary>

```bash
docker compose down -v
docker compose up -d
sleep 10
alembic upgrade head
docker compose exec -T postgres psql -U sip -d staffing < sample_data/sql/seed_data.sql
python scripts/load_redis_fixtures.py
python -c "from ml.embedder import embed_all_candidates, embed_all_jobs; embed_all_candidates(); embed_all_jobs()"
```
</details>

---

## Project structure

```
staffing-intelligence-platform/
├── app.py                  Streamlit entry point + auth
├── pages/                  15 UI pages, one per feature
├── ml/                     Matcher, predictors, forecaster, parser, LLM
├── db/                     SQLAlchemy models, queries, migrations
├── data/                   Uploads, models, fixtures, DuckDB
├── sample_data/            Pre-generated demo data
├── scripts/                Utilities and loaders
├── tests/                  Pytest suite
├── logs/                   Structured JSON logs
└── docker-compose.yml      Postgres, Redis, Ollama
```

Full reference: [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)

---

## Running tests

```bash
pytest tests/ -v                          # everything
pytest tests/test_sprint4.py -v           # one sprint
pytest tests/ -v -m "not ollama"          # skip tests needing the LLM
```

---

## A note on the bundled models

The four `.pkl` models in `sample_data/models/` are trained on **synthetic**
feature distributions, not real placement outcomes. Their AUC figures
(0.91–0.96) measure how well they learned the generator's rules — not
real-world predictive power.

They are fine for demos, UI work, and integration testing. Retrain on real
historical data before operational use:

```python
from ml.predictor import retrain_all_models
retrain_all_models()
```

---

## License

MIT