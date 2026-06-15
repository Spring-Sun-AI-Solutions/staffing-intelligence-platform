"""
db/models.py
SQLAlchemy ORM models for the Staffing Intelligence Platform.

Sprint 1: users
Sprint 2: candidates, jobs, clients, recruiters, placements,
          timesheets, payroll, predictions
"""
import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Date,
    DateTime, Enum, Text, ForeignKey, create_engine, JSON
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from pgvector.sqlalchemy import Vector
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

# Embedding dimension — sentence-transformers/all-MiniLM-L6-v2 produces 384-dim
EMBEDDING_DIM = 384


# ── Enums ──────────────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    recruiter  = "recruiter"
    manager    = "manager"
    exec       = "exec"
    compliance = "compliance"


class VisaStatusEnum(str, enum.Enum):
    citizen   = "citizen"
    gc        = "gc"            # Green Card
    h1b       = "h1b"
    opt       = "opt"
    stem_opt  = "stem_opt"
    ead       = "ead"
    other     = "other"
    unknown   = "unknown"


class JobStatusEnum(str, enum.Enum):
    open    = "open"
    on_hold = "on_hold"
    filled  = "filled"
    closed  = "closed"


class PlacementStageEnum(str, enum.Enum):
    submitted   = "submitted"
    interview   = "interview"
    offer       = "offer"
    hire        = "hire"
    rejected    = "rejected"


class TimesheetStatusEnum(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"
    flagged  = "flagged"


# ── Sprint 1: Users ──────────────────────────────────────────────────────────────

class User(Base):
    """Platform users — mirrors auth_config.yaml roles."""
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    username   = Column(String(64), unique=True, nullable=False, index=True)
    name       = Column(String(128), nullable=False)
    email      = Column(String(256), unique=True, nullable=False)
    role       = Column(Enum(RoleEnum, name="roleenum"), nullable=False, default=RoleEnum.recruiter)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


# ── Sprint 2: Core entities ────────────────────────────────────────────────────

class Client(Base):
    """A staffing client / account."""
    __tablename__ = "clients"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(256), nullable=False, index=True)
    industry    = Column(String(128))
    contact_name  = Column(String(128))
    contact_email = Column(String(256))
    status      = Column(String(32), default="active")   # active / inactive / churned
    req_volume  = Column(Integer, default=0)              # active req count, refreshed by nightly job
    margin_pct  = Column(Float, default=0.0)              # average margin across placements
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs       = relationship("Job", back_populates="client")
    placements = relationship("Placement", back_populates="client")

    def __repr__(self):
        return f"<Client {self.name}>"


class Recruiter(Base):
    """A recruiter / account manager working placements."""
    __tablename__ = "recruiters"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(128), nullable=False)
    email      = Column(String(256), unique=True, nullable=False)
    team       = Column(String(64))
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)  # link to login, optional
    created_at = Column(DateTime, default=datetime.utcnow)

    placements = relationship("Placement", back_populates="recruiter")

    def __repr__(self):
        return f"<Recruiter {self.name}>"


class Candidate(Base):
    """A candidate / contractor profile, derived from a parsed resume."""
    __tablename__ = "candidates"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(128), nullable=False)
    email         = Column(String(256))
    phone         = Column(String(32))

    skills        = Column(ARRAY(String), default=list)
    visa_status   = Column(Enum(VisaStatusEnum, name="visastatusenum"),
                            default=VisaStatusEnum.unknown)
    location      = Column(String(128))
    yoe           = Column(Float, default=0.0)              # years of experience
    rate          = Column(Float, nullable=True)            # candidate's desired rate ($/hr)

    resume_path   = Column(String(512), nullable=True)      # path under data/uploads/resumes/
    resume_text   = Column(Text, nullable=True)             # extracted plain text (Sprint 3)
    embedding     = Column(Vector(EMBEDDING_DIM), nullable=True)  # resume embedding (Sprint 3)

    # Attrition signals (populated Sprint 5)
    is_active_contractor = Column(Boolean, default=False)
    tenure_days           = Column(Integer, nullable=True)
    comms_gap_days        = Column(Integer, nullable=True)
    overtime_pct          = Column(Float, nullable=True)
    client_feedback_score = Column(Float, nullable=True)
    attrition_risk_score  = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    placements = relationship("Placement", back_populates="candidate")
    timesheets = relationship("Timesheet", back_populates="contractor")
    payroll    = relationship("Payroll", back_populates="contractor")

    def __repr__(self):
        return f"<Candidate {self.name}>"


class Job(Base):
    """An open requisition / job description."""
    __tablename__ = "jobs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    title           = Column(String(256), nullable=False)
    client_id       = Column(Integer, ForeignKey("clients.id"), nullable=False)

    jd_text         = Column(Text, nullable=True)
    required_skills = Column(ARRAY(String), default=list)
    location        = Column(String(128))
    remote_ok       = Column(Boolean, default=False)

    rate_min        = Column(Float, nullable=True)
    rate_max        = Column(Float, nullable=True)
    visa_requirement = Column(Enum(VisaStatusEnum, name="visastatusenum"),
                               nullable=True)  # null = no restriction
    min_yoe         = Column(Float, default=0.0)
    max_yoe         = Column(Float, nullable=True)

    status          = Column(Enum(JobStatusEnum, name="jobstatusenum"),
                              default=JobStatusEnum.open)
    embedding       = Column(Vector(EMBEDDING_DIM), nullable=True)  # JD embedding (Sprint 3)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client     = relationship("Client", back_populates="jobs")
    placements = relationship("Placement", back_populates="job")

    def __repr__(self):
        return f"<Job {self.title} @ client_id={self.client_id}>"


class Placement(Base):
    """A single candidate-job submission moving through the funnel."""
    __tablename__ = "placements"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id       = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    recruiter_id = Column(Integer, ForeignKey("recruiters.id"), nullable=True)
    client_id    = Column(Integer, ForeignKey("clients.id"), nullable=False)

    stage        = Column(Enum(PlacementStageEnum, name="placementstageenum"),
                           default=PlacementStageEnum.submitted)

    match_score  = Column(Float, nullable=True)     # composite score (Sprint 4)
    skill_gap    = Column(JSON, nullable=True)       # {"missing": [...], "severity": "..."}

    bill_rate    = Column(Float, nullable=True)
    pay_rate     = Column(Float, nullable=True)
    margin       = Column(Float, nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="placements")
    job       = relationship("Job", back_populates="placements")
    recruiter = relationship("Recruiter", back_populates="placements")
    client    = relationship("Client", back_populates="placements")

    def __repr__(self):
        return f"<Placement cand={self.candidate_id} job={self.job_id} stage={self.stage}>"


class Timesheet(Base):
    """Weekly hours logged by an active contractor."""
    __tablename__ = "timesheets"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    contractor_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    week_start    = Column(Date, nullable=False)
    hours         = Column(Float, nullable=False)
    overtime_hours = Column(Float, default=0.0)

    status        = Column(Enum(TimesheetStatusEnum, name="timesheetstatusenum"),
                            default=TimesheetStatusEnum.pending)
    anomaly_flag  = Column(Boolean, default=False)
    anomaly_score = Column(Float, nullable=True)
    anomaly_reason = Column(String(256), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    contractor = relationship("Candidate", back_populates="timesheets")

    def __repr__(self):
        return f"<Timesheet contractor={self.contractor_id} week={self.week_start} hrs={self.hours}>"


class Payroll(Base):
    """Bill/pay rate and margin for a contractor for a given period."""
    __tablename__ = "payroll"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    contractor_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    period        = Column(Date, nullable=False)   # first day of month

    bill_rate     = Column(Float, nullable=False)
    pay_rate      = Column(Float, nullable=False)
    margin        = Column(Float, nullable=False)  # bill_rate - pay_rate
    margin_pct    = Column(Float, nullable=False)  # margin / bill_rate

    created_at = Column(DateTime, default=datetime.utcnow)

    contractor = relationship("Candidate", back_populates="payroll")

    def __repr__(self):
        return f"<Payroll contractor={self.contractor_id} period={self.period}>"


class Prediction(Base):
    """Generic store for ML model outputs (Sprint 4+)."""
    __tablename__ = "predictions"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False)   # 'candidate' | 'client' | 'placement'
    entity_id   = Column(Integer, nullable=False)
    model_name  = Column(String(64), nullable=False)   # 'submission_success' | 'attrition' | 'churn' | ...
    score       = Column(Float, nullable=False)
    features    = Column(JSON, nullable=True)          # input features used, for explainability
    created_at  = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Prediction {self.model_name} {self.entity_type}={self.entity_id} score={self.score}>"


# ── DB engine helpers ──────────────────────────────────────────────────────────

def get_engine():
    db_url = os.getenv("DATABASE_URL", "postgresql://sip:sippassword@localhost:5432/staffing")
    return create_engine(db_url, pool_pre_ping=True)


def get_session():
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    Session = sessionmaker(bind=get_engine())
    return Session()


def get_connection():
    return get_engine().connect()
