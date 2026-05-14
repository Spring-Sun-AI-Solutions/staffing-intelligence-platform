# Setup Guide — Staffing Intelligence Platform

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker Desktop | Latest | https://www.docker.com/products/docker-desktop/ |
| Python | 3.10+ | https://www.python.org/downloads/ |
| Git | Any | https://git-scm.com/ |

---

## Quick Start (Mac / Linux)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_ORG/staffing-intelligence-platform.git
cd staffing-intelligence-platform

# 2. Run the installer
chmod +x install.sh
./install.sh

# 3. Start the platform
source .venv/bin/activate
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

## Quick Start (Windows)

```powershell
# In PowerShell (run as Administrator once to allow scripts):
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# Then:
git clone https://github.com/YOUR_ORG/staffing-intelligence-platform.git
cd staffing-intelligence-platform
.\install.ps1

# Start:
.venv\Scripts\Activate.ps1
streamlit run app.py
```

---

## Default Login Credentials

> ⚠️ Change these before using with any real data.

| Username | Password | Role |
|----------|----------|------|
| `recruiter1` | `recruit123` | Recruiter |
| `manager1` | `manage123` | Manager |
| `exec1` | `exec123` | Executive |
| `compliance1` | `comply123` | Compliance |

To change passwords, edit `scripts/hash_passwords.py` and re-run:
```bash
python scripts/hash_passwords.py
```

---

## Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| Postgres + pgvector | 5432 | Main database + vector embeddings |
| Redis | 6379 | Session cache + task queue |
| Ollama | 11434 | Local LLM inference (Llama 3) |

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f postgres
docker compose logs -f ollama

# Stop (keeps data)
docker compose down

# Full reset (DELETES ALL DATA)
docker compose down -v
```

---

## Ollama / LLM Setup

The AI assistant and JD tools require a local LLM. On first install, `llama3`
is pulled in the background (3–4 GB download).

```bash
# Check if model is downloaded
docker compose exec ollama ollama list

# Pull manually if needed
docker compose exec ollama ollama pull llama3

# Switch to a smaller/faster model (optional)
docker compose exec ollama ollama pull mistral
# Then update OLLAMA_MODEL=mistral in .env
```

**Apple Silicon (M1/M2/M3):** Ollama runs natively on Metal — excellent performance.  
**NVIDIA GPU:** Uncomment the GPU block in `docker-compose.yml`.  
**CPU only:** Works, but LLM responses will be slow (~30–60s). Use `mistral:7b-q4` for speed.

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current migration version
alembic current

# Create a new migration (Sprint 2+)
alembic revision --autogenerate -m "add candidates table"

# Roll back one migration
alembic downgrade -1
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=term-missing

# Sprint 1 tests only
pytest tests/test_sprint1.py -v
```

---

## Project Structure

```
staffing-intelligence-platform/
├── app.py                    # Streamlit entry point + auth gate
├── pages/                    # One .py file per page (auto-discovered by Streamlit)
│   ├── 1_job_match.py
│   ├── 2_resume_parser.py
│   └── ...                   # 15 pages total
├── ml/                       # ML models, parsers, LLM client
├── data/                     # DuckDB file, MLflow runs, seed scripts
├── db/                       # SQLAlchemy models, query functions, migrations
│   ├── models.py
│   ├── queries.py            # (Sprint 2)
│   └── migrations/
├── docker/                   # Docker config files
│   └── init.sql              # pgvector extension setup
├── tests/                    # Pytest test suite
├── scripts/                  # Utility scripts (hash_passwords.py, etc.)
├── docs/                     # This file and other docs
├── .streamlit/config.toml    # Streamlit theme + server config
├── .github/workflows/ci.yml  # GitHub Actions CI
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── pyproject.toml            # ruff + pytest config
├── auth_config.yaml          # User credentials (bcrypt hashed)
├── .env.example              # Environment variable template
└── install.sh / install.ps1  # One-command installers
```

---

## Adding a New User

1. Edit `auth_config.yaml` — add a new entry under `credentials.usernames`
2. Run `python scripts/hash_passwords.py` to hash the password
3. Restart the Streamlit app

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://sip:sippassword@localhost:5432/staffing` | Postgres connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3` | LLM model to use |
| `DUCKDB_PATH` | `./data/analytics.duckdb` | DuckDB file location |
| `MLFLOW_TRACKING_URI` | `./data/mlruns` | MLflow experiment store |
| `AUTH_COOKIE_SECRET` | (random on install) | Session cookie secret |
