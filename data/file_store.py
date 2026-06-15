"""
data/file_store.py
Local file storage for resumes and training data.

Files live on disk under data/uploads/. Postgres stores only the path,
never the file bytes.

Usage in a Streamlit page:
    from data.file_store import save_upload, list_training_files

    uploaded = st.file_uploader("Upload resume", type=["pdf", "docx"])
    if uploaded:
        path = save_upload(uploaded, subfolder="resumes")
        # path -> "data/uploads/resumes/20260601_123456_john_doe.pdf"
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project-root relative base directory
BASE_DIR  = Path(__file__).resolve().parent.parent  # repo root
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
RESUME_DIR   = UPLOAD_DIR / "resumes"
TRAINING_DIR = UPLOAD_DIR / "training"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


def _ensure_dirs():
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    """Strip unsafe characters and prefix with a timestamp to avoid collisions."""
    name = re.sub(r"[^A-Za-z0-9_.\-]", "_", filename)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{name}"


def save_upload(uploaded_file, subfolder: str = "resumes") -> str:
    """
    Save a Streamlit UploadedFile object to disk.

    Args:
        uploaded_file: object returned by st.file_uploader (has .name and .getbuffer())
        subfolder: "resumes" or "training"

    Returns:
        Relative path string (from repo root) to the saved file, e.g.
        "data/uploads/resumes/20260601_120000_john_doe.pdf"
    """
    _ensure_dirs()

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    target_dir = UPLOAD_DIR / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(uploaded_file.name)
    file_path = target_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Return path relative to repo root for portability
    return str(file_path.relative_to(BASE_DIR))


def save_bytes(data: bytes, filename: str, subfolder: str = "resumes") -> str:
    """Save raw bytes (e.g. from a batch script) to disk."""
    _ensure_dirs()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    target_dir = UPLOAD_DIR / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(filename)
    file_path = target_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(data)

    return str(file_path.relative_to(BASE_DIR))


def load_file(relative_path: str) -> bytes:
    """Read a file's bytes given its path relative to repo root."""
    full_path = BASE_DIR / relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {full_path}")
    with open(full_path, "rb") as f:
        return f.read()


def list_training_files() -> list[str]:
    """List all PDF/DOCX files in data/uploads/training/ for batch processing (Sprint 3)."""
    _ensure_dirs()
    files = []
    for ext in ALLOWED_EXTENSIONS:
        files.extend(str(p.relative_to(BASE_DIR)) for p in TRAINING_DIR.glob(f"*{ext}"))
    return sorted(files)


def list_resume_files() -> list[str]:
    """List all resumes uploaded via the UI."""
    _ensure_dirs()
    files = []
    for ext in ALLOWED_EXTENSIONS:
        files.extend(str(p.relative_to(BASE_DIR)) for p in RESUME_DIR.glob(f"*{ext}"))
    return sorted(files)


def delete_file(relative_path: str) -> None:
    full_path = BASE_DIR / relative_path
    if full_path.exists():
        full_path.unlink()
