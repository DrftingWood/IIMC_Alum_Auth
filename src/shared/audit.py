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
