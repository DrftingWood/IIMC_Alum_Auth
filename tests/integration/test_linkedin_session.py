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
        await session.execute(select(LinkedInAuthSession).where(LinkedInAuthSession.state == state))
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
        await session.execute(select(LinkedInAuthSession).where(LinkedInAuthSession.state == state))
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
        await session.execute(select(LinkedInAuthSession).where(LinkedInAuthSession.state == state))
    ).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    assert await consume_session(session, state=state) is None
