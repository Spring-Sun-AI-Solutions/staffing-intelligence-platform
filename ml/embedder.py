"""
ml/embedder.py
Generates 384-dim sentence-transformer embeddings for resumes and job descriptions.
Stores embeddings directly into Postgres via pgvector.

Model: all-MiniLM-L6-v2 (fast, 384-dim, excellent for semantic similarity)
- ~22MB download on first use
- Runs well on CPU (Apple Silicon or Intel)
- No GPU needed

Usage:
    from ml.embedder import embed_text, embed_all_candidates, embed_all_jobs

    vector = embed_text("5 years Python experience, AWS, Docker")
    embed_all_candidates()   # batch embed all candidates without embeddings
    embed_all_jobs()         # batch embed all jobs without embeddings
"""
import logging
from typing import Optional

import numpy as np

from data.logger import get_logger, log_embed_event
from ml.performance import timed
logger = get_logger("ml.embedder")

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None  # lazy-loaded


def _get_model():
    """Lazy-load sentence-transformer model (downloads on first call ~22MB)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Embedding model loaded")
    return _model


# ── Core embedding function ───────────────────────────────────────────────────
@timed("embed_text")
def embed_text(text: str) -> list[float]:
    """
    Convert text to a 384-dim embedding vector.

    Args:
        text: plain text (resume text, JD text, skill string, etc.)

    Returns:
        List of 384 floats, ready to store in pgvector column
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    model = _get_model()
    # Truncate to avoid exceeding model's max token limit (256 tokens)
    text = text[:4000]
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Batch embed multiple texts efficiently.

    Args:
        texts: list of strings
        batch_size: how many to process at once (default 32, safe for 16GB RAM)

    Returns:
        List of embedding vectors, one per input text
    """
    if not texts:
        return []

    model = _get_model()
    # Truncate each text
    texts = [t[:4000] if t else "" for t in texts]

    logger.info(f"Batch embedding {len(texts)} texts...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 10,
    )
    return [e.tolist() for e in embeddings]


# ── Resume text builder ───────────────────────────────────────────────────────

def build_candidate_embed_text(candidate) -> str:
    """
    Build a rich text representation of a candidate for embedding.
    Combines skills, location, visa status, and YOE for better semantic matching.
    """
    parts = []
    if candidate.resume_text:
        parts.append(candidate.resume_text[:2000])
    if candidate.skills:
        parts.append("Skills: " + ", ".join(candidate.skills))
    if candidate.location:
        parts.append(f"Location: {candidate.location}")
    if candidate.visa_status:
        parts.append(f"Visa: {candidate.visa_status}")
    if candidate.yoe:
        parts.append(f"Years of experience: {candidate.yoe}")
    return "\n".join(parts)


def build_job_embed_text(job) -> str:
    """
    Build a rich text representation of a job for embedding.
    """
    parts = []
    if job.title:
        parts.append(f"Job title: {job.title}")
    if job.jd_text:
        parts.append(job.jd_text[:2000])
    if job.required_skills:
        parts.append("Required skills: " + ", ".join(job.required_skills))
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.min_yoe:
        parts.append(f"Minimum experience: {job.min_yoe} years")
    return "\n".join(parts)


# ── Batch embedding (store to DB) ─────────────────────────────────────────────

def embed_all_candidates(force: bool = False) -> int:
    """
    Embed all candidates that don't have an embedding yet.
    Stores vectors directly to candidates.embedding column.

    Args:
        force: if True, re-embed even candidates that already have embeddings

    Returns:
        Number of candidates embedded
    """
    from db.models import get_session, Candidate
    from sqlalchemy import select

    session = get_session()
    try:
        q = select(Candidate)
        if not force:
            q = q.where(Candidate.embedding.is_(None))
        candidates = session.execute(q).scalars().all()

        if not candidates:
            logger.info("No candidates need embedding")
            return 0

        logger.info(f"Embedding {len(candidates)} candidates...")

        # Build texts
        texts = [build_candidate_embed_text(c) for c in candidates]

        # Batch embed
        embeddings = embed_texts_batch(texts)

        # Store back
        for candidate, embedding in zip(candidates, embeddings):
            candidate.embedding = embedding

        session.commit()
        logger.info(f"Embedded {len(candidates)} candidates successfully")
        return len(candidates)

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to embed candidates: {e}")
        raise
    finally:
        session.close()


def embed_all_jobs(force: bool = False) -> int:
    """
    Embed all jobs that don't have an embedding yet.
    Stores vectors directly to jobs.embedding column.
    """
    from db.models import get_session, Job
    from sqlalchemy import select

    session = get_session()
    try:
        q = select(Job)
        if not force:
            q = q.where(Job.embedding.is_(None))
        jobs = session.execute(q).scalars().all()

        if not jobs:
            logger.info("No jobs need embedding")
            return 0

        logger.info(f"Embedding {len(jobs)} jobs...")

        texts = [build_job_embed_text(j) for j in jobs]
        embeddings = embed_texts_batch(texts)

        for job, embedding in zip(jobs, embeddings):
            job.embedding = embedding

        session.commit()
        logger.info(f"Embedded {len(jobs)} jobs successfully")
        return len(jobs)

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to embed jobs: {e}")
        raise
    finally:
        session.close()


def embed_candidate(candidate_id: int) -> bool:
    """Embed a single candidate by ID. Used after a new resume is uploaded."""
    from db.models import get_session, Candidate

    session = get_session()
    try:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        text = build_candidate_embed_text(candidate)
        candidate.embedding = embed_text(text)
        session.commit()
        logger.info(f"Embedded candidate {candidate_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to embed candidate {candidate_id}: {e}")
        return False
    finally:
        session.close()


def embed_job(job_id: int) -> bool:
    """Embed a single job by ID. Used after a new JD is added."""
    from db.models import get_session, Job

    session = get_session()
    try:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        text = build_job_embed_text(job)
        job.embedding = embed_text(text)
        session.commit()
        logger.info(f"Embedded job {job_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to embed job {job_id}: {e}")
        return False
    finally:
        session.close()
