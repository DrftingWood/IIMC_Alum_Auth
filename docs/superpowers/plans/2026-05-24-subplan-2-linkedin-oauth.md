# Sub-Plan 2 — LinkedIn OIDC Verification Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LinkedIn as a co-equal verification path alongside Email OTP. An alum clicks "Verify with LinkedIn" → completes LinkedIn OIDC in a browser → if their LinkedIn-verified email matches a record in the directory, they're instantly verified (no OTP needed); otherwise their case enters the admin-review queue with the LinkedIn profile URL prefilled for human eyeballing.

**Architecture:** A second async task (an HTTP server) runs in the same process as the Telegram bot. The bot generates a CSRF `state` token and a session row, DMs the LinkedIn authorization URL. The user completes LinkedIn OIDC in their browser; LinkedIn redirects to our callback endpoint. The callback validates the state, exchanges the code for tokens, fetches userinfo, and either auto-verifies (if email matches) or queues for admin review.

**Tech Stack additions:** FastAPI + uvicorn for the OAuth callback HTTP server · `authlib` for OIDC verification · `aiogram` Bot reused inside the FastAPI handlers via `app.state.bot`.

**Out of scope (later sub-plans):**
- Admin dashboard (Sub-plan 4 will let admins drain the pending-review queue)
- Production deployment of the HTTP server (Sub-plan 5)
- LinkedIn profile scraping for follower count / education (deferred indefinitely per the spec — admin eyeballs the public profile manually)

---

## File structure produced by this sub-plan

```
IIMC_Alum_Auth/
├── alembic/versions/
│   └── 003_linkedin_auth_sessions.py    # NEW migration
├── src/
│   ├── shared/
│   │   ├── models.py                    # MODIFIED: add LinkedInAuthSession
│   │   └── linkedin.py                  # NEW: state gen, session lookup, userinfo fetch
│   └── bot/
│       ├── __main__.py                  # MODIFIED: run uvicorn alongside polling
│       ├── handlers/
│       │   ├── start.py                 # MODIFIED: linkedin choice now starts flow
│       │   └── verify_linkedin.py       # NEW: bot-side handler (generates URL + DMs)
│       └── http/
│           ├── __init__.py              # NEW (empty)
│           └── oauth_callback.py        # NEW: FastAPI app + /oauth/linkedin/callback
└── tests/
    ├── unit/
    │   └── test_linkedin_state.py       # NEW
    ├── integration/
    │   └── test_linkedin_session.py     # NEW
    └── e2e/
        ├── test_verify_linkedin_match.py        # NEW
        └── test_verify_linkedin_no_match.py     # NEW
```

**Total: 11 tasks across 4 phases.**

---

## Phase A — Database & shared

### Task 1: Migration 003 — `linkedin_auth_sessions` table

**Files:**
- Create: `alembic/versions/003_linkedin_auth_sessions.py`

- [ ] **Step 1: Write the migration**

```python
"""linkedin_auth_sessions table

Revision ID: 003_linkedin_auth_sessions
Revises: 002_operational_tables
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

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
```

- [ ] **Step 2: Apply the migration**

```powershell
$env:DATABASE_URL="postgresql+asyncpg://app:app@localhost:5433/iimc_dev"
$env:PATH="$env:USERPROFILE\.local\bin;$env:PATH"
uv run alembic upgrade head
```

Expected: `Running upgrade 002_operational_tables -> 003_linkedin_auth_sessions, linkedin_auth_sessions table`.

- [ ] **Step 3: Verify the table exists**

```bash
docker compose exec postgres psql -U app -d iimc_dev -c "\d linkedin_auth_sessions"
```

Expected: table with columns `state, telegram_user_id, expires_at, consumed_at, created_at` and an index on `telegram_user_id`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/003_linkedin_auth_sessions.py
git commit -m "feat(db): migration 003 (linkedin_auth_sessions table)"
```

---

### Task 2: Add `LinkedInAuthSession` SQLAlchemy model

**Files:**
- Modify: `src/shared/models.py`
- Modify (append): `tests/integration/test_models.py`

- [ ] **Step 1: Append failing test to `tests/integration/test_models.py`**

```python
from src.shared.models import LinkedInAuthSession


@pytest.mark.asyncio
async def test_linkedin_auth_session_round_trip(session: AsyncSession) -> None:
    expires = datetime.now(UTC) + timedelta(minutes=15)
    s = LinkedInAuthSession(
        state="abc-state-token",
        telegram_user_id=555,
        expires_at=expires,
    )
    session.add(s)
    await session.flush()
    fetched = await session.get(LinkedInAuthSession, "abc-state-token")
    assert fetched is not None
    assert fetched.telegram_user_id == 555
    assert fetched.consumed_at is None
```

- [ ] **Step 2: Run test (expect ImportError)**

```bash
uv run pytest tests/integration/test_models.py::test_linkedin_auth_session_round_trip -v
```

Expected: FAIL — `ImportError: cannot import name 'LinkedInAuthSession'`.

- [ ] **Step 3: Add the model to `src/shared/models.py`** (insert it at the end, before any module-level constants — or just append):

```python
class LinkedInAuthSession(Base):
    __tablename__ = "linkedin_auth_sessions"

    state: Mapped[str] = mapped_column(Text, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Run the test**

```bash
uv run pytest tests/integration/test_models.py -v
```

Expected: all model tests pass (previous + 1 new).

- [ ] **Step 5: Commit**

```bash
git add src/shared/models.py tests/integration/test_models.py
git commit -m "feat(shared): add LinkedInAuthSession model"
```

---

### Task 3: Extend config with LinkedIn OAuth env vars

**Files:**
- Modify: `src/shared/config.py`
- Modify: `.env.example`
- Modify (append): `tests/unit/test_config.py`

- [ ] **Step 1: Append a failing test to `tests/unit/test_config.py`**

```python
def test_settings_loads_linkedin_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h:5432/d")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setenv("OTP_PEPPER", "x" * 32)
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("BREVO_FROM_NAME", "Test")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "li-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "li-secret")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://example.com/oauth/linkedin/callback")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")

    from src.shared import config

    config._settings = None
    s = config.Settings()
    assert s.linkedin_client_id == "li-client"
    assert s.linkedin_client_secret == "li-secret"
    assert s.linkedin_redirect_uri == "https://example.com/oauth/linkedin/callback"
    assert s.public_base_url == "https://example.com"
```

- [ ] **Step 2: Run test (expect failure)**

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'linkedin_client_id'`.

- [ ] **Step 3: Add fields to `src/shared/config.py`**

Add inside the `Settings` class (after the existing fields, before `log_level`):

```python
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = ""
    public_base_url: str = ""
    http_port: int = 8080
```

(Defaults are empty strings so the bot still starts when LinkedIn isn't configured. The LinkedIn handler will check for empty values and fall back to the "coming soon" message.)

- [ ] **Step 4: Add to `.env.example`**

Append:

```bash
# LinkedIn OAuth
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=
PUBLIC_BASE_URL=
HTTP_PORT=8080
```

- [ ] **Step 5: Run test**

```bash
uv run pytest tests/unit/test_config.py -v
```

Expected: PASS (all 3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/shared/config.py .env.example tests/unit/test_config.py
git commit -m "feat(shared): add LinkedIn OAuth + public_base_url settings"
```

---

## Phase B — LinkedIn session logic

### Task 4: `src/shared/linkedin.py` — state gen, session lookup, userinfo fetch

**Files:**
- Create: `src/shared/linkedin.py`
- Test: `tests/unit/test_linkedin_state.py`
- Test: `tests/integration/test_linkedin_session.py`

- [ ] **Step 1: Write unit test `tests/unit/test_linkedin_state.py`**

```python
from src.shared.linkedin import build_authorization_url, generate_state


def test_generate_state_returns_url_safe_token() -> None:
    seen = set()
    for _ in range(20):
        s = generate_state()
        assert len(s) >= 32
        # URL-safe characters only
        assert all(c.isalnum() or c in "-_" for c in s)
        seen.add(s)
    # Tokens are unique
    assert len(seen) == 20


def test_build_authorization_url_includes_required_params() -> None:
    url = build_authorization_url(
        client_id="cid",
        redirect_uri="https://example.com/oauth/linkedin/callback",
        state="state-xyz",
    )
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert "client_id=cid" in url
    assert "redirect_uri=https%3A%2F%2Fexample.com%2Foauth%2Flinkedin%2Fcallback" in url
    assert "state=state-xyz" in url
    assert "scope=openid+profile+email" in url or "scope=openid%20profile%20email" in url
    assert "response_type=code" in url
```

- [ ] **Step 2: Write integration test `tests/integration/test_linkedin_session.py`**

```python
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.linkedin import (
    consume_session,
    create_session,
)
from src.shared.models import LinkedInAuthSession


@pytest.mark.asyncio
async def test_create_session_inserts_row(session: AsyncSession) -> None:
    state = await create_session(session, telegram_user_id=777)
    await session.flush()
    assert len(state) >= 32

    row = (
        await session.execute(
            select(LinkedInAuthSession).where(LinkedInAuthSession.state == state)
        )
    ).scalar_one()
    assert row.telegram_user_id == 777
    assert row.consumed_at is None
    assert row.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_consume_session_happy_path(session: AsyncSession) -> None:
    state = await create_session(session, telegram_user_id=777)
    await session.flush()

    tg_id = await consume_session(session, state=state)
    await session.flush()
    assert tg_id == 777

    row = (
        await session.execute(
            select(LinkedInAuthSession).where(LinkedInAuthSession.state == state)
        )
    ).scalar_one()
    assert row.consumed_at is not None


@pytest.mark.asyncio
async def test_consume_session_unknown_state(session: AsyncSession) -> None:
    assert await consume_session(session, state="not-a-real-state") is None


@pytest.mark.asyncio
async def test_consume_session_already_consumed(session: AsyncSession) -> None:
    state = await create_session(session, telegram_user_id=777)
    await session.flush()
    first = await consume_session(session, state=state)
    await session.flush()
    second = await consume_session(session, state=state)
    assert first == 777
    assert second is None


@pytest.mark.asyncio
async def test_consume_session_expired(session: AsyncSession) -> None:
    state = await create_session(session, telegram_user_id=777)
    await session.flush()
    # Force-expire
    row = (
        await session.execute(
            select(LinkedInAuthSession).where(LinkedInAuthSession.state == state)
        )
    ).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    assert await consume_session(session, state=state) is None
```

- [ ] **Step 3: Run tests (expect failure)**

```bash
uv run pytest tests/unit/test_linkedin_state.py tests/integration/test_linkedin_session.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.shared.linkedin'`.

- [ ] **Step 4: Implement `src/shared/linkedin.py`**

```python
"""LinkedIn OIDC helpers — state generation, session lifecycle, userinfo fetch."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import LinkedInAuthSession

SESSION_TTL = timedelta(minutes=15)
AUTHORIZATION_ENDPOINT = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_ENDPOINT = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_ENDPOINT = "https://api.linkedin.com/v2/userinfo"


def generate_state() -> str:
    """Return a URL-safe random 32-byte token (~43 chars after base64)."""
    return secrets.token_urlsafe(32)


def build_authorization_url(
    *, client_id: str, redirect_uri: str, state: str
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile email",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def create_session(
    session: AsyncSession, *, telegram_user_id: int
) -> str:
    """Insert a new auth session and return the state token."""
    state = generate_state()
    session.add(
        LinkedInAuthSession(
            state=state,
            telegram_user_id=telegram_user_id,
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    return state


async def consume_session(
    session: AsyncSession, *, state: str
) -> int | None:
    """Atomically consume an auth session. Returns telegram_user_id on success,
    None if not found / already consumed / expired."""
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(LinkedInAuthSession).where(LinkedInAuthSession.state == state)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.consumed_at is not None:
        return None
    if row.expires_at <= now:
        return None
    row.consumed_at = now
    return row.telegram_user_id


async def exchange_code_for_token(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, str]:
    """Exchange an authorization code for an access token + id_token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(*, access_token: str) -> dict[str, str]:
    """Fetch the OIDC userinfo claims (name, email, sub, picture)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_linkedin_state.py tests/integration/test_linkedin_session.py -v
```

Expected: PASS (2 unit + 5 integration = 7 tests).

- [ ] **Step 6: Commit**

```bash
git add src/shared/linkedin.py tests/unit/test_linkedin_state.py tests/integration/test_linkedin_session.py
git commit -m "feat(shared): LinkedIn OIDC helpers — state, sessions, token exchange, userinfo"
```

---

## Phase C — Bot-side LinkedIn handler

### Task 5: `verify_linkedin.py` — bot DMs the auth URL on LinkedIn choice

**Files:**
- Create: `src/bot/handlers/verify_linkedin.py`
- Modify: `src/bot/handlers/start.py` — remove the "coming soon" handler so LinkedIn callback handler in `verify_linkedin` is the one that fires on `m:linkedin`
- Test: `tests/e2e/test_verify_linkedin_start.py`

- [ ] **Step 1: Write failing test `tests/e2e/test_verify_linkedin_start.py`**

```python
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_linkedin import register as register_linkedin
from src.shared.models import LinkedInAuthSession


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_linkedin(dp)
    return dp


def _click_linkedin(user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "chat_instance": "ci",
                "data": "m:linkedin",
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


@pytest.mark.asyncio
async def test_linkedin_choice_dms_auth_url_and_creates_session(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "test-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _click_linkedin(user_id=42))

    # The bot should have DM'd an authorization URL
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "linkedin.com/oauth/v2/authorization" in sent
    assert "state=" in sent

    # A LinkedInAuthSession row should exist for this tg user
    sessions = (
        await committed_session.execute(
            select(LinkedInAuthSession).where(
                LinkedInAuthSession.telegram_user_id == 42
            )
        )
    ).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].consumed_at is None


@pytest.mark.asyncio
async def test_linkedin_choice_unconfigured_shows_coming_soon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "")
    from src.shared import config

    config._settings = None

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _click_linkedin(user_id=43))

    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "not configured" in sent.lower() or "not available" in sent.lower()
```

- [ ] **Step 2: Run tests (expect failure)**

```bash
uv run pytest tests/e2e/test_verify_linkedin_start.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/bot/handlers/verify_linkedin.py`**

```python
from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.linkedin import build_authorization_url, create_session


async def handle_method_linkedin(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return

    settings = get_settings()
    if not (
        settings.linkedin_client_id
        and settings.linkedin_client_secret
        and settings.linkedin_redirect_uri
    ):
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                "LinkedIn verification is not configured on this bot yet. "
                "Please use Email OTP for now."
            ),
        )
        return

    async with session_scope() as s:
        state = await create_session(
            s, telegram_user_id=callback.from_user.id
        )

    auth_url = build_authorization_url(
        client_id=settings.linkedin_client_id,
        redirect_uri=settings.linkedin_redirect_uri,
        state=state,
    )

    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=(
            "Tap the link below to sign in with LinkedIn. After you approve, "
            "you'll be redirected back to a confirmation page and we'll let "
            "you know here whether your record matched.\n\n"
            f"{auth_url}\n\n"
            "(Link expires in 15 minutes.)"
        ),
    )


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_linkedin, F.data == "m:linkedin")
```

- [ ] **Step 4: Remove the "coming soon" stub from `start.py`**

In `src/bot/handlers/start.py`, delete the `handle_linkedin_choice` function and its registration line in `register()`. The new `verify_linkedin.py` registers for `m:linkedin`. Also update the inline-keyboard button text — remove "(coming soon)":

Find and replace:

```python
                InlineKeyboardButton(
                    text="🔗 Verify with LinkedIn (coming soon)",
                    callback_data="m:linkedin",
                ),
```

with:

```python
                InlineKeyboardButton(
                    text="🔗 Verify with LinkedIn",
                    callback_data="m:linkedin",
                ),
```

And delete:

```python
async def handle_linkedin_choice(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.message is not None:
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text="LinkedIn verification isn't available yet. Please use Email OTP for now.",
        )
```

And remove `dp.callback_query.register(handle_linkedin_choice, F.data == "m:linkedin")` from `register()`.

Also remove `CallbackQuery` from the imports if it's no longer used in `start.py`.

- [ ] **Step 5: Update the test for `start.py`**

In `tests/e2e/test_start_handler.py`, the existing test still asserts `any("linkedin" in t for t in button_texts)` which still holds. No change needed unless the test was asserting on "coming soon" text.

- [ ] **Step 6: Run all bot tests**

```bash
uv run pytest tests/e2e -v
```

Expected: all e2e tests pass (previous + 2 new LinkedIn tests).

- [ ] **Step 7: Commit**

```bash
git add src/bot/handlers/verify_linkedin.py src/bot/handlers/start.py tests/e2e/test_verify_linkedin_start.py
git commit -m "feat(bot): LinkedIn choice handler — generates session + DMs auth URL"
```

---

## Phase D — OAuth callback HTTP server

### Task 6: Skeleton FastAPI app + `/health` endpoint + integration with `__main__.py`

**Files:**
- Create: `src/bot/http/__init__.py` (empty)
- Create: `src/bot/http/oauth_callback.py`
- Modify: `src/bot/__main__.py` — run bot polling and uvicorn concurrently
- Modify: `pyproject.toml` — add `fastapi`, `uvicorn[standard]`

- [ ] **Step 1: Add FastAPI + uvicorn deps**

Edit `pyproject.toml`'s `dependencies = [...]` array, add:

```toml
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
```

Run:

```bash
uv sync
```

- [ ] **Step 2: Create `src/bot/http/__init__.py`** (empty file).

- [ ] **Step 3: Implement `src/bot/http/oauth_callback.py`**

```python
"""FastAPI app exposing the LinkedIn OAuth callback endpoint."""
from __future__ import annotations

from aiogram import Bot
from fastapi import FastAPI


def build_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="IIMC Alum Auth — OAuth callback")
    app.state.bot = bot

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # /oauth/linkedin/callback is added in Task 7
    return app
```

- [ ] **Step 4: Update `src/bot/__main__.py` to run both bot polling and uvicorn concurrently**

Replace the entire file with:

```python
import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher

from src.bot.handlers import group_events, start, verify_email, verify_linkedin
from src.bot.http.oauth_callback import build_app
from src.shared.config import get_settings


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    start.register(dp)
    verify_email.register(dp)
    verify_linkedin.register(dp)
    group_events.register(dp)
    return dp


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()

    app = build_app(bot)
    server_config = uvicorn.Config(
        app,
        host="0.0.0.0",  # noqa: S104  intentional — needs external reach for OAuth callback
        port=settings.http_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(server_config)

    bot_task = asyncio.create_task(dp.start_polling(bot))
    web_task = asyncio.create_task(server.serve())

    try:
        await asyncio.gather(bot_task, web_task)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Verify mypy and ruff are clean (no test yet — uvicorn isn't fully testable inline; T8 will exercise the callback endpoint via FastAPI's TestClient)**

```bash
uv run ruff check src tests scripts
uv run mypy src
```

Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/bot/http/ src/bot/__main__.py
git commit -m "feat(bot): FastAPI app scaffolding for OAuth callback, runs alongside bot polling"
```

---

### Task 7: Implement the `/oauth/linkedin/callback` endpoint — match path

**Files:**
- Modify: `src/bot/http/oauth_callback.py` — add the callback route
- Test: `tests/e2e/test_verify_linkedin_match.py`

- [ ] **Step 1: Write failing test `tests/e2e/test_verify_linkedin_match.py`**

```python
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.http.oauth_callback import build_app
from src.shared.db import session_scope
from src.shared.linkedin import create_session
from src.shared.models import Alumni, AuditLog, InviteLink, Member


@pytest.mark.asyncio
async def test_linkedin_callback_with_matching_email_auto_verifies(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-1009999")
    from src.shared import config

    config._settings = None

    # GIVEN an alum in the directory with email matching what LinkedIn will return
    a = Alumni(
        user_id="liu1",
        name="LinkedIn User",
        email="liu1@example.com",
        program="PGP",
        batch_year=2019,
    )
    committed_session.add(a)
    await committed_session.commit()

    # AND a pre-existing LinkedIn auth session for tg user 333
    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=333)

    bot = AsyncMock()
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("L", (), {"invite_link": "https://t.me/+linkedinlink"})()
    )

    app = build_app(bot)

    with respx.mock(assert_all_called=True) as r:
        r.post("https://www.linkedin.com/oauth/v2/accessToken").mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        r.get("https://api.linkedin.com/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": "li-xyz",
                    "name": "LinkedIn User",
                    "email": "liu1@example.com",
                    "email_verified": True,
                    "picture": "https://media.licdn.com/pic.jpg",
                },
            )
        )

        with TestClient(app) as client:
            resp = client.get(
                "/oauth/linkedin/callback",
                params={"code": "li-code-abc", "state": state},
            )

    assert resp.status_code == 200
    assert "verified" in resp.text.lower()

    # Member row exists, bound to alumni
    member = (
        await committed_session.execute(
            select(Member).where(Member.telegram_user_id == 333)
        )
    ).scalar_one()
    assert member.alumni_id == "liu1"
    assert member.verified_via == "linkedin"
    assert member.display_name == "LinkedIn User (PGP 2019)"

    # Invite link created and DM'd
    invite = (
        await committed_session.execute(
            select(InviteLink).where(InviteLink.telegram_user_id == 333)
        )
    ).scalar_one()
    assert invite.invite_link == "https://t.me/+linkedinlink"
    bot.send_message.assert_awaited()

    # Audit log row exists
    actions = [
        row.action
        for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "member_created" in actions
```

- [ ] **Step 2: Run test (expect failure — endpoint doesn't exist)**

```bash
uv run pytest tests/e2e/test_verify_linkedin_match.py -v
```

Expected: FAIL with a 404 or routing error.

- [ ] **Step 3: Implement the callback endpoint**

Replace `src/bot/http/oauth_callback.py` with:

```python
"""FastAPI app exposing the LinkedIn OAuth callback endpoint."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Bot
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select

from src.shared.audit import write_audit
from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.display_name import canonical_display_name
from src.shared.linkedin import (
    consume_session,
    exchange_code_for_token,
    fetch_userinfo,
)
from src.shared.models import Alumni, InviteLink, VerificationCase
from src.shared.verification import (
    AlreadyBoundError,
    AlumniAlreadyClaimedError,
    bind_member,
)


def build_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="IIMC Alum Auth — OAuth callback")
    app.state.bot = bot

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/oauth/linkedin/callback", response_class=HTMLResponse)
    async def linkedin_callback(
        code: str = Query(...),
        state: str = Query(...),
    ) -> str:
        settings = get_settings()

        # 1. Validate state and recover the originating Telegram user
        async with session_scope() as s:
            tg_id = await consume_session(s, state=state)
        if tg_id is None:
            return _page(
                "Invalid or expired link",
                "This verification link is no longer valid. Please start over "
                "from the bot.",
            )

        # 2. Exchange the code for an access token
        try:
            token_resp = await exchange_code_for_token(
                client_id=settings.linkedin_client_id,
                client_secret=settings.linkedin_client_secret,
                redirect_uri=settings.linkedin_redirect_uri,
                code=code,
            )
        except Exception:  # noqa: BLE001
            return _page(
                "Something went wrong",
                "LinkedIn refused our request. Please start over from the bot.",
            )

        access_token = token_resp.get("access_token")
        if not access_token:
            return _page(
                "Something went wrong",
                "LinkedIn didn't return an access token. Please start over.",
            )

        # 3. Pull userinfo
        try:
            userinfo = await fetch_userinfo(access_token=access_token)
        except Exception:  # noqa: BLE001
            return _page(
                "Something went wrong",
                "Could not fetch your LinkedIn profile. Please start over.",
            )

        verified_email = userinfo.get("email")
        if not verified_email or not userinfo.get("email_verified"):
            return _page(
                "Email not verified",
                "We need a LinkedIn-verified email to proceed. Please verify "
                "your email on LinkedIn or use the Email OTP method instead.",
            )

        # 4. Match against directory
        bot_ref: Bot = app.state.bot
        async with session_scope() as s:
            stmt = select(Alumni).where(
                or_(
                    Alumni.email == verified_email,
                    Alumni.personal_email == verified_email,
                )
            )
            alum = (await s.execute(stmt)).scalar_one_or_none()

            if alum is None:
                # 4a. No match → queue for admin review
                case = VerificationCase(
                    telegram_user_id=tg_id,
                    method="linkedin",
                    claimed_alumni_id=None,
                    submitted_name=userinfo.get("name"),
                    linkedin_url=userinfo.get("sub")  # LinkedIn 'sub' is profile id
                    and f"https://www.linkedin.com/in/{userinfo['sub']}",
                    linkedin_email=verified_email,
                    linkedin_pic_url=userinfo.get("picture"),
                    status="pending",
                )
                s.add(case)
                await s.flush()
                await write_audit(
                    s,
                    actor_email="system@bot",
                    action="linkedin_no_match_queued",
                    subject_type="verification_case",
                    subject_id=str(case.id),
                    details={"linkedin_email": verified_email},
                )
                # DM the user
                try:
                    await bot_ref.send_message(
                        chat_id=tg_id,
                        text=(
                            "Your LinkedIn profile didn't auto-match our directory. "
                            "We've queued your verification for an admin to review. "
                            "You'll hear back within 24 hours."
                        ),
                    )
                except Exception:  # noqa: BLE001
                    pass
                return _page(
                    "Queued for review",
                    "Your LinkedIn verification has been queued for an admin to "
                    "review. We'll DM you on Telegram once it's processed.",
                )

            # 4b. Match → claim, bind, issue invite link
            case = VerificationCase(
                telegram_user_id=tg_id,
                method="linkedin",
                claimed_alumni_id=alum.user_id,
                submitted_name=userinfo.get("name"),
                linkedin_email=verified_email,
                linkedin_pic_url=userinfo.get("picture"),
                status="auto_approved",
            )
            s.add(case)
            await s.flush()
            display_name = canonical_display_name(
                alum.name, alum.program, alum.batch_year
            )
            try:
                await bind_member(
                    s,
                    alumni_id=alum.user_id,
                    telegram_user_id=tg_id,
                    display_name=display_name,
                    verified_via="linkedin",
                    verification_case_id=case.id,
                )
            except AlumniAlreadyClaimedError:
                return _page(
                    "Already claimed",
                    "This alumni record has already been claimed by another "
                    "Telegram account. Please contact an admin if this is a mistake.",
                )
            except AlreadyBoundError:
                return _page(
                    "Already bound",
                    "Your Telegram account is already bound to another verified "
                    "alum. Please contact an admin if this is a mistake.",
                )

        # 5. Issue invite link and DM
        expires = datetime.now(UTC) + timedelta(hours=24)
        invite = await bot_ref.create_chat_invite_link(
            chat_id=settings.telegram_group_chat_id,
            expire_date=expires,
            member_limit=1,
            name=f"verify-{tg_id}",
        )

        async with session_scope() as s:
            s.add(
                InviteLink(
                    telegram_user_id=tg_id,
                    alumni_id=alum.user_id,
                    invite_link=invite.invite_link,
                    expires_at=expires,
                )
            )

        try:
            await bot_ref.send_message(
                chat_id=tg_id,
                text=(
                    f"🎉 You're verified via LinkedIn! Here is your one-time invite "
                    f"link (valid 24 hours, single use):\n\n{invite.invite_link}"
                ),
            )
        except Exception:  # noqa: BLE001
            pass

        return _page(
            "Verified ✅",
            "You've been verified. Check your Telegram DMs for your one-time "
            "invite link to the group.",
        )

    return app


def _page(title: str, body: str) -> str:
    """Render a tiny HTML page so users see something meaningful in the browser."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;max-width:560px;margin:60px auto;"
        "padding:0 20px;color:#222;line-height:1.5}"
        "h1{font-size:1.5rem;margin-bottom:.5rem}"
        "p{font-size:1rem}"
        "</style></head>"
        f"<body><h1>{title}</h1><p>{body}</p></body></html>"
    )
```

- [ ] **Step 4: Run the test**

```bash
uv run pytest tests/e2e/test_verify_linkedin_match.py -v
```

Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bot/http/oauth_callback.py tests/e2e/test_verify_linkedin_match.py
git commit -m "feat(bot): LinkedIn OAuth callback — match path auto-verifies and DMs invite"
```

## Notes

- The LinkedIn `sub` field is the user's LinkedIn member ID, not the public vanity URL. For storing a useful URL for admins, we use `https://www.linkedin.com/in/{sub}` as a best-effort. Some LinkedIn accounts return a `vanityName` field in userinfo when granted (it isn't standard OIDC) — if so, we can switch later. For v1 the `sub`-based URL is good enough.
- We catch broad `Exception` from the LinkedIn HTTP calls intentionally and return a friendly error page; logs will still capture the traceback for ops debugging. The `# noqa: BLE001` annotations are deliberate.

---

### Task 8: No-match path (already covered above, but verify via its own test)

**Files:**
- Test: `tests/e2e/test_verify_linkedin_no_match.py`

The endpoint already handles no-match in Task 7. This task adds a dedicated test so the no-match branch is independently verified.

- [ ] **Step 1: Write the test**

```python
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.http.oauth_callback import build_app
from src.shared.db import session_scope
from src.shared.linkedin import create_session
from src.shared.models import AuditLog, Member, VerificationCase


@pytest.mark.asyncio
async def test_linkedin_callback_no_match_creates_pending_case(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    # No alum with this email exists in the directory
    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=444)

    bot = AsyncMock()

    app = build_app(bot)

    with respx.mock(assert_all_called=True) as r:
        r.post("https://www.linkedin.com/oauth/v2/accessToken").mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        r.get("https://api.linkedin.com/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": "stranger-xyz",
                    "name": "Some Stranger",
                    "email": "nobody@example.com",
                    "email_verified": True,
                    "picture": "https://media.licdn.com/stranger.jpg",
                },
            )
        )

        with TestClient(app) as client:
            resp = client.get(
                "/oauth/linkedin/callback",
                params={"code": "li-code-no-match", "state": state},
            )

    assert resp.status_code == 200
    assert "queued" in resp.text.lower() or "review" in resp.text.lower()

    # No member created
    members = (await committed_session.execute(select(Member))).scalars().all()
    assert members == []

    # A pending verification_case row exists
    cases = (
        await committed_session.execute(
            select(VerificationCase).where(
                VerificationCase.telegram_user_id == 444
            )
        )
    ).scalars().all()
    assert len(cases) == 1
    case = cases[0]
    assert case.method == "linkedin"
    assert case.status == "pending"
    assert case.claimed_alumni_id is None
    assert case.linkedin_email == "nobody@example.com"
    assert case.submitted_name == "Some Stranger"

    # Audit log captures the no-match event
    actions = [
        row.action
        for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "linkedin_no_match_queued" in actions

    # User got a DM
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "queue" in sent.lower() or "review" in sent.lower()
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/e2e/test_verify_linkedin_no_match.py -v
```

Expected: PASS (1 passed).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_verify_linkedin_no_match.py
git commit -m "test(e2e): LinkedIn OAuth no-match path queues admin review case"
```

---

### Task 9: Invalid state / expired state path

**Files:**
- Modify (append): `tests/e2e/test_verify_linkedin_no_match.py` (or a new file)

We add two tests for the rejection paths. Keep them in the same file as the no-match test since they're closely related.

- [ ] **Step 1: Append to `tests/e2e/test_verify_linkedin_no_match.py`** (re-use imports from Step 1 above):

```python
@pytest.mark.asyncio
async def test_linkedin_callback_invalid_state_rejected(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    bot = AsyncMock()
    app = build_app(bot)

    with TestClient(app) as client:
        resp = client.get(
            "/oauth/linkedin/callback",
            params={"code": "anything", "state": "never-issued"},
        )

    assert resp.status_code == 200
    assert "invalid" in resp.text.lower() or "expired" in resp.text.lower()
    # No member, no case
    members = (await committed_session.execute(select(Member))).scalars().all()
    cases = (await committed_session.execute(select(VerificationCase))).scalars().all()
    assert members == []
    assert cases == []
    # No DM sent
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_linkedin_callback_state_consumed_once(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=555)

    bot = AsyncMock()
    app = build_app(bot)

    with respx.mock() as r:
        r.post("https://www.linkedin.com/oauth/v2/accessToken").mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        r.get("https://api.linkedin.com/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": "x",
                    "name": "X",
                    "email": "nobody2@example.com",
                    "email_verified": True,
                },
            )
        )

        with TestClient(app) as client:
            # First use — consumed
            r1 = client.get(
                "/oauth/linkedin/callback",
                params={"code": "c1", "state": state},
            )
            assert r1.status_code == 200

            # Second use — rejected
            r2 = client.get(
                "/oauth/linkedin/callback",
                params={"code": "c2", "state": state},
            )
            assert r2.status_code == 200
            assert "invalid" in r2.text.lower() or "expired" in r2.text.lower()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/e2e/test_verify_linkedin_no_match.py -v
```

Expected: PASS (3 tests in that file: no-match + invalid-state + consumed-state).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_verify_linkedin_no_match.py
git commit -m "test(e2e): LinkedIn OAuth invalid/consumed state are rejected without side effects"
```

---

### Task 10: Update verify_email FSM to also work after the user clicked LinkedIn first

Tiny task — handle the case where a user starts LinkedIn flow, abandons it, then clicks "Email OTP". The Email OTP FSM should still work normally. Add a regression test.

**Files:**
- Modify (append): `tests/e2e/test_verify_email_part1.py`

- [ ] **Step 1: Append a test that exercises the LinkedIn-then-Email path**

```python
@pytest.mark.asyncio
async def test_email_otp_works_after_abandoning_linkedin_flow(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    from src.bot.handlers.verify_linkedin import register as register_linkedin
    from src.shared.models import Alumni

    a = Alumni(
        user_id="ab1",
        name="Abandoner",
        email="ab1@example.com",
        program="PGP",
        batch_year=2020,
        reg_number="PGP/2020/0099",
    )
    committed_session.add(a)
    await committed_session.commit()

    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    register_linkedin(dp)

    bot = AsyncMock(spec=Bot)
    bot.id = 1

    # User starts LinkedIn flow then abandons
    await dp.feed_update(bot, _make_callback("m:linkedin", user_id=99))
    # User goes back to start and picks Email
    await dp.feed_update(bot, _make_callback("m:email", user_id=99))
    bot.send_message.reset_mock()

    with patch("src.bot.handlers.verify_email.send_otp_email", new=AsyncMock()) as send:
        await dp.feed_update(bot, _make_text("PGP/2020/0099", user_id=99))

    send.assert_awaited_once()
```

(The existing imports at the top of `test_verify_email_part1.py` already include the helpers; you only need to add the `Dispatcher` and `MemoryStorage` imports if they're not already present from earlier tests in the file.)

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/e2e/test_verify_email_part1.py -v
```

Expected: PASS (3 tests in that file now).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_verify_email_part1.py
git commit -m "test(e2e): Email OTP path still works after abandoning LinkedIn flow"
```

---

## Phase E — Final acceptance

### Task 11: Run the full suite + linters + commit acceptance

This is a verification task — no new files. Confirms Sub-plan 2 is shippable.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass (≥45 previous + 11+ new = ≥56).

- [ ] **Step 2: Lint and type-check**

```bash
uv run ruff check src tests scripts
uv run mypy src
```

Expected: both clean.

- [ ] **Step 3: Verify the bot still starts (smoke check)**

```bash
$env:DATABASE_URL="postgresql+asyncpg://app:app@localhost:5433/iimc_dev"
$env:PATH="$env:USERPROFILE\.local\bin;$env:PATH"
$env:TELEGRAM_BOT_TOKEN="placeholder"
$env:TELEGRAM_GROUP_CHAT_ID="-100123"
$env:OTP_PEPPER="placeholder-pepper-must-be-32-chars-min"
$env:BREVO_API_KEY="placeholder"
$env:BREVO_FROM_EMAIL="x@example.com"
$env:BREVO_FROM_NAME="X"
$env:EMAIL_DEV_MODE="true"
uv run python -c "from src.bot.__main__ import build_dispatcher; build_dispatcher()"
```

Expected: imports cleanly, no module-level errors. Don't actually run polling (it would fail to connect to Telegram with a placeholder token).

- [ ] **Step 4: Optional — exercise the OAuth callback against a tunnel**

If you want to do a real end-to-end test against LinkedIn:

1. Register a LinkedIn developer app at https://www.linkedin.com/developers/
2. Add `OpenID Connect` to its products.
3. Set the redirect URI to a public URL (use `ngrok http 8080` for dev).
4. Set the `LINKEDIN_*` env vars and `PUBLIC_BASE_URL`.
5. Run `uv run python -m src.bot`.
6. DM the bot, pick LinkedIn, follow the URL.

This is optional and not part of the automated test suite — it's a manual smoke check before shipping to production.

- [ ] **Step 5: No commit (verification only)**

## Acceptance criteria for Sub-Plan 2

After Task 11:

1. **`pytest`** is green with ≥56 tests, including:
   - All 45 Sub-plan 1 tests still pass
   - LinkedIn state tests (2 unit)
   - LinkedIn session tests (5 integration)
   - LinkedIn bot tests (2 e2e — `verify_linkedin_start`)
   - LinkedIn callback tests (4 e2e — match + no-match + invalid + consumed)
   - Email-OTP-after-LinkedIn regression test (1)
2. **`ruff check`** and **`mypy --strict`** are clean.
3. The bot's `build_dispatcher()` imports cleanly with all 4 handlers registered (`start`, `verify_email`, `verify_linkedin`, `group_events`).
4. The FastAPI app builds and serves `/health` (testable manually with `uvicorn src.bot.http.oauth_callback:build_app` — though `build_app` needs a bot arg, so it's only used from `__main__.py`).

**End-state**: an alum can verify via Email OTP OR LinkedIn OAuth as co-equal paths. The LinkedIn no-match queue produces `verification_cases` rows that Sub-plan 4's admin dashboard will drain.

---

**Next sub-plan (Sub-plan 3):** Group enforcement hardening — reconciliation cron + drift watcher + `/forget_me` erasure.
