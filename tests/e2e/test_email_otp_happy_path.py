"""The single-test definition of 'v1 works': from /start to invite link DM."""

from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.group_events import register as register_group
from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.shared.models import Alumni, AuditLog, InviteLink, Member


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    register_group(dp)
    return dp


def _send_start(user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "text": "/start",
            },
        }
    )


def _click_email(user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "chat_instance": "ci",
                "data": "m:email",
                "message": {
                    "message_id": 2,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "...",
                },
            },
        }
    )


def _send_text(text: str, msg_id: int, user_id: int = 4242) -> Update:
    return Update.model_validate(
        {
            "update_id": msg_id,
            "message": {
                "message_id": msg_id,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Hero"},
                "text": text,
            },
        }
    )


@pytest.mark.asyncio
async def test_v1_email_otp_full_happy_path(
    committed_session: AsyncSession,
) -> None:
    # GIVEN an alum is in the directory
    a = Alumni(
        user_id="herov1",
        name="Hero V1",
        email="hero@example.com",
        program="PGP",
        batch_year=2016,
        reg_number="PGP/2016/0007",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("L", (), {"invite_link": "https://t.me/+herolink"})()
    )

    captured: dict[str, str] = {}

    async def fake_send(*, to: str, code: str) -> None:
        captured["code"] = code
        captured["to"] = to

    dp = _dp()

    # WHEN they walk the full flow
    await dp.feed_update(bot, _send_start())
    await dp.feed_update(bot, _click_email())
    with patch("src.bot.handlers.verify_email.send_otp_email", new=fake_send):
        await dp.feed_update(bot, _send_text("PGP/2016/0007", msg_id=3))
    await dp.feed_update(bot, _send_text(captured["code"], msg_id=4))
    await dp.feed_update(bot, _send_text("ok", msg_id=5))

    # THEN: OTP went to their real address
    assert captured["to"] == "hero@example.com"

    # THEN: a member row exists, bound and active
    member = (
        await committed_session.execute(select(Member).where(Member.telegram_user_id == 4242))
    ).scalar_one()
    assert member.alumni_id == "herov1"
    assert member.status == "active"
    assert member.display_name == "Hero V1 (PGP 2016)"
    assert member.verified_via == "email_otp"

    # THEN: an invite link was generated and recorded
    invite = (
        await committed_session.execute(
            select(InviteLink).where(InviteLink.telegram_user_id == 4242)
        )
    ).scalar_one()
    assert invite.invite_link == "https://t.me/+herolink"

    # THEN: the user was DM'd the invite link
    dms = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "https://t.me/+herolink" in dms

    # THEN: audit_log captured member_created
    actions = [
        row.action for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "member_created" in actions
