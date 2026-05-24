import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from alembic.config import Config


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


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_engine() -> AsyncIterator[None]:
    """Dispose the module-level engine after each test.

    pytest-asyncio (auto mode) creates a fresh event loop per test. The
    `src.shared.db` module caches a singleton engine on first use; once the
    test's loop closes, asyncpg connections bound to that loop become invalid
    and the next test fails with "Event loop is closed" during pool checkout.
    Disposing after each test forces the next handler call to build a fresh
    engine on the new loop.
    """
    yield
    import contextlib

    from src.shared import db as _db

    if _db._engine is not None:
        with contextlib.suppress(Exception):
            await _db._engine.dispose()
        _db._engine = None
        _db._session_factory = None


@pytest_asyncio.fixture
async def committed_session(_migrations: None) -> AsyncIterator[AsyncSession]:
    """A session that commits. Used for e2e tests where handlers need to see data
    written before the handler runs. Cleans up by TRUNCATEing all tables at teardown."""
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
