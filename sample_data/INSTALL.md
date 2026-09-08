# Pre-Generated Data Pack — Install Guide

Everything is already generated. No script to run, no waiting.
Just copy files into place and load the SQL.

---

## What's in this pack

```
data-pack/
├── sql/
│   └── seed_data.sql              1,264 INSERT statements — all 9 tables
├── resumes/                        18 resume files (12 PDF + 6 DOCX)
│   ├── *.pdf  *.docx
│   └── _manifest.json              Ground truth for parser testing
├── models/                         4 pre-trained ML models
│   ├── submission_success.pkl      XGBoost   · AUC 0.910
│   ├── attrition_risk.pkl          XGBoost   · AUC 0.958
│   ├── client_churn.pkl            LightGBM  · AUC 0.920
│   ├── timesheet_anomaly.pkl       IForest   · 32 anomalies flagged
│   └── model_metrics.json          Training metrics
├── fixtures/                       JSON for every table + Redis
│   ├── candidates.json  jobs.json  clients.json  ...
│   └── redis_data.json
├── csv/                            Same data as CSV (Excel-friendly)
├── logs/                           413 realistic log entries
│   ├── ml.log  data.log  events.log  slow_ops.log  app.log
├── analytics.duckdb                Pre-built DuckDB with all 9 tables
└── load_redis_fixtures.py          Script to load Redis
```

---

## Install — 5 steps

### 1. Copy files into your project

```bash
cd ~/Downloads/data-pack

# Resumes → training folder
mkdir -p ~/staffing-platform/data/uploads/training
cp resumes/* ~/staffing-platform/data/uploads/training/

# ML models
mkdir -p ~/staffing-platform/data/models
cp models/* ~/staffing-platform/data/models/

# DuckDB
cp analytics.duckdb ~/staffing-platform/data/

# Fixtures (for Redis loader + reference)
mkdir -p ~/staffing-platform/data/fixtures
cp fixtures/* ~/staffing-platform/data/fixtures/

# Logs
mkdir -p ~/staffing-platform/logs
cp logs/* ~/staffing-platform/logs/

# Redis loader script
cp load_redis_fixtures.py ~/staffing-platform/scripts/

# SQL
cp sql/seed_data.sql ~/staffing-platform/
```

### 2. Make sure Docker is running

```bash
cd ~/staffing-platform
docker compose up -d
docker compose ps        # sip_postgres must show "Up"
```

### 3. Load the SQL into Postgres

```bash
docker compose exec -T postgres psql -U sip -d staffing < seed_data.sql
```

You should see a long run of `INSERT 0 1` lines ending with `COMMIT`.

### 4. Load Redis fixtures

```bash
source .venv/bin/activate
python scripts/load_redis_fixtures.py
```

### 5. Generate embeddings

This is the one step that must run locally — embeddings need the
sentence-transformers model on your machine.

```bash
python -c "
from ml.embedder import embed_all_candidates, embed_all_jobs
print('Embedding candidates...'); n1 = embed_all_candidates()
print('Embedding jobs...');       n2 = embed_all_jobs()
print(f'Done: {n1} candidates, {n2} jobs')
"
```

First run downloads the model (~22MB), then takes about 30 seconds.

---

## Verify it worked

```bash
# Row counts
docker compose exec postgres psql -U sip -d staffing -c "
SELECT 'candidates' t, COUNT(*) FROM candidates
UNION ALL SELECT 'jobs',        COUNT(*) FROM jobs
UNION ALL SELECT 'clients',     COUNT(*) FROM clients
UNION ALL SELECT 'recruiters',  COUNT(*) FROM recruiters
UNION ALL SELECT 'placements',  COUNT(*) FROM placements
UNION ALL SELECT 'timesheets',  COUNT(*) FROM timesheets
UNION ALL SELECT 'payroll',     COUNT(*) FROM payroll
UNION ALL SELECT 'predictions', COUNT(*) FROM predictions;
"
```

Expected:

| table | count |
|-------|-------|
| candidates | 80 |
| jobs | 30 |
| clients | 12 |
| recruiters | 6 |
| placements | 150 |
| timesheets | 624 |
| payroll | 234 |
| predictions | 92 |

```bash
# Embeddings written
docker compose exec postgres psql -U sip -d staffing -c \
  "SELECT COUNT(*) FROM candidates WHERE embedding IS NOT NULL;"

# Redis keys
docker compose exec redis redis-cli KEYS 'sip:*'

# Files in place
ls data/uploads/training/ | head
ls data/models/
tail -2 logs/events.log
```

---

## Start the app

```bash
streamlit run app.py
```

Login: `recruiter1` / `recruit123`

Every page now has data:

| Page | What you'll see |
|------|-----------------|
| Job Match | 80 candidates ranked against any of 30 jobs |
| Resume Parser | Upload any file from `data/uploads/training/` |
| Attrition Risk | 36 active contractors with risk scores |
| Revenue Forecast | 6 months history → 12 month projection |
| Client Churn | 12 clients scored |
| Rate Optimizer | Works immediately, no data needed |
| Recruiter KPIs | 6 recruiters, 150 placements |
| Timesheet Anomalies | 32 pre-flagged timesheets |
| Placement Funnel | submitted 40 → interview 34 → offer 24 → hire 30 |
| Margin Leakage | Accounts below threshold |
| AI Assistant | Needs Ollama + `build_index()` first |

---

## Data profile

**80 candidates** — 36 active contractors, visa mix roughly 38% citizen,
25% H1B, 20% green card, remainder OPT/STEM-OPT/EAD. Skills drawn from a
39-item pool, 4–9 per candidate.

**624 timesheets** — 16 weeks per active contractor. About 6% are
deliberate anomalies (62–85 hours) so the anomaly detector has real
signal. The pre-trained model flags 32 of them.

**150 placements** — spread across the funnel: 40 submitted, 34 interview,
24 offer, 30 hire, 22 rejected. Match scores 35–98.

**18 resumes** — validated end-to-end: 12/12 correct visa extraction and
12/12 email extraction when parsed with pdfminer.

---

## Testing the parser against ground truth

`_manifest.json` holds the true values for every generated resume:

```bash
python -c "
import json
from pathlib import Path
from ml.parser import parse_resume_file

manifest = json.loads(Path('data/uploads/training/_manifest.json').read_text())
correct = 0
for e in manifest:
    r = parse_resume_file(f\"data/uploads/training/{e['file']}\")
    hit = r['visa_status'] == e['visa']
    correct += hit
    print(f\"{e['file'][:32]:34} exp={e['visa']:9} got={r['visa_status']:9} {'OK' if hit else 'MISS'}\")
print(f'\nVisa accuracy: {correct}/{len(manifest)}')
"
```

---

## Re-running or resetting

The SQL starts with `TRUNCATE ... RESTART IDENTITY CASCADE`, so you can
re-load it any time to reset to a clean state:

```bash
docker compose exec -T postgres psql -U sip -d staffing < seed_data.sql
```

Note this wipes the embeddings too, so re-run step 5 afterwards.

---

## One caveat on the models

The four `.pkl` models are trained on synthetic feature distributions,
not on real placement outcomes. The AUC figures (0.91–0.96) reflect how
well the model learned the synthetic generator's rules, not real-world
predictive power.

They are fine for demos, UI development, and integration testing. Before
any real use, retrain against actual historical data:

```python
from ml.predictor import retrain_all_models
retrain_all_models()
```

The same applies to the anomaly detector — it learned what "normal" looks
like from the generated timesheets. Retrain once real timesheet data lands.
