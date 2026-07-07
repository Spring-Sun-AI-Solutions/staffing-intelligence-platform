"""
data/scheduler.py
APScheduler background jobs — nightly re-embedding and future model scoring.

Started automatically when Streamlit app launches.
All jobs are non-blocking and run in background threads.

Usage (in app.py, called once):
    from data.scheduler import start_scheduler
    start_scheduler()
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler = None


# ── Job definitions ───────────────────────────────────────────────────────────

def job_embed_new_candidates():
    """Embed any candidates added since last run."""
    try:
        from ml.embedder import embed_all_candidates
        n = embed_all_candidates(force=False)
        if n:
            logger.info(f"[scheduler] Embedded {n} new candidates")
    except Exception as e:
        logger.error(f"[scheduler] embed_candidates failed: {e}")


def job_embed_new_jobs():
    """Embed any jobs added since last run."""
    try:
        from ml.embedder import embed_all_jobs
        n = embed_all_jobs(force=False)
        if n:
            logger.info(f"[scheduler] Embedded {n} new jobs")
    except Exception as e:
        logger.error(f"[scheduler] embed_jobs failed: {e}")


def job_health_check():
    """Simple heartbeat — confirms scheduler is alive."""
    logger.info("[scheduler] Heartbeat OK")


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler():
    """
    Start the background scheduler. Safe to call multiple times
    (idempotent — won't start twice in the same process).
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("[scheduler] Already running, skipping start")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Nightly at 2:00 AM UTC — embed new candidates
    _scheduler.add_job(
        job_embed_new_candidates,
        trigger=CronTrigger(hour=2, minute=0),
        id="embed_candidates",
        name="Nightly candidate embedding",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Nightly at 2:15 AM UTC — embed new jobs
    _scheduler.add_job(
        job_embed_new_jobs,
        trigger=CronTrigger(hour=2, minute=15),
        id="embed_jobs",
        name="Nightly job embedding",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Hourly heartbeat
    _scheduler.add_job(
        job_health_check,
        trigger=CronTrigger(minute=0),
        id="heartbeat",
        name="Scheduler heartbeat",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[scheduler] Started — 3 jobs registered")
    return _scheduler


def stop_scheduler():
    """Gracefully stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")


def get_scheduler_status() -> dict:
    """Return current scheduler status — used by admin page."""
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
