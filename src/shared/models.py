from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Alumni(Base):
    __tablename__ = "alumni"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT)
    personal_email: Mapped[str | None] = mapped_column(CITEXT)
    status: Mapped[str | None] = mapped_column(Text)
    batch_year: Mapped[int | None] = mapped_column(Integer)
    program: Mapped[str | None] = mapped_column(Text)
    reg_number: Mapped[str | None] = mapped_column(Text)
    mobile: Mapped[str | None] = mapped_column(Text)
    home_city: Mapped[str | None] = mapped_column(Text)
    home_country: Mapped[str | None] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VerificationCase(Base):
    __tablename__ = "verification_cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_alumni_id: Mapped[str | None] = mapped_column(Text, ForeignKey("alumni.user_id"))
    submitted_name: Mapped[str | None] = mapped_column(Text)
    submitted_reg: Mapped[str | None] = mapped_column(Text)
    submitted_batch: Mapped[int | None] = mapped_column(Integer)
    submitted_program: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    linkedin_email: Mapped[str | None] = mapped_column(CITEXT)
    linkedin_pic_url: Mapped[str | None] = mapped_column(Text)
    free_text_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alumni_id: Mapped[str] = mapped_column(Text, ForeignKey("alumni.user_id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alumni_id: Mapped[str] = mapped_column(Text, ForeignKey("alumni.user_id"), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    verified_via: Mapped[str] = mapped_column(Text, nullable=False)
    verification_case_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verification_cases.id")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    drift_incidents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drift_last_sampled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drift_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InviteLink(Base):
    __tablename__ = "invite_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alumni_id: Mapped[str] = mapped_column(Text, ForeignKey("alumni.user_id"), nullable=False)
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LinkedInAuthSession(Base):
    __tablename__ = "linkedin_auth_sessions"

    state: Mapped[str] = mapped_column(Text, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
