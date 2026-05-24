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
