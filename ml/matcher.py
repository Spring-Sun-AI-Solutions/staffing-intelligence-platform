"""
ml/matcher.py
Resume–Job Matching Engine (#1)

Composite scoring across 6 dimensions:
1. Semantic similarity  — pgvector cosine distance on embeddings
2. Skill overlap        — weighted match of required vs candidate skills
3. Location            — exact, same-state, remote-ok logic
4. Visa compatibility  — job requirement vs candidate visa status
5. Rate compatibility  — candidate rate vs job rate range
6. YOE compatibility   — candidate years vs job min/max experience

Returns ranked candidate list with per-dimension score breakdown
and skill gap analysis.

Usage:
    from ml.matcher import rank_candidates, score_candidate_job

    ranked = rank_candidates(job_id=5)
    # Returns list of dicts sorted by match_score desc
"""
import logging
from typing import Optional

from data.logger import get_logger
from ml.performance import timed

logger = get_logger("ml.matcher")

# ── Score weights (must sum to 1.0) ──────────────────────────────────────────
# Tunable via .env — defaults work well for IT staffing
WEIGHTS = {
    "semantic":  0.35,   # embedding cosine similarity
    "skill":     0.30,   # skill overlap
    "visa":      0.15,   # visa compatibility
    "yoe":       0.10,   # years of experience
    "rate":      0.05,   # rate compatibility
    "location":  0.05,   # location match
}

# Visa compatibility matrix
# Key = job requirement, Value = set of candidate visas that are compatible
VISA_COMPAT = {
    None:           {"citizen", "gc", "h1b", "opt", "stem_opt", "ead", "unknown"},
    "citizen":      {"citizen"},
    "gc":           {"citizen", "gc"},
    "h1b":          {"citizen", "gc", "h1b"},
    "opt":          {"citizen", "gc", "h1b", "opt", "stem_opt", "ead"},
    "stem_opt":     {"citizen", "gc", "h1b", "opt", "stem_opt", "ead"},
    "ead":          {"citizen", "gc", "h1b", "opt", "stem_opt", "ead"},
    "unknown":      {"citizen", "gc", "h1b", "opt", "stem_opt", "ead", "unknown"},
}

# Skill severity — skills marked as must-have get higher gap penalty
MUST_HAVE_RATIO = 0.6   # top 60% of required skills are treated as must-have


# ── Individual scorers ────────────────────────────────────────────────────────

def score_semantic(candidate_embedding, job_embedding) -> float:
    """
    Cosine similarity between candidate and job embeddings.
    pgvector stores normalised vectors so dot product = cosine similarity.
    Returns 0.0–1.0
    """
    if candidate_embedding is None or job_embedding is None:
        return 0.0
    # Both vectors are already L2-normalised by the embedder
    dot = sum(a * b for a, b in zip(candidate_embedding, job_embedding))
    # Clamp to [0, 1] — cosine can be slightly negative for unrelated texts
    return max(0.0, min(1.0, float(dot)))


def score_skill_overlap(candidate_skills: list, required_skills: list) -> tuple[float, dict]:
    """
    Weighted skill overlap score.
    Top MUST_HAVE_RATIO of required skills count double.

    Returns:
        (score 0.0–1.0, skill_gap dict)
    """
    if not required_skills:
        return 1.0, {"missing": [], "present": [], "severity": "none"}

    candidate_lower = {s.lower() for s in (candidate_skills or [])}
    required_lower  = [s.lower() for s in required_skills]

    n_must = max(1, int(len(required_lower) * MUST_HAVE_RATIO))
    must_have  = set(required_lower[:n_must])
    nice_have  = set(required_lower[n_must:])

    must_present  = must_have  & candidate_lower
    nice_present  = nice_have  & candidate_lower
    must_missing  = must_have  - candidate_lower
    nice_missing  = nice_have  - candidate_lower

    # Weighted score: must-have worth 2x
    total_weight   = len(must_have) * 2 + len(nice_have)
    earned_weight  = len(must_present) * 2 + len(nice_present)
    score = earned_weight / total_weight if total_weight > 0 else 1.0

    # Severity
    if len(must_missing) == 0:
        severity = "low"
    elif len(must_missing) <= 2:
        severity = "medium"
    else:
        severity = "high"

    # Reconstruct original-case missing skills
    req_original = {s.lower(): s for s in required_skills}
    missing = [req_original.get(s, s) for s in sorted(must_missing | nice_missing)]
    present = [req_original.get(s, s) for s in sorted(must_present | nice_present)]

    return round(score, 4), {
        "missing":       missing,
        "present":       present,
        "must_missing":  [req_original.get(s, s) for s in sorted(must_missing)],
        "severity":      severity,
    }


def score_visa(candidate_visa: str, job_visa_req) -> float:
    """
    Returns 1.0 if candidate visa satisfies job requirement, 0.0 otherwise.
    """
    if job_visa_req is None:
        return 1.0
    req_str = str(job_visa_req.value) if hasattr(job_visa_req, "value") else str(job_visa_req)
    cand_str = str(candidate_visa.value) if hasattr(candidate_visa, "value") else str(candidate_visa)
    compatible = VISA_COMPAT.get(req_str, set())
    return 1.0 if cand_str in compatible else 0.0


def score_yoe(candidate_yoe: float, min_yoe: float, max_yoe: Optional[float]) -> float:
    """
    Score based on years of experience fit.
    - Perfect: within min–max range → 1.0
    - Under min: partial score, penalised proportionally
    - Over max: slight penalty (overqualified) → 0.7
    """
    if candidate_yoe is None:
        candidate_yoe = 0.0
    if min_yoe is None:
        min_yoe = 0.0

    if candidate_yoe < min_yoe:
        # Under-qualified: score proportionally
        return round(max(0.0, candidate_yoe / min_yoe), 4) if min_yoe > 0 else 0.5
    if max_yoe and candidate_yoe > max_yoe:
        # Overqualified: slight penalty
        return 0.7
    return 1.0


def score_rate(candidate_rate: Optional[float], rate_min: Optional[float],
               rate_max: Optional[float]) -> float:
    """
    Score rate compatibility.
    - No rate info → neutral 0.5
    - Within range → 1.0
    - Outside range → penalised proportionally
    """
    if candidate_rate is None or rate_min is None:
        return 0.5

    if rate_max is None:
        rate_max = rate_min * 1.3  # assume 30% buffer if no max

    if rate_min <= candidate_rate <= rate_max:
        return 1.0

    if candidate_rate < rate_min:
        # Candidate cheaper than min — very good for client
        return 1.0

    # Candidate more expensive than max
    overage = (candidate_rate - rate_max) / rate_max
    return round(max(0.0, 1.0 - overage), 4)


def score_location(candidate_location: Optional[str], job_location: Optional[str],
                   remote_ok: bool = False) -> float:
    """
    Score location compatibility.
    - Remote job → 1.0 always
    - Exact city match → 1.0
    - Same state → 0.7
    - Different → 0.3
    - No location info → 0.5
    """
    if remote_ok:
        return 1.0
    if not candidate_location or not job_location:
        return 0.5

    cand = candidate_location.lower().strip()
    job  = job_location.lower().strip()

    if cand == job:
        return 1.0

    if "remote" in cand or "remote" in job:
        return 1.0

    # Same state (last part of "City, ST" format)
    cand_parts = [p.strip() for p in cand.split(",")]
    job_parts  = [p.strip() for p in job.split(",")]
    if len(cand_parts) >= 2 and len(job_parts) >= 2:
        if cand_parts[-1] == job_parts[-1]:
            return 0.7

    return 0.3


# ── Composite scorer ──────────────────────────────────────────────────────────

def score_candidate_job(candidate, job) -> dict:
    """
    Compute a full composite match score between one candidate and one job.

    Args:
        candidate: SQLAlchemy Candidate ORM object
        job:       SQLAlchemy Job ORM object

    Returns dict with:
        match_score, semantic, skill, visa, yoe, rate, location, skill_gap
    """
    # Individual scores
    sem   = score_semantic(candidate.embedding, job.embedding)
    skill_score, skill_gap = score_skill_overlap(
        candidate.skills or [], job.required_skills or []
    )
    visa  = score_visa(candidate.visa_status, job.visa_requirement)
    yoe   = score_yoe(candidate.yoe, job.min_yoe or 0, job.max_yoe)
    rate  = score_rate(candidate.rate, job.rate_min, job.rate_max)
    loc   = score_location(candidate.location, job.location, job.remote_ok or False)

    # Weighted composite
    composite = (
        sem   * WEIGHTS["semantic"] +
        skill_score * WEIGHTS["skill"] +
        visa  * WEIGHTS["visa"] +
        yoe   * WEIGHTS["yoe"] +
        rate  * WEIGHTS["rate"] +
        loc   * WEIGHTS["location"]
    )

    return {
        "candidate_id":  candidate.id,
        "candidate_name": candidate.name,
        "match_score":   round(composite * 100, 1),   # 0–100 scale
        "scores": {
            "semantic":  round(sem * 100, 1),
            "skill":     round(skill_score * 100, 1),
            "visa":      round(visa * 100, 1),
            "yoe":       round(yoe * 100, 1),
            "rate":      round(rate * 100, 1),
            "location":  round(loc * 100, 1),
        },
        "skill_gap":     skill_gap,
        "visa_status":   str(candidate.visa_status.value) if hasattr(candidate.visa_status, "value") else str(candidate.visa_status),
        "location":      candidate.location,
        "yoe":           candidate.yoe,
        "rate":          candidate.rate,
        "skills":        candidate.skills or [],
    }


# ── Main ranking function ─────────────────────────────────────────────────────

@timed("rank_candidates")
def rank_candidates(
    job_id: int,
    top_n: int = 50,
    min_score: float = 0.0,
    visa_filter: Optional[str] = None,
    location_filter: Optional[str] = None,
) -> list[dict]:
    """
    Rank all candidates against a job and return top N matches.

    Args:
        job_id:          ID of the job to match against
        top_n:           max candidates to return (default 50)
        min_score:       minimum match score 0–100 to include (default 0)
        visa_filter:     only return candidates with this visa status
        location_filter: only return candidates in this location

    Returns:
        List of score dicts sorted by match_score descending
    """
    from db.models import get_session, Candidate, Job
    from sqlalchemy import select

    session = get_session()
    try:
        # Load job
        job = session.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        # Load candidates
        q = select(Candidate)
        if visa_filter:
            q = q.where(Candidate.visa_status == visa_filter)
        if location_filter:
            q = q.where(Candidate.location.ilike(f"%{location_filter}%"))

        candidates = session.execute(q).scalars().all()

        if not candidates:
            logger.warning(f"No candidates found for job {job_id}")
            return []

        logger.info(f"Scoring {len(candidates)} candidates against job {job_id}: {job.title}")

        # Score all candidates
        results = []
        for candidate in candidates:
            try:
                score = score_candidate_job(candidate, job)
                if score["match_score"] >= min_score:
                    results.append(score)
            except Exception as e:
                logger.error(f"Failed to score candidate {candidate.id}: {e}")

        # Sort by match score descending
        results.sort(key=lambda x: x["match_score"], reverse=True)

        logger.info(
            f"Ranked {len(results)} candidates for job {job_id}. "
            f"Top score: {results[0]['match_score'] if results else 0}"
        )

        return results[:top_n]

    finally:
        session.close()


def get_skill_gap_summary(job_id: int, candidate_id: int) -> dict:
    """
    Get detailed skill gap between one candidate and one job.
    Used for the skill gap panel in the Streamlit UI.
    """
    from db.models import get_session, Candidate, Job

    session = get_session()
    try:
        candidate = session.get(Candidate, candidate_id)
        job = session.get(Job, job_id)
        if not candidate or not job:
            raise ValueError("Candidate or job not found")
        _, skill_gap = score_skill_overlap(
            candidate.skills or [], job.required_skills or []
        )
        return skill_gap
    finally:
        session.close()
