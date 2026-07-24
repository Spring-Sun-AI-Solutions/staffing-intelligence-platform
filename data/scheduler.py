"""
data/scheduler.py  (Sprint 5 update)
APScheduler background jobs — updated to include Sprint 5 scoring jobs.

REPLACE your existing data/scheduler.py with this file.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from data.logger import get_logger

logger = get_logger("data.scheduler")

_scheduler = None


# ── Job definitions ───────────────────────────────────────────────────────────

def job_embed_new_candidates():
    try:
        from ml.embedder import embed_all_candidates
        n = embed_all_candidates(force=False)
        if n:
            logger.info(f"[scheduler] Embedded {n} new candidates")
        from data.redis_client import set_job_last_run
        set_job_last_run("embed_candidates")
    except Exception as e:
        logger.error(f"[scheduler] embed_candidates failed: {e}")


def job_embed_new_jobs():
    try:
        from ml.embedder import embed_all_jobs
        n = embed_all_jobs(force=False)
        if n:
            logger.info(f"[scheduler] Embedded {n} new jobs")
        from data.redis_client import set_job_last_run
        set_job_last_run("embed_jobs")
    except Exception as e:
        logger.error(f"[scheduler] embed_jobs failed: {e}")


def job_score_attrition():
    """Nightly attrition risk scoring for all active contractors."""
    try:
        from db.models import get_session, Candidate
        from sqlalchemy import select
        from ml.predictor import predict_attrition_risk

        session = get_session()
        active = session.execute(
            select(Candidate).where(Candidate.is_active_contractor.is_(True))
        ).scalars().all()
        session.close()

        for candidate in active:
            try:
                predict_attrition_risk(candidate.id)
            except Exception as e:
                logger.warning(f"Attrition score failed for candidate {candidate.id}: {e}")

        logger.info(f"[scheduler] Scored attrition for {len(active)} active contractors")
        from data.redis_client import set_job_last_run, cache_invalidate_pattern
        set_job_last_run("score_attrition")
        cache_invalidate_pattern("attrition:*")
    except Exception as e:
        logger.error(f"[scheduler] score_attrition failed: {e}")


def job_score_client_churn():
    """Nightly churn scoring for all clients."""
    try:
        from ml.forecaster import predict_all_client_churn
        results = predict_all_client_churn()
        logger.info(f"[scheduler] Scored churn for {len(results)} clients")
        from data.redis_client import set_job_last_run, cache_invalidate_pattern
        set_job_last_run("score_client_churn")
        cache_invalidate_pattern("churn:*")
    except Exception as e:
        logger.error(f"[scheduler] score_client_churn failed: {e}")


def job_detect_anomalies():
    """Nightly timesheet anomaly detection."""
    try:
        from ml.anomaly import detect_timesheet_anomalies
        flagged = detect_timesheet_anomalies(flag_in_db=True)
        logger.info(f"[scheduler] Anomaly detection: {len(flagged)} timesheets flagged")
        from data.redis_client import set_job_last_run
        set_job_last_run("detect_anomalies")
    except Exception as e:
        logger.error(f"[scheduler] detect_anomalies failed: {e}")


def job_refresh_duckdb():
    """Nightly DuckDB cache refresh."""
    try:
        from data.duckdb_client import refresh_cache
        refresh_cache()
        logger.info("[scheduler] DuckDB cache refreshed")
        from data.redis_client import set_job_last_run
        set_job_last_run("refresh_duckdb")
    except Exception as e:
        logger.error(f"[scheduler] refresh_duckdb failed: {e}")


def job_health_check():
    logger.info("[scheduler] Heartbeat OK")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    jobs = [
        (job_embed_new_candidates, CronTrigger(hour=2, minute=0),  "embed_candidates"),
        (job_embed_new_jobs,       CronTrigger(hour=2, minute=15), "embed_jobs"),
        (job_score_attrition,      CronTrigger(hour=2, minute=30), "score_attrition"),
        (job_score_client_churn,   CronTrigger(hour=2, minute=45), "score_client_churn"),
        (job_detect_anomalies,     CronTrigger(hour=3, minute=0),  "detect_anomalies"),
        (job_refresh_duckdb,       CronTrigger(hour=3, minute=30), "refresh_duckdb"),
        (job_health_check,         CronTrigger(minute=0),          "heartbeat"),
    ]

    for func, trigger, job_id in jobs:
        _scheduler.add_job(
            func, trigger=trigger, id=job_id,
            replace_existing=True, misfire_grace_time=3600,
        )

    _scheduler.start()
    logger.info(f"[scheduler] Started — {len(jobs)} jobs registered")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")


def get_scheduler_status() -> dict:
    if _scheduler is None:
        return {"running": False, "jobs": []}
    return {
        "running": _scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
            }
            for job in _scheduler.get_jobs()
        ],
    }
