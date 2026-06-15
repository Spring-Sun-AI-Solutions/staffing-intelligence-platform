"""
db/queries.py
Reusable query functions called directly from Streamlit pages.

Usage in a page:
    from db.queries import get_candidates, get_open_jobs
    candidates = get_candidates()
    st.dataframe(candidates)

All functions return plain Python objects (lists of dicts or pandas DataFrames)
so Streamlit pages never need to touch SQLAlchemy session objects directly.
"""
from datetime import datetime, date
from typing import Optional

import pandas as pd
from sqlalchemy import select, func

from db.models import (
    get_session, Candidate, Job, Client, Recruiter, Placement,
    Timesheet, Payroll, Prediction,
    VisaStatusEnum, JobStatusEnum, PlacementStageEnum, TimesheetStatusEnum,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_df(rows, columns=None):
    """Convert a list of ORM objects to a DataFrame using their __dict__."""
    data = []
    for r in rows:
        d = {k: v for k, v in vars(r).items() if not k.startswith("_")}
        data.append(d)
    df = pd.DataFrame(data)
    if columns:
        existing = [c for c in columns if c in df.columns]
        df = df[existing]
    return df


# ── Candidates ───────────────────────────────────────────────────────────────

def get_candidates(active_only: bool = False) -> pd.DataFrame:
    """Return all candidates as a DataFrame."""
    session = get_session()
    try:
        q = select(Candidate)
        if active_only:
            q = q.where(Candidate.is_active_contractor.is_(True))
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "name", "email", "skills", "visa_status", "location",
            "yoe", "rate", "is_active_contractor", "attrition_risk_score",
            "resume_path", "created_at",
        ])
    finally:
        session.close()


def get_candidate_by_id(candidate_id: int) -> Optional[Candidate]:
    session = get_session()
    try:
        return session.get(Candidate, candidate_id)
    finally:
        session.close()


def create_candidate(data: dict) -> int:
    """Insert a new candidate. Returns the new candidate's id."""
    session = get_session()
    try:
        candidate = Candidate(**data)
        session.add(candidate)
        session.commit()
        return candidate.id
    finally:
        session.close()


def update_candidate(candidate_id: int, data: dict) -> None:
    session = get_session()
    try:
        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate {candidate_id} not found")
        for k, v in data.items():
            setattr(candidate, k, v)
        candidate.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()


# ── Jobs ─────────────────────────────────────────────────────────────────────

def get_jobs(status: Optional[str] = None) -> pd.DataFrame:
    """Return jobs, optionally filtered by status ('open', 'closed', etc.)."""
    session = get_session()
    try:
        q = select(Job)
        if status:
            q = q.where(Job.status == JobStatusEnum(status))
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "title", "client_id", "required_skills", "location",
            "remote_ok", "rate_min", "rate_max", "visa_requirement",
            "min_yoe", "max_yoe", "status", "created_at",
        ])
    finally:
        session.close()


def get_open_jobs() -> pd.DataFrame:
    return get_jobs(status="open")


def get_job_by_id(job_id: int) -> Optional[Job]:
    session = get_session()
    try:
        return session.get(Job, job_id)
    finally:
        session.close()


def create_job(data: dict) -> int:
    session = get_session()
    try:
        job = Job(**data)
        session.add(job)
        session.commit()
        return job.id
    finally:
        session.close()


# ── Clients ──────────────────────────────────────────────────────────────────

def get_clients() -> pd.DataFrame:
    session = get_session()
    try:
        rows = session.execute(select(Client)).scalars().all()
        return _to_df(rows, columns=[
            "id", "name", "industry", "status", "req_volume",
            "margin_pct", "contact_name", "contact_email", "created_at",
        ])
    finally:
        session.close()


def get_client_by_id(client_id: int) -> Optional[Client]:
    session = get_session()
    try:
        return session.get(Client, client_id)
    finally:
        session.close()


# ── Recruiters ───────────────────────────────────────────────────────────────

def get_recruiters() -> pd.DataFrame:
    session = get_session()
    try:
        rows = session.execute(select(Recruiter)).scalars().all()
        return _to_df(rows, columns=["id", "name", "email", "team", "created_at"])
    finally:
        session.close()


# ── Placements ───────────────────────────────────────────────────────────────

def get_placements(
    client_id: Optional[int] = None,
    recruiter_id: Optional[int] = None,
    stage: Optional[str] = None,
) -> pd.DataFrame:
    session = get_session()
    try:
        q = select(Placement)
        if client_id:
            q = q.where(Placement.client_id == client_id)
        if recruiter_id:
            q = q.where(Placement.recruiter_id == recruiter_id)
        if stage:
            q = q.where(Placement.stage == PlacementStageEnum(stage))
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "candidate_id", "job_id", "recruiter_id", "client_id",
            "stage", "match_score", "skill_gap", "bill_rate", "pay_rate",
            "margin", "submitted_at", "updated_at",
        ])
    finally:
        session.close()


def create_placement(data: dict) -> int:
    session = get_session()
    try:
        placement = Placement(**data)
        session.add(placement)
        session.commit()
        return placement.id
    finally:
        session.close()


def update_placement_stage(placement_id: int, stage: str) -> None:
    session = get_session()
    try:
        placement = session.get(Placement, placement_id)
        if placement is None:
            raise ValueError(f"Placement {placement_id} not found")
        placement.stage = PlacementStageEnum(stage)
        placement.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()


def get_placement_funnel_counts(client_id: Optional[int] = None) -> pd.DataFrame:
    """Returns counts per funnel stage — used by the placement funnel chart (Sprint 8)."""
    session = get_session()
    try:
        q = select(Placement.stage, func.count(Placement.id).label("count"))
        if client_id:
            q = q.where(Placement.client_id == client_id)
        q = q.group_by(Placement.stage)
        rows = session.execute(q).all()
        return pd.DataFrame(rows, columns=["stage", "count"])
    finally:
        session.close()


# ── Timesheets ───────────────────────────────────────────────────────────────

def get_timesheets(
    contractor_id: Optional[int] = None,
    flagged_only: bool = False,
) -> pd.DataFrame:
    session = get_session()
    try:
        q = select(Timesheet)
        if contractor_id:
            q = q.where(Timesheet.contractor_id == contractor_id)
        if flagged_only:
            q = q.where(Timesheet.anomaly_flag.is_(True))
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "contractor_id", "week_start", "hours", "overtime_hours",
            "status", "anomaly_flag", "anomaly_score", "anomaly_reason", "created_at",
        ])
    finally:
        session.close()


def create_timesheet(data: dict) -> int:
    session = get_session()
    try:
        ts = Timesheet(**data)
        session.add(ts)
        session.commit()
        return ts.id
    finally:
        session.close()


def flag_timesheet_anomaly(timesheet_id: int, score: float, reason: str) -> None:
    session = get_session()
    try:
        ts = session.get(Timesheet, timesheet_id)
        if ts is None:
            raise ValueError(f"Timesheet {timesheet_id} not found")
        ts.anomaly_flag = True
        ts.anomaly_score = score
        ts.anomaly_reason = reason
        ts.status = TimesheetStatusEnum.flagged
        session.commit()
    finally:
        session.close()


# ── Payroll ──────────────────────────────────────────────────────────────────

def get_payroll(contractor_id: Optional[int] = None) -> pd.DataFrame:
    session = get_session()
    try:
        q = select(Payroll)
        if contractor_id:
            q = q.where(Payroll.contractor_id == contractor_id)
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "contractor_id", "period", "bill_rate", "pay_rate",
            "margin", "margin_pct", "created_at",
        ])
    finally:
        session.close()


def get_monthly_revenue() -> pd.DataFrame:
    """Aggregate revenue (sum of bill_rate) by month — feeds the revenue forecast (Sprint 5)."""
    session = get_session()
    try:
        q = select(
            func.date_trunc("month", Payroll.period).label("month"),
            func.sum(Payroll.bill_rate).label("revenue"),
            func.count(Payroll.contractor_id).label("headcount"),
        ).group_by(func.date_trunc("month", Payroll.period)).order_by("month")
        rows = session.execute(q).all()
        return pd.DataFrame(rows, columns=["month", "revenue", "headcount"])
    finally:
        session.close()


def get_margin_leakage() -> pd.DataFrame:
    """Accounts with margin_pct below 15% — feeds margin leakage analysis (Sprint 8)."""
    session = get_session()
    try:
        q = (
            select(
                Client.id, Client.name,
                func.avg(Payroll.margin_pct).label("avg_margin_pct"),
                func.sum(Payroll.bill_rate).label("total_revenue"),
            )
            .join(Candidate, Candidate.id == Payroll.contractor_id)
            .join(Placement, Placement.candidate_id == Candidate.id)
            .join(Client, Client.id == Placement.client_id)
            .group_by(Client.id, Client.name)
            .having(func.avg(Payroll.margin_pct) < 0.15)
        )
        # Note: requires Payroll join — simplified version, refined in Sprint 5
        rows = session.execute(
            select(Client.id, Client.name, Client.margin_pct)
            .where(Client.margin_pct < 15)
        ).all()
        return pd.DataFrame(rows, columns=["id", "name", "margin_pct"])
    finally:
        session.close()


# ── Predictions ──────────────────────────────────────────────────────────────

def save_prediction(entity_type: str, entity_id: int, model_name: str,
                     score: float, features: Optional[dict] = None) -> int:
    session = get_session()
    try:
        pred = Prediction(
            entity_type=entity_type, entity_id=entity_id,
            model_name=model_name, score=score, features=features,
        )
        session.add(pred)
        session.commit()
        return pred.id
    finally:
        session.close()


def get_latest_predictions(model_name: str, entity_type: Optional[str] = None) -> pd.DataFrame:
    session = get_session()
    try:
        q = select(Prediction).where(Prediction.model_name == model_name)
        if entity_type:
            q = q.where(Prediction.entity_type == entity_type)
        q = q.order_by(Prediction.created_at.desc())
        rows = session.execute(q).scalars().all()
        return _to_df(rows, columns=[
            "id", "entity_type", "entity_id", "model_name",
            "score", "features", "created_at",
        ])
    finally:
        session.close()
