"""
tests/test_sprint2.py
Sprint 2 tests — data schema, queries, seed data, file storage.

Requires a live Postgres connection (DATABASE_URL) with migrations applied:
    alembic upgrade head
    pytest tests/test_sprint2.py -v
"""
import os
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import inspect

from db.models import (
    get_engine, get_session, Base,
    Candidate, Job, Client, Recruiter, Placement, Timesheet, Payroll, Prediction,
    VisaStatusEnum, JobStatusEnum, PlacementStageEnum,
)
from db.queries import (
    get_candidates, get_jobs, get_open_jobs, get_clients, get_recruiters,
    get_placements, create_candidate, create_job, create_placement,
    get_placement_funnel_counts, get_timesheets, get_payroll,
    save_prediction, get_latest_predictions,
)
from data.file_store import (
    save_bytes, load_file, list_training_files, list_resume_files,
    delete_file, RESUME_DIR, TRAINING_DIR,
)


# ── Schema tests ──────────────────────────────────────────────────────────────

EXPECTED_TABLES = [
    "users", "clients", "recruiters", "candidates", "jobs",
    "placements", "timesheets", "payroll", "predictions",
]


def test_all_tables_exist():
    engine = get_engine()
    inspector = inspect(engine)
    existing = inspector.get_table_names()
    for table in EXPECTED_TABLES:
        assert table in existing, f"Missing table: {table}"


def test_candidates_table_columns():
    engine = get_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("candidates")}
    required = {
        "id", "name", "email", "skills", "visa_status", "location",
        "yoe", "rate", "resume_path", "embedding", "is_active_contractor",
        "attrition_risk_score",
    }
    assert required.issubset(cols), f"Missing columns: {required - cols}"


def test_jobs_table_columns():
    engine = get_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("jobs")}
    required = {
        "id", "title", "client_id", "jd_text", "required_skills",
        "rate_min", "rate_max", "status", "embedding",
    }
    assert required.issubset(cols)


def test_embedding_columns_are_vector_type():
    """pgvector columns should accept 384-dim vectors."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            __import__("sqlalchemy").text(
                "SELECT column_name, udt_name FROM information_schema.columns "
                "WHERE table_name = 'candidates' AND column_name = 'embedding'"
            )
        ).fetchone()
        assert result is not None
        assert result[1] == "vector"


# ── ORM model tests ───────────────────────────────────────────────────────────

def test_models_importable():
    assert Candidate.__tablename__ == "candidates"
    assert Job.__tablename__ == "jobs"
    assert Client.__tablename__ == "clients"
    assert Placement.__tablename__ == "placements"
    assert Timesheet.__tablename__ == "timesheets"
    assert Payroll.__tablename__ == "payroll"
    assert Prediction.__tablename__ == "predictions"


def test_create_and_read_candidate():
    cand_id = create_candidate({
        "name": "Test Candidate",
        "email": "test.candidate@example.com",
        "skills": ["Python", "SQL"],
        "visa_status": VisaStatusEnum.citizen,
        "location": "Remote",
        "yoe": 5.0,
        "rate": 80.0,
    })
    assert cand_id is not None

    df = get_candidates()
    assert "Test Candidate" in df["name"].values

    # Cleanup
    session = get_session()
    session.query(Candidate).filter(Candidate.id == cand_id).delete()
    session.commit()
    session.close()


def test_create_job_requires_valid_client():
    session = get_session()
    client = Client(name="Test Client Co", industry="Technology")
    session.add(client)
    session.commit()
    client_id = client.id

    job_id = create_job({
        "title": "Test Engineer",
        "client_id": client_id,
        "jd_text": "Test JD",
        "required_skills": ["Python"],
        "status": JobStatusEnum.open,
    })
    assert job_id is not None

    df = get_open_jobs()
    assert job_id in df["id"].values

    # Cleanup
    session.query(Job).filter(Job.id == job_id).delete()
    session.query(Client).filter(Client.id == client_id).delete()
    session.commit()
    session.close()


def test_placement_funnel_counts_returns_dataframe():
    df = get_placement_funnel_counts()
    assert "stage" in df.columns
    assert "count" in df.columns


# ── Prediction store tests ───────────────────────────────────────────────────

def test_save_and_retrieve_prediction():
    pred_id = save_prediction(
        entity_type="candidate", entity_id=1, model_name="test_model",
        score=0.87, features={"match_score": 0.9, "skill_overlap": 0.8},
    )
    assert pred_id is not None

    df = get_latest_predictions("test_model")
    assert len(df) >= 1
    assert df.iloc[0]["score"] == 0.87

    # Cleanup
    session = get_session()
    session.query(Prediction).filter(Prediction.id == pred_id).delete()
    session.commit()
    session.close()


# ── File storage tests ───────────────────────────────────────────────────────

def test_save_and_load_bytes():
    fake_pdf = b"%PDF-1.4 fake content for testing"
    path = save_bytes(fake_pdf, "test_resume.pdf", subfolder="training")

    assert path.startswith("data/uploads/training/")
    assert Path(path).exists()

    loaded = load_file(path)
    assert loaded == fake_pdf

    delete_file(path)
    assert not Path(path).exists()


def test_save_bytes_rejects_unsupported_extension():
    with pytest.raises(ValueError):
        save_bytes(b"data", "resume.txt", subfolder="training")


def test_list_training_files_returns_list():
    files = list_training_files()
    assert isinstance(files, list)


def test_upload_directories_exist():
    assert RESUME_DIR.parent.exists()  # data/uploads/
