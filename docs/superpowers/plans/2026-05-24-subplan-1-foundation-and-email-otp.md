# Sub-Plan 1 — Foundation + Verification Core + Bot Email-OTP Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working end-to-end Email-OTP verification flow: an IIM C alum DMs the bot, enters their Reg#, receives a 6-digit OTP at their registered email, enters the code, picks a display name, and gets a one-time invite link to the Telegram supergroup. The bot enforces membership at group-join time.

**Architecture:** A single Python process (`src/bot`) runs an aiogram long-polling bot. All persistence is PostgreSQL via SQLAlchemy 2.x async. The verification flow is an aiogram FSM with one state per question. The "claim and bind" operation is a single Postgres transaction that uses `SELECT … FOR UPDATE` plus partial UNIQUE indexes to make double-claiming atomically impossible. Tests use real Postgres via `testcontainers`; Telegram is exercised by feeding fake updates into `dispatcher.feed_update`.

**Tech Stack:** Python 3.12 · aiogram 3.x · SQLAlchemy 2.x + Alembic + asyncpg · pydantic-settings · bcrypt · httpx (Brevo API) · openpyxl (importer) · pytest + pytest-asyncio + testcontainers · ruff · mypy.

**Out of scope (later sub-plans):** LinkedIn OAuth path · admin dashboard · drift watcher · reconciliation cron · `/forget_me` erasure · production deployment.

---

## File structure produced by this sub-plan

```
IIMC_Alum_Auth/
├── pyproject.toml
├── Makefile
├── ruff.toml
├── mypy.ini
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_alumni_table.py
│       └── 002_operational_tables.py
├── src/
│   ├── __init__.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── config.py            # pydantic-settings env loader
│   │   ├── db.py                # async engine + session factory
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── audit.py             # audit_log writer
│   │   ├── email.py             # Brevo client + dev mode
│   │   ├── otp.py               # generate / hash / verify
│   │   ├── display_name.py      # canonical name + collision suffix
│   │   └── verification.py      # claim_and_bind() transaction
│   └── bot/
│       ├── __init__.py
│       ├── __main__.py          # aiogram entrypoint, long-polling
│       └── handlers/
│           ├── __init__.py
│           ├── start.py         # /start command, method choice
│           ├── verify_email.py  # Email OTP FSM
│           └── group_events.py  # on_chat_member_joined
├── scripts/
│   └── import_directory.py      # xlsx → alumni
└── tests/
    ├── __init__.py
    ├── conftest.py              # Postgres testcontainer, sample directory loader
    ├── factories.py             # factory_boy: alumni, members, etc.
    ├── fixtures/
    │   └── make_sample_xlsx.py  # generates alumni_sample.xlsx (no binary in git)
    ├── unit/
    │   ├── __init__.py
    │   ├── test_otp.py
    │   ├── test_display_name.py
    │   ├── test_email_mask.py
    │   └── test_email_dev_mode.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_importer.py
    │   ├── test_models.py
    │   ├── test_audit.py
    │   ├── test_otp_lifecycle.py
    │   └── test_verification.py
    └── e2e/
        ├── __init__.py
        └── test_email_otp_happy_path.py
```

**Total: 21 tasks across 8 phases. Each task: write failing test → run (verify failure) → implement → run (verify pass) → commit.**

---

## Phase A — Project foundation

### Task 1: Initialize Python project with `uv`, lint/type configs

**Files:**
- Create: `pyproject.toml`
- Create: `ruff.toml`
- Create: `mypy.ini`
- Create: `Makefile`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/shared/__init__.py`
- Create: `src/bot/__init__.py`
- Create: `src/bot/handlers/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/e2e/__init__.py`

- [ ] **Step 1: Install `uv` if not already present**

```bash
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Run `uv --version` to confirm. Expected output: `uv 0.x.x` (any 0.x).

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "iimc-alum-auth"
version = "0.1.0"
description = "IIM C alumni Telegram verification system"
requires-python = ">=3.12"
dependencies = [
    "aiogram>=3.4,<4",
    "sqlalchemy>=2.0,<3",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "httpx>=0.27",
    "bcrypt>=4.1",
    "openpyxl>=3.1",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "testcontainers[postgres]>=4.0",
    "respx>=0.21",
    "factory-boy>=3.3",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-bcrypt",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes
    "I",    # isort
    "B",    # bugbear
    "UP",   # pyupgrade
    "ASYNC",
    "S",    # bandit (security)
    "T20",  # no print
    "SIM",  # simplify
]
ignore = ["S101"]  # allow assert in tests

[lint.per-file-ignores]
"tests/**" = ["S105", "S106", "S311"]  # test passwords, hardcoded secrets, weak rng OK in tests
```

- [ ] **Step 4: Write `mypy.ini`**

```ini
[mypy]
python_version = 3.12
strict = true
ignore_missing_imports = false
plugins = pydantic.mypy

[mypy-testcontainers.*]
ignore_missing_imports = true

[mypy-factory.*]
ignore_missing_imports = true
```

- [ ] **Step 5: Write `Makefile`**

```makefile
.PHONY: install dev test test-unit test-int test-e2e lint type fmt migrate seed clean

install:
	uv sync

dev:
	docker compose up -d postgres
	uv run alembic upgrade head
	uv run python scripts/import_directory.py tests/fixtures/alumni_sample.xlsx
	uv run python -m src.bot

test: test-unit test-int test-e2e

test-unit:
	uv run pytest tests/unit -v

test-int:
	uv run pytest tests/integration -v

test-e2e:
	uv run pytest tests/e2e -v

lint:
	uv run ruff check src tests scripts

type:
	uv run mypy src

fmt:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

migrate:
	uv run alembic upgrade head

seed:
	uv run python scripts/import_directory.py tests/fixtures/alumni_sample.xlsx

clean:
	docker compose down -v
```

- [ ] **Step 6: Write `.env.example`**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5433/iimc_dev

# Telegram
TELEGRAM_BOT_TOKEN=replace-me-from-botfather
TELEGRAM_GROUP_CHAT_ID=-1001234567890

# OTP
OTP_PEPPER=replace-me-with-a-long-random-string

# Email (Brevo)
BREVO_API_KEY=replace-me
BREVO_FROM_EMAIL=noreply@example.com
BREVO_FROM_NAME=IIM C Alumni Verification
# Set to "true" to print OTPs to console instead of calling Brevo (dev only)
EMAIL_DEV_MODE=true

# App
LOG_LEVEL=INFO
```

- [ ] **Step 7: Create empty package init files**

```bash
# Create empty __init__.py files
mkdir -p src/shared src/bot/handlers tests/unit tests/integration tests/e2e
for f in src/__init__.py src/shared/__init__.py src/bot/__init__.py src/bot/handlers/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/e2e/__init__.py; do
  touch "$f"
done
```

- [ ] **Step 8: Install dependencies**

```bash
uv sync
```

Expected: `uv` resolves and installs all deps, writes `uv.lock`. The command finishes without errors.

- [ ] **Step 9: Run `ruff` and `mypy` to confirm tooling works**

```bash
uv run ruff check src tests scripts
uv run mypy src
```

Expected: both commands succeed (no files yet means no findings).

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock ruff.toml mypy.ini Makefile .env.example src tests
git commit -m "chore: initialize Python project with uv, ruff, mypy, and Makefile"
```

---

### Task 2: Add docker-compose for local Postgres

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: iimc_postgres_dev
    environment:
      POSTGRES_DB: iimc_dev
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d iimc_dev"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
```

- [ ] **Step 2: Start Postgres and verify it's healthy**

```bash
docker compose up -d postgres
docker compose ps
```

Expected: `iimc_postgres_dev` shows `Up (healthy)` within ~15s.

- [ ] **Step 3: Verify connectivity**

```bash
docker compose exec postgres psql -U app -d iimc_dev -c "SELECT 1 AS ok;"
```

Expected: returns a single row with `ok = 1`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker-compose for local Postgres dev"
```

---

### Task 3: Add pre-commit hooks (gitleaks) + GitHub Actions CI skeleton

**Files:**
- Create: `.pre-commit-config.yaml`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: no-xlsx
        name: Block .xlsx files from being committed
        entry: bash -c 'if git diff --cached --name-only | grep -E "\.xlsx?$"; then echo "ERROR: .xlsx files must not be committed"; exit 1; fi'
        language: system
        pass_filenames: false
```

- [ ] **Step 2: Install pre-commit hooks**

```bash
uv tool install pre-commit
pre-commit install
```

Expected: hooks installed into `.git/hooks/pre-commit`.

- [ ] **Step 3: Test the no-xlsx hook**

```bash
# Stage the Joka_Directory_Final.xlsx — should be blocked
git add Joka_Directory_Final.xlsx 2>&1 || echo "blocked at add (gitignore)"
# (.gitignore already blocks it; this confirms belt-and-braces)
```

Expected: `git add` is silently ignored because of `.gitignore`; if you `git add -f Joka_Directory_Final.xlsx`, the pre-commit hook would block the commit.

- [ ] **Step 4: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "0.4.18"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync

      - name: Lint with ruff
        run: uv run ruff check src tests scripts

      - name: Type-check with mypy
        run: uv run mypy src

      - name: Run unit tests
        run: uv run pytest tests/unit -v

      - name: Run integration tests
        run: uv run pytest tests/integration -v
        env:
          # testcontainers spins up its own Postgres; no DATABASE_URL needed here
          OTP_PEPPER: "ci-pepper-not-secret"
          TELEGRAM_BOT_TOKEN: "ci-fake-token"
          TELEGRAM_GROUP_CHAT_ID: "-100000000000"
          BREVO_API_KEY: "ci-fake-key"
          BREVO_FROM_EMAIL: "noreply@example.com"
          BREVO_FROM_NAME: "CI"
          EMAIL_DEV_MODE: "true"
```

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml
git commit -m "ci: add pre-commit hooks (gitleaks, ruff, no-xlsx) and GitHub Actions"
```

---

## Phase B — Database schema

### Task 4: Initialize Alembic and write migration 001 (alumni table)

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/001_alumni_table.py`

- [ ] **Step 1: Initialize Alembic**

```bash
uv run alembic init -t async alembic
```

This creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, and an empty `alembic/versions/` directory.

- [ ] **Step 2: Edit `alembic.ini`**

Find the `sqlalchemy.url` line and replace it with:

```ini
sqlalchemy.url =
```

(blank — we'll set it from env in `env.py`). Also add at the top:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
```

- [ ] **Step 3: Edit `alembic/env.py`**

Replace its contents with:

```python
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

# Pull DATABASE_URL from env so we don't duplicate config
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL env var is required for migrations")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic doesn't autogenerate for this plan — we hand-write migrations
target_metadata = None


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 4: Write the alumni-table migration**

Create `alembic/versions/001_alumni_table.py` with this exact content (note the revision string `001_alumni_table`):

```python
"""alumni table

Revision ID: 001_alumni_table
Revises:
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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
    op.execute(
        "CREATE INDEX alumni_name_trgm_idx ON alumni USING gin (name gin_trgm_ops)"
    )
    op.create_index("alumni_batch_program_idx", "alumni", ["batch_year", "program"])


def downgrade() -> None:
    op.drop_index("alumni_batch_program_idx", table_name="alumni")
    op.execute("DROP INDEX alumni_name_trgm_idx")
    op.drop_index("alumni_reg_number_idx", table_name="alumni")
    op.drop_index("alumni_personal_email_idx", table_name="alumni")
    op.drop_index("alumni_email_idx", table_name="alumni")
    op.drop_table("alumni")
    # citext / pg_trgm extensions left in place; cheap to keep
```

- [ ] **Step 5: Run migration against local Postgres**

```bash
export DATABASE_URL="postgresql+asyncpg://app:app@localhost:5433/iimc_dev"
# (Windows PowerShell:  $env:DATABASE_URL="postgresql+asyncpg://app:app@localhost:5433/iimc_dev")
uv run alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 001_alumni_table, alumni table`.

- [ ] **Step 6: Verify the table exists**

```bash
docker compose exec postgres psql -U app -d iimc_dev -c "\d alumni"
```

Expected: table description with all columns and 5 indexes listed.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini alembic/env.py alembic/script.py.mako alembic/versions/001_alumni_table.py
git commit -m "feat(db): alembic init and migration 001 (alumni table)"
```

---

### Task 5: Migration 002 — operational tables

**Files:**
- Create: `alembic/versions/002_operational_tables.py`

- [ ] **Step 1: Write the operational-tables migration**

```python
"""operational tables

Revision ID: 002_operational_tables
Revises: 001_alumni_table
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

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
        "CREATE INDEX audit_subject_idx ON audit_log "
        "(subject_type, subject_id, created_at DESC)"
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
```

- [ ] **Step 2: Run the migration**

```bash
uv run alembic upgrade head
```

Expected: `Running upgrade 001_alumni_table -> 002_operational_tables, operational tables`.

- [ ] **Step 3: Verify all tables exist**

```bash
docker compose exec postgres psql -U app -d iimc_dev -c "\dt"
```

Expected: lists `alumni`, `verification_cases`, `otp_codes`, `members`, `audit_log`, `invite_links`, plus the `alembic_version` table.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/002_operational_tables.py
git commit -m "feat(db): migration 002 (operational tables with partial unique indexes)"
```

---

### Task 6: Verify migrations are reversible

This is a guard against future migrations being non-reversible. Pure verification task.

- [ ] **Step 1: Downgrade fully**

```bash
uv run alembic downgrade base
```

Expected: both migrations roll back. `\dt` in psql shows only `alembic_version`.

- [ ] **Step 2: Re-upgrade**

```bash
uv run alembic upgrade head
```

Expected: both migrations re-apply cleanly. `\dt` shows all tables again.

- [ ] **Step 3: Commit (empty commit to mark the verification — optional)**

No commit needed; this is a runtime check only.

---

## Phase C — Shared layer

### Task 7: `src/shared/config.py` — pydantic-settings env loader

**Files:**
- Create: `src/shared/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:

```python
import pytest

from src.shared.config import Settings


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("OTP_PEPPER", "x" * 32)
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    monkeypatch.setenv("EMAIL_DEV_MODE", "true")

    s = Settings()
    assert s.telegram_group_chat_id == -100123
    assert s.email_dev_mode is True
    assert s.otp_pepper == "x" * 32


def test_settings_missing_pepper_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTP_PEPPER", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")

    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.shared.config'`.

- [ ] **Step 3: Implement `src/shared/config.py`**

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    telegram_bot_token: str
    telegram_group_chat_id: int
    otp_pepper: str = Field(min_length=16)
    brevo_api_key: str
    brevo_from_email: str
    brevo_from_name: str
    email_dev_mode: bool = False
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/config.py tests/unit/test_config.py
git commit -m "feat(shared): pydantic-settings config loader"
```

---

### Task 8: `src/shared/db.py` — async engine + session factory + testcontainer conftest

**Files:**
- Create: `src/shared/db.py`
- Create: `tests/conftest.py`
- Test: `tests/integration/test_models.py` (smoke test in next task; this task is infrastructure)

- [ ] **Step 1: Write `src/shared/db.py`**

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Open a session, commit on success, rollback on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def reset_engine_for_tests() -> None:
    """Test helper: dispose the cached engine so a new DATABASE_URL takes effect."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
```

- [ ] **Step 2: Write `tests/conftest.py`** with testcontainer Postgres

```python
import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """asyncpg-format URL for the session-wide test Postgres."""
    raw = postgres_container.get_connection_url()
    # testcontainers returns psycopg2 URL; convert to asyncpg
    return raw.replace("postgresql+psycopg2", "postgresql+asyncpg").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session", autouse=True)
def _env(database_url: str) -> None:
    """Inject all required env vars before any test runs."""
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    os.environ.setdefault("TELEGRAM_GROUP_CHAT_ID", "-100000000000")
    os.environ.setdefault("OTP_PEPPER", "test-pepper-please-ignore-32chars-min")
    os.environ.setdefault("BREVO_API_KEY", "test-brevo-key")
    os.environ.setdefault("BREVO_FROM_EMAIL", "test@example.com")
    os.environ.setdefault("BREVO_FROM_NAME", "Test")
    os.environ.setdefault("EMAIL_DEV_MODE", "true")


@pytest.fixture(scope="session", autouse=True)
def _migrations(_env: None) -> None:
    """Run all Alembic migrations against the test container once per session."""
    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def session(_migrations: None) -> AsyncIterator[AsyncSession]:
    """Per-test transaction that rolls back at teardown."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()
```

- [ ] **Step 3: Write a minimal smoke test**

`tests/integration/test_models.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_database_is_up(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1 AS ok"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_alumni_table_exists(session: AsyncSession) -> None:
    result = await session.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'alumni'"
        )
    )
    assert result.scalar_one() == 1
```

- [ ] **Step 4: Run integration tests**

```bash
uv run pytest tests/integration/test_models.py -v
```

Expected: PASS (2 passed). First run will be slow (~30s) as testcontainers pulls the Postgres image.

- [ ] **Step 5: Commit**

```bash
git add src/shared/db.py tests/conftest.py tests/integration/test_models.py
git commit -m "feat(shared): async db session factory + testcontainers conftest"
```

---

### Task 9: `src/shared/models.py` — SQLAlchemy models

**Files:**
- Create: `src/shared/models.py`
- Modify: `tests/integration/test_models.py` (add model round-trip tests)

- [ ] **Step 1: Write the failing tests (append to existing file)**

Append to `tests/integration/test_models.py`:

```python
from datetime import datetime, timedelta, timezone

from src.shared.models import (
    Alumni,
    AuditLog,
    InviteLink,
    Member,
    OtpCode,
    VerificationCase,
)


@pytest.mark.asyncio
async def test_alumni_round_trip(session: AsyncSession) -> None:
    a = Alumni(
        user_id="testuser1",
        name="Test User",
        email="test@example.com",
        program="PGP",
        batch_year=2020,
    )
    session.add(a)
    await session.flush()
    fetched = await session.get(Alumni, "testuser1")
    assert fetched is not None
    assert fetched.name == "Test User"
    assert fetched.email == "test@example.com"
    assert fetched.extra == {}


@pytest.mark.asyncio
async def test_member_unique_active_alumni_constraint(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    a = Alumni(user_id="u1", name="One", program="PGP", batch_year=2015)
    session.add(a)
    await session.flush()

    m1 = Member(
        alumni_id="u1",
        telegram_user_id=111,
        display_name="One (PGP 2015)",
        status="active",
        verified_via="email_otp",
    )
    session.add(m1)
    await session.flush()

    m2 = Member(
        alumni_id="u1",
        telegram_user_id=222,
        display_name="One (PGP 2015)",
        status="active",
        verified_via="email_otp",
    )
    session.add(m2)
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_otp_code_round_trip(session: AsyncSession) -> None:
    a = Alumni(user_id="u2", name="Two", program="PGP", batch_year=2016)
    session.add(a)
    await session.flush()
    o = OtpCode(
        telegram_user_id=333,
        alumni_id="u2",
        code_hash="$2b$12$abc",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    session.add(o)
    await session.flush()
    assert o.id is not None
    assert o.attempts == 0
```

- [ ] **Step 2: Run tests (expect import failure)**

```bash
uv run pytest tests/integration/test_models.py -v
```

Expected: FAIL with `ImportError: cannot import name 'Alumni' from 'src.shared.models'`.

- [ ] **Step 3: Implement `src/shared/models.py`**

```python
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Alumni(Base):
    __tablename__ = "alumni"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT)
    personal_email: Mapped[str | None] = mapped_column(CITEXT)
    status: Mapped[str | None] = mapped_column(Text)
    batch_year: Mapped[int | None] = mapped_column(Integer)
    program: Mapped[str | None] = mapped_column(Text)
    reg_number: Mapped[str | None] = mapped_column(Text)
    mobile: Mapped[str | None] = mapped_column(Text)
    home_city: Mapped[str | None] = mapped_column(Text)
    home_country: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VerificationCase(Base):
    __tablename__ = "verification_cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_alumni_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("alumni.user_id")
    )
    submitted_name: Mapped[str | None] = mapped_column(Text)
    submitted_reg: Mapped[str | None] = mapped_column(Text)
    submitted_batch: Mapped[int | None] = mapped_column(Integer)
    submitted_program: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    linkedin_email: Mapped[str | None] = mapped_column(CITEXT)
    linkedin_pic_url: Mapped[str | None] = mapped_column(Text)
    free_text_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alumni_id: Mapped[str] = mapped_column(
        Text, ForeignKey("alumni.user_id"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alumni_id: Mapped[str] = mapped_column(
        Text, ForeignKey("alumni.user_id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    verified_via: Mapped[str] = mapped_column(Text, nullable=False)
    verification_case_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verification_cases.id")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    drift_incidents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drift_last_sampled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    drift_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InviteLink(Base):
    __tablename__ = "invite_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alumni_id: Mapped[str] = mapped_column(
        Text, ForeignKey("alumni.user_id"), nullable=False
    )
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/integration/test_models.py -v
```

Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/models.py tests/integration/test_models.py
git commit -m "feat(shared): SQLAlchemy models for alumni and operational tables"
```

---

### Task 10: `src/shared/audit.py` — audit log writer

**Files:**
- Create: `src/shared/audit.py`
- Test: `tests/integration/test_audit.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_audit.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.audit import write_audit
from src.shared.models import AuditLog


@pytest.mark.asyncio
async def test_write_audit_creates_row(session: AsyncSession) -> None:
    await write_audit(
        session,
        actor_email="system@bot",
        action="member_created",
        subject_type="member",
        subject_id="42",
        details={"alumni_id": "u1", "via": "email_otp"},
    )
    await session.flush()

    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_email == "system@bot"
    assert row.action == "member_created"
    assert row.subject_type == "member"
    assert row.subject_id == "42"
    assert row.details == {"alumni_id": "u1", "via": "email_otp"}


@pytest.mark.asyncio
async def test_write_audit_details_optional(session: AsyncSession) -> None:
    await write_audit(
        session,
        actor_email="system@bot",
        action="member_left",
        subject_type="member",
        subject_id="42",
    )
    await session.flush()
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].details is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/integration/test_audit.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/shared/audit.py`**

```python
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    actor_email: str,
    action: str,
    subject_type: str,
    subject_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a row to audit_log. Caller is responsible for committing the session."""
    session.add(
        AuditLog(
            actor_email=actor_email,
            action=action,
            subject_type=subject_type,
            subject_id=str(subject_id),
            details=details,
        )
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/integration/test_audit.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/audit.py tests/integration/test_audit.py
git commit -m "feat(shared): audit_log writer"
```

---

## Phase D — Directory importer

### Task 11: `scripts/import_directory.py` + sample fixture generator

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/make_sample_xlsx.py`
- Create: `scripts/import_directory.py`
- Test: `tests/integration/test_importer.py`

- [ ] **Step 1: Write the fixture generator** (generates `alumni_sample.xlsx` on demand — keeps no binary in git)

`tests/fixtures/__init__.py`:
```python
```
(empty)

`tests/fixtures/make_sample_xlsx.py`:

```python
"""Generate a 50-row synthetic alumni Excel file for tests and local dev.

Run: python -m tests.fixtures.make_sample_xlsx [output_path]
"""
import sys
from pathlib import Path

import openpyxl

HEADERS = [
    "User ID", "Name", "Email", "Personal Email", "Status", "Batch Year",
    "Program", "Joining Year", "Passing Year", "Reg Number", "Gender",
    "Mobile", "Home City", "Home Country", "Company", "Designation",
    "Office City", "Hostel", "Room Number", "UG Degree", "UG Institute",
    "Summer Internship Firm", "Summer Internship Domain", "Finals Firm",
    "Finals Domain", "LinkedIn URL", "Hobbies",
]

PROGRAMS = ["PGP", "PGDM", "LDP", "FP", "PGPEX"]


def make_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(1, 51):
        program = PROGRAMS[i % len(PROGRAMS)]
        batch = 2000 + (i % 25)
        rows.append(
            {
                "User ID": f"sample{i:03d}",
                "Name": f"Test Alum {i:03d}",
                "Email": f"alum{i:03d}@example.com",
                "Personal Email": f"alum{i:03d}.personal@example.org" if i % 3 == 0 else None,
                "Status": "Alumni" if i % 4 != 0 else None,
                "Batch Year": batch,
                "Program": program,
                "Joining Year": batch - 2,
                "Passing Year": batch,
                "Reg Number": f"{program}/{batch}/{i:04d}",
                "Gender": "M" if i % 2 == 0 else "F",
                "Mobile": f"99999{i:05d}" if i % 4 == 0 else None,
                "Home City": "TestCity",
                "Home Country": "TestCountry",
                "Company": "TestCo" if i % 2 == 0 else None,
                "Designation": "Engineer" if i % 2 == 0 else None,
                "Office City": "TestOfficeCity",
                "Hostel": "OH",
                "Room Number": f"H{i % 4 + 1}-{i:03d}",
                "UG Degree": "B.Tech",
                "UG Institute": "TestUG",
                "Summer Internship Firm": None,
                "Summer Internship Domain": None,
                "Finals Firm": None,
                "Finals Domain": None,
                "LinkedIn URL": f"https://linkedin.com/in/alum-{i:03d}" if i % 12 == 0 else None,
                "Hobbies": None,
            }
        )
    # Inject a name-collision pair for testing display-name disambiguation
    rows.append(
        {
            **rows[0],
            "User ID": "sample001b",
            "Reg Number": "PGP/2001/0099",
            "Email": "alum001b@example.com",
            "Personal Email": None,
            "Mobile": None,
        }
    )
    return rows


def write(out: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All Students"
    ws.append(HEADERS)
    for r in make_rows():
        ws.append([r.get(h) for h in HEADERS])
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/alumni_sample.xlsx")
    write(out)
    print(f"Wrote {out}")
```

- [ ] **Step 2: Generate the fixture once locally**

```bash
uv run python -m tests.fixtures.make_sample_xlsx
ls tests/fixtures/alumni_sample.xlsx
```

Expected: file exists, ~10 KB. The `.gitignore` rule on `*.xlsx` keeps it out of git — that's intentional. Tests regenerate it via the conftest fixture below.

- [ ] **Step 3: Write the importer test**

`tests/integration/test_importer.py`:

```python
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.import_directory import import_directory
from src.shared.models import Alumni
from tests.fixtures.make_sample_xlsx import write as write_sample


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    p = tmp_path / "sample.xlsx"
    write_sample(p)
    return p


@pytest.mark.asyncio
async def test_import_inserts_all_rows(
    session: AsyncSession, sample_xlsx: Path
) -> None:
    summary = await import_directory(session, sample_xlsx)
    await session.flush()
    assert summary.inserted == 51
    assert summary.updated == 0

    count = (await session.execute(select(func.count()).select_from(Alumni))).scalar_one()
    assert count == 51


@pytest.mark.asyncio
async def test_import_is_idempotent(
    session: AsyncSession, sample_xlsx: Path
) -> None:
    await import_directory(session, sample_xlsx)
    await session.flush()
    summary2 = await import_directory(session, sample_xlsx)
    await session.flush()
    assert summary2.inserted == 0
    assert summary2.updated == 51


@pytest.mark.asyncio
async def test_import_preserves_extra_columns(
    session: AsyncSession, sample_xlsx: Path
) -> None:
    await import_directory(session, sample_xlsx)
    await session.flush()
    a = await session.get(Alumni, "sample001")
    assert a is not None
    assert a.extra.get("Hostel") == "OH"
    assert "UG Degree" in a.extra
```

- [ ] **Step 4: Run the test to verify it fails**

```bash
uv run pytest tests/integration/test_importer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.import_directory'`.

- [ ] **Step 5: Implement `scripts/__init__.py` and `scripts/import_directory.py`**

Create `scripts/__init__.py`:
```python
```
(empty)

Create `scripts/import_directory.py`:

```python
"""Idempotent loader for the IIM C alumni directory Excel file."""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db import session_scope
from src.shared.models import Alumni

# Excel header → Alumni model attribute. Anything not listed here goes into `extra`.
COLUMN_MAP: dict[str, str] = {
    "User ID": "user_id",
    "Name": "name",
    "Email": "email",
    "Personal Email": "personal_email",
    "Status": "status",
    "Batch Year": "batch_year",
    "Program": "program",
    "Reg Number": "reg_number",
    "Mobile": "mobile",
    "Home City": "home_city",
    "Home Country": "home_country",
    "Company": "company",
    "Designation": "designation",
    "LinkedIn URL": "linkedin_url",
}


@dataclass
class ImportSummary:
    inserted: int
    updated: int


def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _parse_row(headers: list[str], row: tuple[Any, ...]) -> dict[str, Any] | None:
    """Convert one Excel row into a dict suitable for Alumni insert. None if invalid."""
    record = {h: _normalize(v) for h, v in zip(headers, row, strict=False)}
    user_id = record.get("User ID")
    name = record.get("Name")
    if not user_id or not name:
        return None  # skip rows without identifier or name

    fields: dict[str, Any] = {"extra": {}}
    for header, raw in record.items():
        attr = COLUMN_MAP.get(header)
        if attr is None:
            if raw is not None:
                fields["extra"][header] = raw
            continue
        fields[attr] = raw
    return fields


async def import_directory(session: AsyncSession, path: Path) -> ImportSummary:
    """Load every row of the spreadsheet into the `alumni` table.

    Idempotent: an existing row is updated rather than re-inserted, based on
    a `SELECT … WHERE user_id = …` pre-check (correct insert/update counts at
    the cost of one extra round-trip per row; acceptable for ~38k rows).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["All Students"] if "All Students" in wb.sheetnames else wb.active

    iterator = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(iterator)]

    inserted = 0
    updated = 0
    for raw_row in iterator:
        fields = _parse_row(headers, raw_row)
        if fields is None:
            continue
        existing = await session.get(Alumni, fields["user_id"])
        if existing is None:
            session.add(Alumni(**fields))
            inserted += 1
        else:
            for k, v in fields.items():
                if k == "user_id":
                    continue
                setattr(existing, k, v)
            updated += 1
    return ImportSummary(inserted=inserted, updated=updated)


async def _main(path: Path) -> None:
    async with session_scope() as session:
        summary = await import_directory(session, path)
        print(f"Imported: {summary.inserted} new, {summary.updated} updated.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_directory <path-to-xlsx>")
        sys.exit(1)
    asyncio.run(_main(Path(sys.argv[1])))
```

- [ ] **Step 6: Run the test**

```bash
uv run pytest tests/integration/test_importer.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/import_directory.py tests/fixtures/__init__.py tests/fixtures/make_sample_xlsx.py tests/integration/test_importer.py
git commit -m "feat(scripts): idempotent directory importer with fixture generator"
```

---

## Phase E — Email & OTP infrastructure

### Task 12: `src/shared/email.py` — Brevo client with dev mode

**Files:**
- Create: `src/shared/email.py`
- Test: `tests/unit/test_email_dev_mode.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_email_dev_mode.py`:

```python
import os

import httpx
import pytest
import respx

from src.shared.email import send_otp_email


@pytest.mark.asyncio
async def test_dev_mode_writes_to_outbox(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EMAIL_DEV_MODE", "true")
    from src.shared import config

    config._settings = None  # reset cache

    await send_otp_email(to="user@example.com", code="123456")

    out = capsys.readouterr().out
    assert "user@example.com" in out
    assert "123456" in out


@pytest.mark.asyncio
async def test_brevo_mode_calls_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_DEV_MODE", "false")
    monkeypatch.setenv("BREVO_API_KEY", "fake-key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    from src.shared import config

    config._settings = None

    with respx.mock(base_url="https://api.brevo.com") as r:
        route = r.post("/v3/smtp/email").mock(
            return_value=httpx.Response(201, json={"messageId": "abc"})
        )
        await send_otp_email(to="user@example.com", code="654321")
        assert route.called
        request = route.calls.last.request
        body = request.read().decode()
        assert "user@example.com" in body
        assert "654321" in body
        assert request.headers["api-key"] == "fake-key"
```

- [ ] **Step 2: Run test (expect failure)**

```bash
uv run pytest tests/unit/test_email_dev_mode.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.shared.email'`.

- [ ] **Step 3: Implement `src/shared/email.py`**

```python
import httpx

from src.shared.config import get_settings


async def send_otp_email(*, to: str, code: str) -> None:
    """Send a 6-digit OTP. In EMAIL_DEV_MODE prints to stdout instead of calling Brevo."""
    settings = get_settings()
    subject = "Your IIM C Alumni verification code"
    body_html = (
        f"<p>Your verification code is <strong>{code}</strong>.</p>"
        f"<p>It expires in 10 minutes and can be used once.</p>"
        f"<p>If you didn't request this, you can ignore this email.</p>"
    )
    body_text = (
        f"Your verification code is {code}.\n"
        f"It expires in 10 minutes and can be used once.\n"
        f"If you didn't request this, you can ignore this email."
    )

    if settings.email_dev_mode:
        print(f"[DEV EMAIL] to={to} subject={subject!r} code={code}")  # noqa: T201
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.brevo_api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json={
                "sender": {
                    "email": settings.brevo_from_email,
                    "name": settings.brevo_from_name,
                },
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": body_html,
                "textContent": body_text,
            },
        )
        resp.raise_for_status()
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_email_dev_mode.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/email.py tests/unit/test_email_dev_mode.py
git commit -m "feat(shared): Brevo email client with dev-mode stdout fallback"
```

---

### Task 13: `src/shared/otp.py` — generate, hash, verify

**Files:**
- Create: `src/shared/otp.py`
- Test: `tests/unit/test_otp.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_otp.py`:

```python
import pytest

from src.shared.otp import generate_code, hash_code, verify_code


def test_generate_code_returns_six_digit_string() -> None:
    for _ in range(50):
        c = generate_code()
        assert len(c) == 6
        assert c.isdigit()


def test_hash_and_verify_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_PEPPER", "p" * 32)
    from src.shared import config

    config._settings = None

    h = hash_code("123456")
    assert h != "123456"
    assert verify_code("123456", h) is True
    assert verify_code("999999", h) is False


def test_verify_rejects_modified_pepper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_PEPPER", "p" * 32)
    from src.shared import config

    config._settings = None
    h = hash_code("424242")

    monkeypatch.setenv("OTP_PEPPER", "q" * 32)
    config._settings = None
    assert verify_code("424242", h) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_otp.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/shared/otp.py`**

```python
import secrets

import bcrypt

from src.shared.config import get_settings


def generate_code() -> str:
    """Return a uniformly-random 6-digit string, zero-padded."""
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str) -> str:
    pepper = get_settings().otp_pepper
    salted = (code + pepper).encode()
    return bcrypt.hashpw(salted, bcrypt.gensalt(rounds=12)).decode()


def verify_code(code: str, hashed: str) -> bool:
    pepper = get_settings().otp_pepper
    salted = (code + pepper).encode()
    try:
        return bcrypt.checkpw(salted, hashed.encode())
    except ValueError:
        return False
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_otp.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/otp.py tests/unit/test_otp.py
git commit -m "feat(shared): OTP generator, bcrypt+pepper hasher and verifier"
```

---

### Task 14: OTP lifecycle integration test (issue → verify → consume → expire)

This task wires `otp.py` into a stateful "OTP service" that handles the full lifecycle.

**Files:**
- Modify: `src/shared/otp.py` (add `issue_otp` and `verify_otp_submission`)
- Test: `tests/integration/test_otp_lifecycle.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_otp_lifecycle.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import Alumni, OtpCode
from src.shared.otp import (
    OtpResult,
    issue_otp,
    verify_otp_submission,
)


@pytest.fixture
async def alum(session: AsyncSession) -> Alumni:
    a = Alumni(
        user_id="otpu1",
        name="OTP One",
        email="otp1@example.com",
        program="PGP",
        batch_year=2018,
    )
    session.add(a)
    await session.flush()
    return a


@pytest.mark.asyncio
async def test_issue_otp_creates_row(session: AsyncSession, alum: Alumni) -> None:
    code = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    assert len(code) == 6 and code.isdigit()

    rows = (await session.execute(select(OtpCode))).scalars().all()
    assert len(rows) == 1
    assert rows[0].telegram_user_id == 111
    assert rows[0].consumed_at is None
    assert rows[0].attempts == 0


@pytest.mark.asyncio
async def test_verify_otp_happy_path(session: AsyncSession, alum: Alumni) -> None:
    code = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    result = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=code
    )
    await session.flush()
    assert result == OtpResult.OK


@pytest.mark.asyncio
async def test_verify_otp_wrong_code_increments(
    session: AsyncSession, alum: Alumni
) -> None:
    await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    r1 = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted="000000"
    )
    assert r1 == OtpResult.WRONG
    row = (await session.execute(select(OtpCode))).scalars().one()
    assert row.attempts == 1


@pytest.mark.asyncio
async def test_verify_otp_three_strikes(session: AsyncSession, alum: Alumni) -> None:
    code = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    for _ in range(3):
        await verify_otp_submission(
            session, telegram_user_id=111, alumni_id=alum.user_id, submitted="000000"
        )
    # 4th attempt with correct code is still rejected — exhausted
    r = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=code
    )
    assert r == OtpResult.EXHAUSTED


@pytest.mark.asyncio
async def test_verify_otp_after_expiry(session: AsyncSession, alum: Alumni) -> None:
    code = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    # Force-expire by direct UPDATE
    row = (await session.execute(select(OtpCode))).scalars().one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.flush()
    r = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=code
    )
    assert r == OtpResult.EXPIRED


@pytest.mark.asyncio
async def test_issuing_invalidates_prior_active_otp(
    session: AsyncSession, alum: Alumni
) -> None:
    c1 = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    # Old code no longer works
    r = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=c1
    )
    assert r in (OtpResult.WRONG, OtpResult.NO_ACTIVE_OTP)
```

- [ ] **Step 2: Run test (expect failure on import)**

```bash
uv run pytest tests/integration/test_otp_lifecycle.py -v
```

Expected: FAIL with `ImportError: cannot import name 'issue_otp' from 'src.shared.otp'`.

- [ ] **Step 3: Extend `src/shared/otp.py`**

Append to the existing `src/shared/otp.py`:

```python
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import OtpCode

OTP_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 3


class OtpResult(str, Enum):
    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    NO_ACTIVE_OTP = "no_active_otp"


async def issue_otp(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    alumni_id: str,
) -> str:
    """Generate a new OTP. Invalidates any prior active OTP for this tg user."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(OtpCode)
        .where(
            OtpCode.telegram_user_id == telegram_user_id,
            OtpCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    code = generate_code()
    session.add(
        OtpCode(
            telegram_user_id=telegram_user_id,
            alumni_id=alumni_id,
            code_hash=hash_code(code),
            expires_at=now + OTP_TTL,
        )
    )
    return code


async def verify_otp_submission(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    alumni_id: str,
    submitted: str,
) -> OtpResult:
    now = datetime.now(timezone.utc)
    row = (
        await session.execute(
            select(OtpCode)
            .where(
                OtpCode.telegram_user_id == telegram_user_id,
                OtpCode.alumni_id == alumni_id,
                OtpCode.consumed_at.is_(None),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return OtpResult.NO_ACTIVE_OTP
    if row.expires_at <= now:
        row.consumed_at = now
        return OtpResult.EXPIRED
    if row.attempts >= MAX_ATTEMPTS:
        row.consumed_at = now
        return OtpResult.EXHAUSTED

    if verify_code(submitted, row.code_hash):
        row.consumed_at = now
        return OtpResult.OK

    row.attempts += 1
    if row.attempts >= MAX_ATTEMPTS:
        row.consumed_at = now
        return OtpResult.EXHAUSTED
    return OtpResult.WRONG
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/integration/test_otp_lifecycle.py -v
```

Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/otp.py tests/integration/test_otp_lifecycle.py
git commit -m "feat(shared): OTP issue + verify lifecycle with single-use, expiry, attempt cap"
```

---

## Phase F — Verification core

### Task 15: `src/shared/display_name.py` — canonical display name + collision suffix

**Files:**
- Create: `src/shared/display_name.py`
- Test: `tests/unit/test_display_name.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_display_name.py`:

```python
from src.shared.display_name import (
    canonical_display_name,
    mask_email,
    suffix_for_collision,
)


def test_canonical_display_name_basic() -> None:
    assert canonical_display_name("Suresh Iyer", "PGP", 2015) == "Suresh Iyer (PGP 2015)"


def test_canonical_display_name_missing_program_or_batch() -> None:
    assert canonical_display_name("Alone", None, None) == "Alone"
    assert canonical_display_name("Just Program", "LDP", None) == "Just Program (LDP)"
    assert canonical_display_name("Just Batch", None, 2020) == "Just Batch (2020)"


def test_canonical_strips_whitespace() -> None:
    assert canonical_display_name("  Spaced  ", "PGP", 2010) == "Spaced (PGP 2010)"


def test_suffix_for_collision_letters() -> None:
    assert suffix_for_collision(0) == "A"
    assert suffix_for_collision(1) == "B"
    assert suffix_for_collision(25) == "Z"


def test_suffix_for_collision_out_of_range() -> None:
    import pytest

    with pytest.raises(ValueError):
        suffix_for_collision(26)


def test_mask_email_normal() -> None:
    assert mask_email("suresh@gmail.com") == "s••••@gmail.com"


def test_mask_email_single_char_local() -> None:
    assert mask_email("a@x.io") == "a••••@x.io"


def test_mask_email_no_at() -> None:
    assert mask_email("notanemail") == "••••"
```

- [ ] **Step 2: Run test (expect failure)**

```bash
uv run pytest tests/unit/test_display_name.py -v
```

Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/shared/display_name.py`**

```python
def canonical_display_name(name: str, program: str | None, batch: int | None) -> str:
    """Build the canonical display string: 'Name (Program Year)'."""
    base = name.strip()
    parts: list[str] = []
    if program:
        parts.append(program.strip())
    if batch:
        parts.append(str(batch))
    if not parts:
        return base
    return f"{base} ({' '.join(parts)})"


def suffix_for_collision(index: int) -> str:
    """0 -> 'A', 1 -> 'B', ..., 25 -> 'Z'. ValueError beyond 25."""
    if not 0 <= index <= 25:
        raise ValueError(f"collision suffix index out of range: {index}")
    return chr(ord("A") + index)


def mask_email(email: str) -> str:
    """Mask an email for safe display: 'suresh@gmail.com' -> 's••••@gmail.com'."""
    if "@" not in email:
        return "••••"
    local, _, domain = email.partition("@")
    if not local:
        return f"••••@{domain}"
    return f"{local[0]}••••@{domain}"
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_display_name.py -v
```

Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/display_name.py tests/unit/test_display_name.py
git commit -m "feat(shared): canonical display name, collision suffix, email masker"
```

---

### Task 16: `src/shared/verification.py` — claim_and_bind transaction

**Files:**
- Create: `src/shared/verification.py`
- Test: `tests/integration/test_verification.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_verification.py`:

```python
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import Alumni, Member, VerificationCase
from src.shared.verification import (
    AlreadyBoundError,
    AlumniAlreadyClaimedError,
    bind_member,
    lookup_alumni_by_reg,
)


@pytest.fixture
async def alum(session: AsyncSession) -> Alumni:
    a = Alumni(
        user_id="va1",
        name="Verify One",
        email="v1@example.com",
        program="PGP",
        batch_year=2014,
        reg_number="PGP/2014/0001",
    )
    session.add(a)
    await session.flush()
    return a


@pytest.mark.asyncio
async def test_lookup_alumni_by_reg_exact(session: AsyncSession, alum: Alumni) -> None:
    found = await lookup_alumni_by_reg(session, "PGP/2014/0001")
    assert found is not None
    assert found.user_id == "va1"


@pytest.mark.asyncio
async def test_lookup_alumni_by_reg_case_insensitive(
    session: AsyncSession, alum: Alumni
) -> None:
    found = await lookup_alumni_by_reg(session, "pgp/2014/0001")
    assert found is not None
    assert found.user_id == "va1"


@pytest.mark.asyncio
async def test_lookup_alumni_by_reg_not_found(session: AsyncSession) -> None:
    assert await lookup_alumni_by_reg(session, "NOPE/0000/9999") is None


@pytest.mark.asyncio
async def test_bind_member_happy_path(session: AsyncSession, alum: Alumni) -> None:
    case = VerificationCase(
        telegram_user_id=999,
        method="email_otp",
        claimed_alumni_id=alum.user_id,
        status="auto_approved",
    )
    session.add(case)
    await session.flush()

    member = await bind_member(
        session,
        alumni_id=alum.user_id,
        telegram_user_id=999,
        display_name="Verify One (PGP 2014)",
        verified_via="email_otp",
        verification_case_id=case.id,
    )
    await session.flush()
    assert member.id is not None
    assert member.status == "active"


@pytest.mark.asyncio
async def test_bind_member_double_claim_raises(
    session: AsyncSession, alum: Alumni
) -> None:
    await bind_member(
        session,
        alumni_id=alum.user_id,
        telegram_user_id=111,
        display_name="Verify One (PGP 2014)",
        verified_via="email_otp",
        verification_case_id=None,
    )
    await session.flush()
    with pytest.raises(AlumniAlreadyClaimedError):
        await bind_member(
            session,
            alumni_id=alum.user_id,
            telegram_user_id=222,
            display_name="Verify One (PGP 2014)",
            verified_via="email_otp",
            verification_case_id=None,
        )


@pytest.mark.asyncio
async def test_bind_member_tg_already_bound_raises(
    session: AsyncSession, alum: Alumni
) -> None:
    other = Alumni(user_id="va2", name="Other", program="PGP", batch_year=2014)
    session.add(other)
    await session.flush()

    await bind_member(
        session,
        alumni_id=alum.user_id,
        telegram_user_id=111,
        display_name="X",
        verified_via="email_otp",
        verification_case_id=None,
    )
    await session.flush()
    with pytest.raises(AlreadyBoundError):
        await bind_member(
            session,
            alumni_id="va2",
            telegram_user_id=111,  # same telegram user
            display_name="Y",
            verified_via="email_otp",
            verification_case_id=None,
        )
```

- [ ] **Step 2: Run test (expect import failure)**

```bash
uv run pytest tests/integration/test_verification.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/shared/verification.py`**

```python
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.audit import write_audit
from src.shared.models import Alumni, Member


class VerificationError(Exception):
    pass


class AlumniAlreadyClaimedError(VerificationError):
    pass


class AlreadyBoundError(VerificationError):
    pass


async def lookup_alumni_by_reg(
    session: AsyncSession, reg_number: str
) -> Alumni | None:
    """Case-insensitive exact match on reg_number."""
    stmt = select(Alumni).where(Alumni.reg_number.ilike(reg_number))
    return (await session.execute(stmt)).scalar_one_or_none()


async def bind_member(
    session: AsyncSession,
    *,
    alumni_id: str,
    telegram_user_id: int,
    display_name: str,
    verified_via: str,
    verification_case_id: int | None,
) -> Member:
    """
    Atomically claim an alumni record and bind it to a telegram user.

    Relies on partial UNIQUE indexes (status='active') for both alumni_id and
    telegram_user_id. A SAVEPOINT is used so we can distinguish the two unique
    constraints by inspecting the IntegrityError.
    """
    # SELECT ... FOR UPDATE on the alumni row to serialize concurrent claims
    await session.execute(
        select(Alumni).where(Alumni.user_id == alumni_id).with_for_update()
    )

    member = Member(
        alumni_id=alumni_id,
        telegram_user_id=telegram_user_id,
        display_name=display_name,
        status="active",
        verified_via=verified_via,
        verification_case_id=verification_case_id,
    )
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        msg = str(exc.orig).lower() if exc.orig else ""
        await session.rollback()
        if "members_one_active_per_tg" in msg:
            raise AlreadyBoundError(
                f"telegram_user_id {telegram_user_id} already bound"
            ) from exc
        if "members_one_active_per_alumni" in msg:
            raise AlumniAlreadyClaimedError(
                f"alumni_id {alumni_id} already claimed"
            ) from exc
        raise

    await write_audit(
        session,
        actor_email="system@bot",
        action="member_created",
        subject_type="member",
        subject_id=str(member.id),
        details={
            "alumni_id": alumni_id,
            "telegram_user_id": telegram_user_id,
            "verified_via": verified_via,
            "verification_case_id": verification_case_id,
        },
    )
    return member
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/integration/test_verification.py -v
```

Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/shared/verification.py tests/integration/test_verification.py
git commit -m "feat(shared): claim_and_bind transaction with uniqueness enforcement"
```

---

## Phase G — Telegram bot (Email OTP path)

### Task 17: Bot entrypoint with `/start` command + method choice keyboard

**Files:**
- Create: `src/bot/__main__.py`
- Create: `src/bot/handlers/start.py`
- Test: `tests/e2e/test_start_handler.py`

- [ ] **Step 1: Write the failing test**

`tests/e2e/test_start_handler.py`:

```python
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from src.bot.handlers.start import register as register_start


@pytest.mark.asyncio
async def test_start_command_replies_with_method_choice() -> None:
    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = Dispatcher()
    register_start(dp)

    msg = Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alum"},
            "text": "/start",
        }
    )
    update = Update.model_validate(
        {"update_id": 1, "message": msg.model_dump(mode="json")}
    )
    await dp.feed_update(bot, update)

    bot.send_message.assert_awaited_once()
    sent = bot.send_message.await_args.kwargs
    assert sent["chat_id"] == 42
    assert "verify" in sent["text"].lower()
    # the inline keyboard should advertise both methods
    keyboard = sent["reply_markup"].inline_keyboard
    button_texts = [b.text.lower() for row in keyboard for b in row]
    assert any("email" in t for t in button_texts)
    assert any("linkedin" in t for t in button_texts)
```

- [ ] **Step 2: Run test (expect failure)**

```bash
uv run pytest tests/e2e/test_start_handler.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/bot/handlers/start.py`**

```python
from aiogram import Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


def _method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📧 Verify with Email OTP", callback_data="m:email"),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Verify with LinkedIn (coming soon)",
                    callback_data="m:linkedin",
                ),
            ],
        ]
    )


async def handle_start(message: Message) -> None:
    text = (
        "👋 Welcome to the IIM C Alumni verification bot.\n\n"
        "To join the alumni Telegram group, you'll need to verify that you're "
        "in the official directory. Choose how you'd like to verify:"
    )
    await message.answer(text, reply_markup=_method_kb())


async def handle_linkedin_choice(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "LinkedIn verification isn't available yet. Please use Email OTP for now."
        )


def register(dp: Dispatcher) -> None:
    dp.message.register(handle_start, CommandStart())
    dp.callback_query.register(handle_linkedin_choice, F.data == "m:linkedin")
```

- [ ] **Step 4: Create `src/bot/__main__.py`**

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.bot.handlers import group_events, start, verify_email
from src.shared.config import get_settings


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    start.register(dp)
    verify_email.register(dp)
    group_events.register(dp)
    return dp


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Note: `verify_email` and `group_events` are referenced but not yet implemented — the next tasks add them. This commit will not run yet; we'll fix in Task 18.

- [ ] **Step 5: Run test for `start.py` only**

```bash
uv run pytest tests/e2e/test_start_handler.py -v
```

Expected: PASS (1 passed). (`__main__.py` is only exercised at runtime, not tested here.)

- [ ] **Step 6: Commit**

```bash
git add src/bot/__main__.py src/bot/handlers/start.py tests/e2e/test_start_handler.py
git commit -m "feat(bot): /start handler with method-choice inline keyboard"
```

---

### Task 18: Email OTP FSM — ask Reg# → lookup → send OTP

**Files:**
- Create: `src/bot/handlers/verify_email.py`
- Test: `tests/e2e/test_verify_email_part1.py`

- [ ] **Step 1: Write the failing test**

`tests/e2e/test_verify_email_part1.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    Update,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.shared.models import Alumni, OtpCode


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    return dp


def _make_callback(data: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "chat_instance": "ci",
                "data": data,
                "message": {
                    "message_id": 100,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "...",
                },
            },
        }
    )


def _make_text(text: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 101,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "text": text,
            },
        }
    )


@pytest.mark.asyncio
async def test_email_choice_asks_for_reg_number() -> None:
    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    bot.send_message.assert_awaited()
    last = bot.send_message.await_args_list[-1].kwargs
    assert "reg" in last["text"].lower() or "registration" in last["text"].lower()


@pytest.mark.asyncio
async def test_reg_number_lookup_match_sends_otp(session: AsyncSession) -> None:
    a = Alumni(
        user_id="bot1",
        name="Bot Alum",
        email="bot1@example.com",
        program="PGP",
        batch_year=2015,
        reg_number="PGP/2015/0001",
    )
    session.add(a)
    await session.flush()
    await session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    bot.send_message.reset_mock()

    # Patch the email sender to assert it was called
    with patch("src.bot.handlers.verify_email.send_otp_email", new=AsyncMock()) as send:
        await dp.feed_update(bot, _make_text("PGP/2015/0001"))

    # Bot should reply with masked-email confirmation
    sent_messages = " ".join(
        c.kwargs.get("text", "") for c in bot.send_message.await_args_list
    )
    assert "b••••@example.com" in sent_messages
    send.assert_awaited_once()
    assert send.await_args.kwargs["to"] == "bot1@example.com"
```

(This test relies on the `session` fixture committing to a shared DB; we adjust `session` fixture in step 2.)

- [ ] **Step 2: Update `tests/conftest.py` to provide a committable session for e2e tests**

Replace the `session` fixture in `tests/conftest.py` with the version below, which adds a separate fixture that **commits** (for e2e tests that need data to survive across handler invocations):

```python
@pytest_asyncio.fixture
async def session(_migrations: None) -> AsyncIterator[AsyncSession]:
    """Per-test transaction that rolls back at teardown."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def committed_session(_migrations: None) -> AsyncIterator[AsyncSession]:
    """A session that commits. Used for e2e tests where handlers need to see data
    written before the handler runs. Cleans up by TRUNCATEing all tables at teardown."""
    from sqlalchemy import text

    engine = create_async_engine(os.environ["DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        try:
            yield s
        finally:
            # Wipe all data so the next test starts clean
            await s.execute(
                text(
                    "TRUNCATE TABLE invite_links, audit_log, members, "
                    "otp_codes, verification_cases, alumni RESTART IDENTITY CASCADE"
                )
            )
            await s.commit()
    await engine.dispose()
```

Then update the failing test in `tests/e2e/test_verify_email_part1.py` to use `committed_session` instead of `session`. Find:

```python
async def test_reg_number_lookup_match_sends_otp(session: AsyncSession) -> None:
```

and change to:

```python
async def test_reg_number_lookup_match_sends_otp(committed_session: AsyncSession) -> None:
```

then change `session.add(a)` / `session.flush()` / `session.commit()` to use `committed_session` instead.

- [ ] **Step 3: Run test to confirm failure**

```bash
uv run pytest tests/e2e/test_verify_email_part1.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.bot.handlers.verify_email'`.

- [ ] **Step 4: Implement `src/bot/handlers/verify_email.py` (partial — Reg# lookup + OTP send)**

```python
from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.shared.db import session_scope
from src.shared.display_name import mask_email
from src.shared.email import send_otp_email
from src.shared.otp import issue_otp
from src.shared.verification import lookup_alumni_by_reg


class EmailVerify(StatesGroup):
    waiting_reg_number = State()
    waiting_otp_code = State()
    waiting_display_name = State()


async def handle_method_email(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(EmailVerify.waiting_reg_number)
    await callback.message.answer(
        "Please reply with your IIM C registration number "
        "(e.g. PGP/2015/0123 or PGDM/2010/0456)."
    )


async def handle_reg_number(message: Message, state: FSMContext) -> None:
    if not message.text or not message.from_user:
        return
    reg = message.text.strip()
    async with session_scope() as s:
        alum = await lookup_alumni_by_reg(s, reg)
        if alum is None:
            await message.answer(
                "We couldn't find that registration number in the directory. "
                "Please double-check and try again, or contact an admin if you "
                "believe this is wrong."
            )
            return
        if not alum.email:
            await message.answer(
                "We found a record but it has no email on file. Please contact "
                "an admin to verify manually."
            )
            await state.clear()
            return

        code = await issue_otp(
            s,
            telegram_user_id=message.from_user.id,
            alumni_id=alum.user_id,
        )

    await send_otp_email(to=alum.email, code=code)
    await state.update_data(alumni_id=alum.user_id, alum_email=alum.email)
    await state.set_state(EmailVerify.waiting_otp_code)
    await message.answer(
        f"A 6-digit code has been sent to {mask_email(alum.email)}.\n"
        f"It expires in 10 minutes. Reply with the code to continue."
    )


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_email, F.data == "m:email")
    dp.message.register(handle_reg_number, EmailVerify.waiting_reg_number)
```

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/e2e/test_verify_email_part1.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/bot/handlers/verify_email.py tests/e2e/test_verify_email_part1.py tests/conftest.py
git commit -m "feat(bot): Email OTP FSM (part 1) — reg# lookup, OTP issued, masked-email confirm"
```

---

### Task 19: Email OTP FSM — verify code → ask display name → claim & bind → DM invite link

**Files:**
- Modify: `src/bot/handlers/verify_email.py`
- Test: `tests/e2e/test_verify_email_part2.py`

- [ ] **Step 1: Write the failing test**

`tests/e2e/test_verify_email_part2.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.shared.models import Alumni, Member


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    return dp


def _make_callback(data: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "chat_instance": "ci",
                "data": data,
                "message": {
                    "message_id": 100,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "...",
                },
            },
        }
    )


def _make_text(text: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 101,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "text": text,
            },
        }
    )


@pytest.mark.asyncio
async def test_full_happy_path_creates_member(
    committed_session: AsyncSession,
) -> None:
    a = Alumni(
        user_id="hp1",
        name="Happy Path",
        email="hp1@example.com",
        program="PGP",
        batch_year=2017,
        reg_number="PGP/2017/0042",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    # Simulate the Telegram invite-link API
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("X", (), {"invite_link": "https://t.me/+abc"})()
    )

    captured_code: dict[str, str] = {}

    async def fake_send_otp_email(*, to: str, code: str) -> None:
        captured_code["code"] = code

    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    with patch(
        "src.bot.handlers.verify_email.send_otp_email", new=fake_send_otp_email
    ):
        await dp.feed_update(bot, _make_text("PGP/2017/0042"))

    assert captured_code["code"], "OTP send was not called"

    # Submit the correct code
    await dp.feed_update(bot, _make_text(captured_code["code"]))
    # Accept the default display name
    await dp.feed_update(bot, _make_text("ok"))

    # A member row should now exist
    members = (await committed_session.execute(select(Member))).scalars().all()
    assert len(members) == 1
    m = members[0]
    assert m.alumni_id == "hp1"
    assert m.telegram_user_id == 42
    assert m.display_name == "Happy Path (PGP 2017)"
    assert m.status == "active"

    # Telegram invite-link API should have been called
    bot.create_chat_invite_link.assert_awaited_once()
    # Last DM should contain the invite link
    final_text = " ".join(
        c.kwargs.get("text", "") for c in bot.send_message.await_args_list
    )
    assert "https://t.me/+abc" in final_text


@pytest.mark.asyncio
async def test_wrong_code_then_correct(committed_session: AsyncSession) -> None:
    a = Alumni(
        user_id="wc1",
        name="Wrong Code",
        email="wc1@example.com",
        program="PGP",
        batch_year=2018,
        reg_number="PGP/2018/0011",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("X", (), {"invite_link": "https://t.me/+xyz"})()
    )
    captured: dict[str, str] = {}

    async def fake_send(*, to: str, code: str) -> None:
        captured["code"] = code

    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    with patch("src.bot.handlers.verify_email.send_otp_email", new=fake_send):
        await dp.feed_update(bot, _make_text("PGP/2018/0011"))
    await dp.feed_update(bot, _make_text("000000"))  # wrong
    await dp.feed_update(bot, _make_text(captured["code"]))  # correct
    await dp.feed_update(bot, _make_text("ok"))

    members = (await committed_session.execute(select(Member))).scalars().all()
    assert len(members) == 1
```

- [ ] **Step 2: Run test to confirm failure**

```bash
uv run pytest tests/e2e/test_verify_email_part2.py -v
```

Expected: FAIL (handlers for OTP submission and display-name acceptance don't exist yet).

- [ ] **Step 3: Replace `src/bot/handlers/verify_email.py` with the full version**

Overwrite the file (do not append — this is the canonical version with all four handlers):

```python
from datetime import datetime, timedelta, timezone

from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.display_name import canonical_display_name, mask_email
from src.shared.email import send_otp_email
from src.shared.models import Alumni, InviteLink, VerificationCase
from src.shared.otp import OtpResult, issue_otp, verify_otp_submission
from src.shared.verification import (
    AlreadyBoundError,
    AlumniAlreadyClaimedError,
    bind_member,
    lookup_alumni_by_reg,
)


class EmailVerify(StatesGroup):
    waiting_reg_number = State()
    waiting_otp_code = State()
    waiting_display_name = State()


async def handle_method_email(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(EmailVerify.waiting_reg_number)
    await callback.message.answer(
        "Please reply with your IIM C registration number "
        "(e.g. PGP/2015/0123 or PGDM/2010/0456)."
    )


async def handle_reg_number(message: Message, state: FSMContext) -> None:
    if not message.text or not message.from_user:
        return
    reg = message.text.strip()
    async with session_scope() as s:
        alum = await lookup_alumni_by_reg(s, reg)
        if alum is None:
            await message.answer(
                "We couldn't find that registration number in the directory. "
                "Please double-check and try again, or contact an admin if you "
                "believe this is wrong."
            )
            return
        if not alum.email:
            await message.answer(
                "We found a record but it has no email on file. Please contact "
                "an admin to verify manually."
            )
            await state.clear()
            return

        code = await issue_otp(
            s,
            telegram_user_id=message.from_user.id,
            alumni_id=alum.user_id,
        )

    await send_otp_email(to=alum.email, code=code)
    await state.update_data(alumni_id=alum.user_id, alum_email=alum.email)
    await state.set_state(EmailVerify.waiting_otp_code)
    await message.answer(
        f"A 6-digit code has been sent to {mask_email(alum.email)}.\n"
        f"It expires in 10 minutes. Reply with the code to continue."
    )


async def handle_otp_code(message: Message, state: FSMContext) -> None:
    if not message.text or not message.from_user:
        return
    submitted = message.text.strip()
    data = await state.get_data()
    alumni_id: str | None = data.get("alumni_id")
    if alumni_id is None:
        await message.answer("Session expired. Please /start over.")
        await state.clear()
        return

    async with session_scope() as s:
        result = await verify_otp_submission(
            s,
            telegram_user_id=message.from_user.id,
            alumni_id=alumni_id,
            submitted=submitted,
        )

    if result == OtpResult.WRONG:
        await message.answer("That code didn't match. Try again.")
        return
    if result == OtpResult.NO_ACTIVE_OTP:
        await message.answer(
            "No active code found. Please /start over to request a new one."
        )
        await state.clear()
        return
    if result == OtpResult.EXPIRED:
        await message.answer(
            "That code has expired. Please /start over to request a new one."
        )
        await state.clear()
        return
    if result == OtpResult.EXHAUSTED:
        await message.answer(
            "Too many incorrect attempts. Please /start over after a few minutes, "
            "or contact an admin."
        )
        await state.clear()
        return

    async with session_scope() as s:
        alum = await s.get(Alumni, alumni_id)
        if alum is None:
            await message.answer("Internal error. Please /start over.")
            await state.clear()
            return
        default_name = canonical_display_name(alum.name, alum.program, alum.batch_year)

    await state.update_data(default_display_name=default_name)
    await state.set_state(EmailVerify.waiting_display_name)
    await message.answer(
        f"✅ Verified.\n\nYour display name in the group will be:\n\n"
        f"  <b>{default_name}</b>\n\n"
        f"Reply 'ok' to accept, or send a different display name.",
        parse_mode="HTML",
    )


async def handle_display_name(message: Message, state: FSMContext) -> None:
    if not message.text or not message.from_user:
        return
    data = await state.get_data()
    alumni_id: str | None = data.get("alumni_id")
    default: str | None = data.get("default_display_name")
    if alumni_id is None or default is None:
        await message.answer("Session expired. Please /start over.")
        await state.clear()
        return

    chosen = (
        default
        if message.text.strip().lower() in {"ok", "yes", "y"}
        else message.text.strip()
    )
    chosen = chosen[:64]

    async with session_scope() as s:
        case = VerificationCase(
            telegram_user_id=message.from_user.id,
            method="email_otp",
            claimed_alumni_id=alumni_id,
            status="auto_approved",
        )
        s.add(case)
        await s.flush()
        try:
            await bind_member(
                s,
                alumni_id=alumni_id,
                telegram_user_id=message.from_user.id,
                display_name=chosen,
                verified_via="email_otp",
                verification_case_id=case.id,
            )
        except AlumniAlreadyClaimedError:
            await message.answer(
                "This alumni record has already been claimed by another Telegram "
                "account. If this is a mistake, please contact an admin."
            )
            await state.clear()
            return
        except AlreadyBoundError:
            await message.answer(
                "Your Telegram account is already bound to another verified alum. "
                "If this is a mistake, please contact an admin."
            )
            await state.clear()
            return

    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    invite = await message.bot.create_chat_invite_link(  # type: ignore[union-attr]
        chat_id=settings.telegram_group_chat_id,
        expire_date=expires,
        member_limit=1,
        name=f"verify-{message.from_user.id}",
    )

    async with session_scope() as s:
        s.add(
            InviteLink(
                telegram_user_id=message.from_user.id,
                alumni_id=alumni_id,
                invite_link=invite.invite_link,
                expires_at=expires,
            )
        )

    await message.answer(
        f"🎉 You're verified! Here is your one-time invite link "
        f"(valid for 24 hours, single use):\n\n{invite.invite_link}"
    )
    await state.clear()


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_email, F.data == "m:email")
    dp.message.register(handle_reg_number, EmailVerify.waiting_reg_number)
    dp.message.register(handle_otp_code, EmailVerify.waiting_otp_code)
    dp.message.register(handle_display_name, EmailVerify.waiting_display_name)
```

- [ ] **Step 4: Run all verify_email tests**

```bash
uv run pytest tests/e2e/test_verify_email_part1.py tests/e2e/test_verify_email_part2.py -v
```

Expected: PASS (4 passed total).

- [ ] **Step 5: Commit**

```bash
git add src/bot/handlers/verify_email.py tests/e2e/test_verify_email_part2.py
git commit -m "feat(bot): Email OTP FSM complete — verify code, display name, claim & DM invite"
```

---

### Task 20: Group-event handler — kick unbound joiners, welcome bound ones

**Files:**
- Create: `src/bot/handlers/group_events.py`
- Test: `tests/e2e/test_group_events.py`

- [ ] **Step 1: Write the failing test**

`tests/e2e/test_group_events.py`:

```python
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.group_events import register as register_group
from src.shared.models import Alumni, Member


def _dp() -> Dispatcher:
    dp = Dispatcher()
    register_group(dp)
    return dp


def _chat_member_joined(user_id: int, chat_id: int) -> Update:
    return Update.model_validate(
        {
            "update_id": 99,
            "chat_member": {
                "chat": {"id": chat_id, "type": "supergroup", "title": "G"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                "date": 0,
                "old_chat_member": {
                    "user": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                    "status": "left",
                },
                "new_chat_member": {
                    "user": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                    "status": "member",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_unbound_joiner_is_kicked(committed_session: AsyncSession) -> None:
    from src.shared.config import get_settings

    chat_id = get_settings().telegram_group_chat_id

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()

    await dp.feed_update(bot, _chat_member_joined(user_id=777, chat_id=chat_id))

    bot.ban_chat_member.assert_awaited_once()
    bot.unban_chat_member.assert_awaited_once()
    # And a DM should be attempted (may swallow if user has DMs off)
    bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_bound_joiner_gets_welcome(committed_session: AsyncSession) -> None:
    from src.shared.config import get_settings

    chat_id = get_settings().telegram_group_chat_id

    a = Alumni(user_id="g1", name="Greeted", program="PGP", batch_year=2019)
    committed_session.add(a)
    m = Member(
        alumni_id="g1",
        telegram_user_id=888,
        display_name="Greeted (PGP 2019)",
        status="active",
        verified_via="email_otp",
    )
    committed_session.add(m)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()

    await dp.feed_update(bot, _chat_member_joined(user_id=888, chat_id=chat_id))

    bot.ban_chat_member.assert_not_awaited()
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "Greeted (PGP 2019)" in sent
```

- [ ] **Step 2: Run test (expect failure)**

```bash
uv run pytest tests/e2e/test_group_events.py -v
```

Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/bot/handlers/group_events.py`**

```python
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ChatMemberUpdated
from sqlalchemy import select

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.models import Member


async def _is_active_member(telegram_user_id: int) -> Member | None:
    async with session_scope() as s:
        stmt = select(Member).where(
            Member.telegram_user_id == telegram_user_id,
            Member.status == "active",
        )
        return (await s.execute(stmt)).scalar_one_or_none()


async def handle_chat_member(event: ChatMemberUpdated, bot: Bot) -> None:
    settings = get_settings()
    if event.chat.id != settings.telegram_group_chat_id:
        return
    if event.new_chat_member.status not in {"member", "restricted"}:
        return
    if event.old_chat_member.status in {"member", "restricted", "administrator"}:
        return  # already a member; this is a status change, not a fresh join

    tg_id = event.new_chat_member.user.id
    member = await _is_active_member(tg_id)

    if member is None:
        # Kick (ban + unban so they can retry after verifying)
        try:
            await bot.ban_chat_member(chat_id=event.chat.id, user_id=tg_id)
        finally:
            await bot.unban_chat_member(chat_id=event.chat.id, user_id=tg_id)
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=(
                    "You tried to join the IIM C alumni group but you're not "
                    "verified yet. Please DM @IIMCAlumBot and run /start first."
                ),
            )
        except TelegramForbiddenError:
            pass  # user has DMs closed; nothing we can do
        return

    # Bound and active — welcome.
    await bot.send_message(
        chat_id=event.chat.id,
        text=f"👋 Welcome <b>{member.display_name}</b>!",
        parse_mode="HTML",
    )


def register(dp: Dispatcher) -> None:
    dp.chat_member.register(handle_chat_member)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/e2e/test_group_events.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bot/handlers/group_events.py tests/e2e/test_group_events.py
git commit -m "feat(bot): chat_member handler — kick unbound, welcome bound members"
```

---

## Phase H — End-to-end happy path

### Task 21: Full email-OTP happy path E2E + final cleanup

**Files:**
- Create: `tests/e2e/test_email_otp_happy_path.py`

This task wires the full flow as one test that mirrors what a real alum will experience. It mostly duplicates Task 19's tests, but tied together as the single "shippable v1 works" assertion. Worth keeping separate so this one test is the canonical "is the MVP working" smoke.

- [ ] **Step 1: Write the test**

`tests/e2e/test_email_otp_happy_path.py`:

```python
"""The single-test definition of 'v1 works': from /start to invite link DM."""
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.group_events import register as register_group
from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.shared.models import Alumni, AuditLog, InviteLink, Member


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    register_group(dp)
    return dp


def _send_start(user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "text": "/start",
            },
        }
    )


def _click_email(user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "chat_instance": "ci",
                "data": "m:email",
                "message": {
                    "message_id": 2,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "...",
                },
            },
        }
    )


def _send_text(text: str, msg_id: int, user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": msg_id,
            "message": {
                "message_id": msg_id,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "text": text,
            },
        }
    )


@pytest.mark.asyncio
async def test_v1_email_otp_full_happy_path(
    committed_session: AsyncSession,
) -> None:
    # GIVEN an alum is in the directory
    a = Alumni(
        user_id="herov1",
        name="Hero V1",
        email="hero@example.com",
        program="PGP",
        batch_year=2016,
        reg_number="PGP/2016/0007",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("L", (), {"invite_link": "https://t.me/+herolink"})()
    )

    captured: dict[str, str] = {}

    async def fake_send(*, to: str, code: str) -> None:
        captured["code"] = code
        captured["to"] = to

    dp = _dp()

    # WHEN they walk the full flow
    await dp.feed_update(bot, _send_start())
    await dp.feed_update(bot, _click_email())
    with patch("src.bot.handlers.verify_email.send_otp_email", new=fake_send):
        await dp.feed_update(bot, _send_text("PGP/2016/0007", msg_id=3))
    await dp.feed_update(bot, _send_text(captured["code"], msg_id=4))
    await dp.feed_update(bot, _send_text("ok", msg_id=5))

    # THEN: OTP went to their real address
    assert captured["to"] == "hero@example.com"

    # THEN: a member row exists, bound and active
    member = (
        await committed_session.execute(
            select(Member).where(Member.telegram_user_id == 4242)
        )
    ).scalar_one()
    assert member.alumni_id == "herov1"
    assert member.status == "active"
    assert member.display_name == "Hero V1 (PGP 2016)"
    assert member.verified_via == "email_otp"

    # THEN: an invite link was generated and recorded
    invite = (
        await committed_session.execute(
            select(InviteLink).where(InviteLink.telegram_user_id == 4242)
        )
    ).scalar_one()
    assert invite.invite_link == "https://t.me/+herolink"

    # THEN: the user was DM'd the invite link
    dms = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "https://t.me/+herolink" in dms

    # THEN: audit_log captured member_created
    actions = [
        row.action
        for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "member_created" in actions
```

- [ ] **Step 2: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Run lint and type checks**

```bash
uv run ruff check src tests scripts
uv run mypy src
```

Expected: both pass with no findings.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_email_otp_happy_path.py
git commit -m "test(e2e): canonical v1 happy-path smoke (start -> reg# -> OTP -> invite link)"
```

---

## Acceptance check for Sub-Plan 1

After all 21 tasks above pass:

1. **`make test`** runs unit + integration + e2e and is green.
2. **`make migrate`** brings up Postgres schema cleanly from a fresh DB.
3. **`make seed`** loads the synthetic 51-row sample directory.
4. **`make dev`** starts the bot polling Telegram. With a real bot token and your own Telegram user added to the synthetic sample, you can walk through the full flow against a real Telegram group.
5. The repository contains zero `.xlsx` files in git history.
6. `ruff check` and `mypy --strict` are clean.

This sub-plan ships a working MVP: an alum can DM the bot and be verified end-to-end via email OTP, with a one-time invite link to the supergroup, name-claim uniqueness enforced at the DB level.

**Next sub-plan (not in scope here):** add the LinkedIn OIDC verification path as a co-equal alternative.
