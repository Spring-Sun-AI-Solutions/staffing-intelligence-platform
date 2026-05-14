"""
tests/test_sprint1.py
Sprint 1 smoke tests — verifies the skeleton is wired correctly.
Runs without a live DB (mocked) so CI passes from day 1.
"""
import os
import pytest
from pathlib import Path


# ── File structure tests ──────────────────────────────────────────────────────

def test_app_entry_point_exists():
    assert Path("app.py").exists(), "app.py must exist"

def test_pages_directory_exists():
    assert Path("pages").is_dir(), "pages/ directory must exist"

def test_all_15_pages_exist():
    pages = list(Path("pages").glob("*.py"))
    assert len(pages) >= 15, f"Expected 15 pages, found {len(pages)}"

def test_requirements_txt_exists():
    assert Path("requirements.txt").exists()

def test_env_example_exists():
    assert Path(".env.example").exists()

def test_docker_compose_exists():
    assert Path("docker-compose.yml").exists()

def test_auth_config_exists():
    assert Path("auth_config.yaml").exists()

def test_streamlit_config_exists():
    assert Path(".streamlit/config.toml").exists()

def test_alembic_ini_exists():
    assert Path("alembic.ini").exists()

def test_migration_exists():
    versions = list(Path("db/migrations/versions").glob("*.py"))
    assert len(versions) >= 1, "At least one migration must exist"

def test_install_script_exists():
    assert Path("install.sh").exists()
    assert Path("install.ps1").exists()

def test_ci_workflow_exists():
    assert Path(".github/workflows/ci.yml").exists()


# ── Config tests ──────────────────────────────────────────────────────────────

def test_env_example_has_required_keys():
    content = Path(".env.example").read_text()
    required = ["DATABASE_URL", "REDIS_URL", "OLLAMA_BASE_URL", "OLLAMA_MODEL",
                 "DUCKDB_PATH", "MLFLOW_TRACKING_URI", "AUTH_COOKIE_SECRET"]
    for key in required:
        assert key in content, f"Missing key in .env.example: {key}"

def test_docker_compose_has_required_services():
    content = Path("docker-compose.yml").read_text()
    for service in ["postgres", "redis", "ollama"]:
        assert service in content, f"Missing service in docker-compose.yml: {service}"

def test_auth_config_has_all_roles():
    import yaml
    config = yaml.safe_load(Path("auth_config.yaml").read_text())
    users = config["credentials"]["usernames"]
    roles = {v["role"] for v in users.values()}
    assert "recruiter"  in roles
    assert "manager"    in roles
    assert "exec"       in roles
    assert "compliance" in roles

def test_requirements_has_core_packages():
    content = Path("requirements.txt").read_text()
    required = ["streamlit", "sqlalchemy", "psycopg2", "alembic",
                 "redis", "plotly", "xgboost", "prophet", "spacy"]
    for pkg in required:
        assert pkg in content, f"Missing package in requirements.txt: {pkg}"


# ── DB model tests (no live DB needed) ───────────────────────────────────────

def test_user_model_importable():
    from db.models import User, RoleEnum, Base
    assert User.__tablename__ == "users"
    assert "recruiter" in [r.value for r in RoleEnum]

def test_user_model_has_required_columns():
    from db.models import User
    cols = [c.name for c in User.__table__.columns]
    for col in ["id", "username", "name", "email", "role", "is_active"]:
        assert col in cols, f"Missing column: {col}"
