"""alumni table

Revision ID: 001_alumni_table
Revises:
Create Date: 2026-05-24 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001_alumni_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "alumni",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT()),
        sa.Column("personal_email", postgresql.CITEXT()),
        sa.Column("status", sa.Text()),
        sa.Column("batch_year", sa.Integer()),
        sa.Column("program", sa.Text()),
        sa.Column("reg_number", sa.Text()),
        sa.Column("mobile", sa.Text()),
        sa.Column("home_city", sa.Text()),
        sa.Column("home_country", sa.Text()),
        sa.Column("company", sa.Text()),
        sa.Column("designation", sa.Text()),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column(
            "extra",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("alumni_email_idx", "alumni", ["email"])
    op.create_index("alumni_personal_email_idx", "alumni", ["personal_email"])
    op.create_index("alumni_reg_number_idx", "alumni", ["reg_number"])
    op.execute("CREATE INDEX alumni_name_trgm_idx ON alumni USING gin (name gin_trgm_ops)")
    op.create_index("alumni_batch_program_idx", "alumni", ["batch_year", "program"])


def downgrade() -> None:
    op.drop_index("alumni_batch_program_idx", table_name="alumni")
    op.execute("DROP INDEX alumni_name_trgm_idx")
    op.drop_index("alumni_reg_number_idx", table_name="alumni")
    op.drop_index("alumni_personal_email_idx", table_name="alumni")
    op.drop_index("alumni_email_idx", table_name="alumni")
    op.drop_table("alumni")
    # citext / pg_trgm extensions left in place; cheap to keep
