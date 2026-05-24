import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import Alumni, VerificationCase
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
async def test_lookup_alumni_by_reg_case_insensitive(session: AsyncSession, alum: Alumni) -> None:
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
async def test_bind_member_double_claim_raises(session: AsyncSession, alum: Alumni) -> None:
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
async def test_bind_member_tg_already_bound_raises(session: AsyncSession, alum: Alumni) -> None:
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
