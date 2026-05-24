"""linkedin_auth_sessions table

Revision ID: 003_linkedin_auth_sessions
Revises: 002_operational_tables
Create Date: 2026-05-24 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "003_linkedin_auth_sessions"
down_revision = "002_operational_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linkedin_auth_sessions",
        sa.Column("state", sa.Text(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "linkedin_auth_tg_idx",
        "linkedin_auth_sessions",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    op.drop_index("linkedin_auth_tg_idx", table_name="linkedin_auth_sessions")
    op.drop_table("linkedin_auth_sessions")
