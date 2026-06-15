"""create core tables: clients, recruiters, candidates, jobs, placements, timesheets, payroll, predictions

Revision ID: 002_core_tables
Revises: 001_users
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "002_core_tables"
down_revision = "001_users"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────────────────────
    visa_enum = sa.Enum(
        "citizen", "gc", "h1b", "opt", "stem_opt", "ead", "other", "unknown",
        name="visastatusenum"
    )
    job_status_enum = sa.Enum("open", "on_hold", "filled", "closed", name="jobstatusenum")
    placement_stage_enum = sa.Enum(
        "submitted", "interview", "offer", "hire", "rejected",
        name="placementstageenum"
    )
    timesheet_status_enum = sa.Enum(
        "pending", "approved", "rejected", "flagged",
        name="timesheetstatusenum"
    )

    visa_enum.create(op.get_bind(), checkfirst=True)
    job_status_enum.create(op.get_bind(), checkfirst=True)
    placement_stage_enum.create(op.get_bind(), checkfirst=True)
    timesheet_status_enum.create(op.get_bind(), checkfirst=True)

    # ── clients ────────────────────────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name",          sa.String(256), nullable=False),
        sa.Column("industry",      sa.String(128)),
        sa.Column("contact_name",  sa.String(128)),
        sa.Column("contact_email", sa.String(256)),
        sa.Column("status",        sa.String(32), server_default="active"),
        sa.Column("req_volume",    sa.Integer(), server_default="0"),
        sa.Column("margin_pct",    sa.Float(), server_default="0"),
        sa.Column("created_at",    sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_clients_name", "clients", ["name"])

    # ── recruiters ────────────────────────────────────────────────────────────
    op.create_table(
        "recruiters",
        sa.Column("id",         sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name",       sa.String(128), nullable=False),
        sa.Column("email",      sa.String(256), nullable=False, unique=True),
        sa.Column("team",       sa.String(64)),
        sa.Column("user_id",    sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    # ── candidates ────────────────────────────────────────────────────────────
    op.create_table(
        "candidates",
        sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name",          sa.String(128), nullable=False),
        sa.Column("email",         sa.String(256)),
        sa.Column("phone",         sa.String(32)),
        sa.Column("skills",        sa.ARRAY(sa.String()), server_default="{}"),
        sa.Column("visa_status",   visa_enum, server_default="unknown"),
        sa.Column("location",      sa.String(128)),
        sa.Column("yoe",           sa.Float(), server_default="0"),
        sa.Column("rate",          sa.Float(), nullable=True),
        sa.Column("resume_path",   sa.String(512), nullable=True),
        sa.Column("resume_text",   sa.Text(), nullable=True),
        sa.Column("embedding",     Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("is_active_contractor", sa.Boolean(), server_default="false"),
        sa.Column("tenure_days",   sa.Integer(), nullable=True),
        sa.Column("comms_gap_days",sa.Integer(), nullable=True),
        sa.Column("overtime_pct",  sa.Float(), nullable=True),
        sa.Column("client_feedback_score", sa.Float(), nullable=True),
        sa.Column("attrition_risk_score",  sa.Float(), nullable=True),
        sa.Column("created_at",    sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_candidates_name", "candidates", ["name"])

    # ── jobs ──────────────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id",              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title",           sa.String(256), nullable=False),
        sa.Column("client_id",       sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("jd_text",         sa.Text(), nullable=True),
        sa.Column("required_skills", sa.ARRAY(sa.String()), server_default="{}"),
        sa.Column("location",        sa.String(128)),
        sa.Column("remote_ok",       sa.Boolean(), server_default="false"),
        sa.Column("rate_min",        sa.Float(), nullable=True),
        sa.Column("rate_max",        sa.Float(), nullable=True),
        sa.Column("visa_requirement",visa_enum, nullable=True),
        sa.Column("min_yoe",         sa.Float(), server_default="0"),
        sa.Column("max_yoe",         sa.Float(), nullable=True),
        sa.Column("status",          job_status_enum, server_default="open"),
        sa.Column("embedding",       Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("created_at",      sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_jobs_title", "jobs", ["title"])

    # ── placements ────────────────────────────────────────────────────────────
    op.create_table(
        "placements",
        sa.Column("id",           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_id",       sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("recruiter_id", sa.Integer(), sa.ForeignKey("recruiters.id"), nullable=True),
        sa.Column("client_id",    sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("stage",        placement_stage_enum, server_default="submitted"),
        sa.Column("match_score",  sa.Float(), nullable=True),
        sa.Column("skill_gap",    sa.JSON(), nullable=True),
        sa.Column("bill_rate",    sa.Float(), nullable=True),
        sa.Column("pay_rate",     sa.Float(), nullable=True),
        sa.Column("margin",       sa.Float(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_placements_candidate", "placements", ["candidate_id"])
    op.create_index("ix_placements_job", "placements", ["job_id"])

    # ── timesheets ────────────────────────────────────────────────────────────
    op.create_table(
        "timesheets",
        sa.Column("id",             sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contractor_id",  sa.Integer(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("week_start",     sa.Date(), nullable=False),
        sa.Column("hours",          sa.Float(), nullable=False),
        sa.Column("overtime_hours", sa.Float(), server_default="0"),
        sa.Column("status",         timesheet_status_enum, server_default="pending"),
        sa.Column("anomaly_flag",   sa.Boolean(), server_default="false"),
        sa.Column("anomaly_score",  sa.Float(), nullable=True),
        sa.Column("anomaly_reason", sa.String(256), nullable=True),
        sa.Column("created_at",     sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_timesheets_contractor", "timesheets", ["contractor_id"])

    # ── payroll ───────────────────────────────────────────────────────────────
    op.create_table(
        "payroll",
        sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contractor_id", sa.Integer(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("period",        sa.Date(), nullable=False),
        sa.Column("bill_rate",     sa.Float(), nullable=False),
        sa.Column("pay_rate",      sa.Float(), nullable=False),
        sa.Column("margin",        sa.Float(), nullable=False),
        sa.Column("margin_pct",    sa.Float(), nullable=False),
        sa.Column("created_at",    sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_payroll_contractor", "payroll", ["contractor_id"])

    # ── predictions ───────────────────────────────────────────────────────────
    op.create_table(
        "predictions",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id",   sa.Integer(), nullable=False),
        sa.Column("model_name",  sa.String(64), nullable=False),
        sa.Column("score",       sa.Float(), nullable=False),
        sa.Column("features",    sa.JSON(), nullable=True),
        sa.Column("created_at",  sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_predictions_entity", "predictions", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("predictions")
    op.drop_table("payroll")
    op.drop_table("timesheets")
    op.drop_table("placements")
    op.drop_table("jobs")
    op.drop_table("candidates")
    op.drop_table("recruiters")
    op.drop_table("clients")

    sa.Enum(name="timesheetstatusenum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="placementstageenum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="jobstatusenum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="visastatusenum").drop(op.get_bind(), checkfirst=True)
