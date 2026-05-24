from datetime import UTC, datetime, timedelta

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
async def test_verify_otp_wrong_code_increments(session: AsyncSession, alum: Alumni) -> None:
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
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    r = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=code
    )
    assert r == OtpResult.EXPIRED


@pytest.mark.asyncio
async def test_issuing_invalidates_prior_active_otp(session: AsyncSession, alum: Alumni) -> None:
    c1 = await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    await issue_otp(session, telegram_user_id=111, alumni_id=alum.user_id)
    await session.flush()
    # Old code no longer works
    r = await verify_otp_submission(
        session, telegram_user_id=111, alumni_id=alum.user_id, submitted=c1
    )
    assert r in (OtpResult.WRONG, OtpResult.NO_ACTIVE_OTP)
