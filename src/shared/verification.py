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


async def lookup_alumni_by_reg(session: AsyncSession, reg_number: str) -> Alumni | None:
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
    telegram_user_id. Inspects IntegrityError message to distinguish which
    constraint fired.
    """
    # SELECT ... FOR UPDATE on the alumni row to serialize concurrent claims
    await session.execute(select(Alumni).where(Alumni.user_id == alumni_id).with_for_update())

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
            raise AlreadyBoundError(f"telegram_user_id {telegram_user_id} already bound") from exc
        if "members_one_active_per_alumni" in msg:
            raise AlumniAlreadyClaimedError(f"alumni_id {alumni_id} already claimed") from exc
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
