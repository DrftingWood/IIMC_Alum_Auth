import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.config import get_settings
from src.shared.models import OtpCode

OTP_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 3


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


class OtpResult(StrEnum):
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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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
        return OtpResult.EXHAUSTED

    if verify_code(submitted, row.code_hash):
        row.consumed_at = now
        return OtpResult.OK

    row.attempts += 1
    if row.attempts >= MAX_ATTEMPTS:
        return OtpResult.EXHAUSTED
    return OtpResult.WRONG
