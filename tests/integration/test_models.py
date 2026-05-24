from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import (
    Alumni,
    LinkedInAuthSession,
    Member,
    OtpCode,
)


@pytest.mark.asyncio
async def test_database_is_up(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1 AS ok"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_alumni_table_exists(session: AsyncSession) -> None:
    result = await session.execute(
        text("SELECT count(*) FROM information_schema.tables WHERE table_name = 'alumni'")
    )
    assert result.scalar_one() == 1


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
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.add(o)
    await session.flush()
    assert o.id is not None
    assert o.attempts == 0


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
