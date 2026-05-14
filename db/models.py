"""
db/models.py
SQLAlchemy ORM models for the Staffing Intelligence Platform.
Sprint 1: Users table only.
Sprint 2: All remaining tables added.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Enum, Text, ARRAY, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class RoleEnum(str, enum.Enum):
    recruiter  = "recruiter"
    manager    = "manager"
    exec       = "exec"
    compliance = "compliance"


class User(Base):
    """Platform users — mirrors auth_config.yaml roles."""
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    username   = Column(String(64), unique=True, nullable=False, index=True)
    name       = Column(String(128), nullable=False)
    email      = Column(String(256), unique=True, nullable=False)
    role       = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.recruiter)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


# ── DB engine helper ──────────────────────────────────────────────────────────
def get_engine():
    db_url = os.getenv("DATABASE_URL", "postgresql://sip:sippassword@localhost:5432/staffing")
    return create_engine(db_url, pool_pre_ping=True)


def get_connection():
    return get_engine().connect()
