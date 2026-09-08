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

## Quick start

```bash
git clone https://github.com/YOUR_ORG/staffing-intelligence-platform
cd staffing-intelligence-platform
chmod +x install.sh && ./install.sh
streamlit run app.py
```

Open **http://localhost:8501**

See [docs/setup.md](docs/setup.md) for full setup guide, Windows instructions, and credentials.
