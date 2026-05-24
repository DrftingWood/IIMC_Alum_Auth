"""operational tables

Revision ID: 002_operational_tables
Revises: 001_alumni_table
Create Date: 2026-05-24 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "002_operational_tables"
down_revision = "001_alumni_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 2. verification_cases
    op.create_table(
        "verification_cases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("claimed_alumni_id", sa.Text(), sa.ForeignKey("alumni.user_id")),
        sa.Column("submitted_name", sa.Text()),
        sa.Column("submitted_reg", sa.Text()),
        sa.Column("submitted_batch", sa.Integer()),
        sa.Column("submitted_program", sa.Text()),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("linkedin_email", postgresql.CITEXT()),
        sa.Column("linkedin_pic_url", sa.Text()),
        sa.Column("free_text_note", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("vc_status_idx", "verification_cases", ["status", "created_at"])
    op.create_index("vc_tg_user_idx", "verification_cases", ["telegram_user_id"])

    # 3. otp_codes
    op.create_table(
        "otp_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "alumni_id",
            sa.Text(),
            sa.ForeignKey("alumni.user_id"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute(
        "CREATE INDEX otp_tg_active_idx ON otp_codes (telegram_user_id) "
        "WHERE consumed_at IS NULL"
    )

    # 5. members
    op.create_table(
        "members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "alumni_id",
            sa.Text(),
            sa.ForeignKey("alumni.user_id"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("verified_via", sa.Text(), nullable=False),
        sa.Column(
            "verification_case_id",
            sa.BigInteger(),
            sa.ForeignKey("verification_cases.id"),
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text()),
        sa.Column("drift_incidents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_last_sampled_at", sa.DateTime(timezone=True)),
        sa.Column("drift_reminded_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE UNIQUE INDEX members_one_active_per_alumni "
        "ON members (alumni_id) WHERE status = 'active'"
    )
    op.execute(
        "CREATE UNIQUE INDEX members_one_active_per_tg "
        "ON members (telegram_user_id) WHERE status = 'active'"
    )

    # 7. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_email", postgresql.CITEXT(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "audit_actor_idx",
        "audit_log",
        ["actor_email", "created_at"],
        postgresql_using="btree",
    )
    op.execute(
        "CREATE INDEX audit_subject_idx ON audit_log " "(subject_type, subject_id, created_at DESC)"
    )

    # 8. invite_links
    op.create_table(
        "invite_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "alumni_id",
            sa.Text(),
            sa.ForeignKey("alumni.user_id"),
            nullable=False,
        ),
        sa.Column("invite_link", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("invite_links")
    op.execute("DROP INDEX audit_subject_idx")
    op.drop_index("audit_actor_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.execute("DROP INDEX members_one_active_per_tg")
    op.execute("DROP INDEX members_one_active_per_alumni")
    op.drop_table("members")
    op.execute("DROP INDEX otp_tg_active_idx")
    op.drop_table("otp_codes")
    op.drop_index("vc_tg_user_idx", table_name="verification_cases")
    op.drop_index("vc_status_idx", table_name="verification_cases")
    op.drop_table("verification_cases")
