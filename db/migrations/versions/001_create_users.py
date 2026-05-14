"""create users table

Revision ID: 001_users
Revises:
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = "001_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id",         sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("username",   sa.String(64),    nullable=False, unique=True),
        sa.Column("name",       sa.String(128),   nullable=False),
        sa.Column("email",      sa.String(256),   nullable=False, unique=True),
        sa.Column("role",       sa.Enum("recruiter","manager","exec","compliance",
                                        name="roleenum"), nullable=False,
                  server_default="recruiter"),
        sa.Column("is_active",  sa.Boolean(),     server_default="true"),
        sa.Column("created_at", sa.DateTime(),    server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(),    server_default=sa.text("now()")),
    )
    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS roleenum")
