from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.shared.models import Alumni, Member


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    return dp


def _make_callback(data: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "chat_instance": "ci",
                "data": data,
                "message": {
                    "message_id": 100,
                    "date": 0,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": 1, "is_bot": True, "first_name": "Bot"},
                    "text": "...",
                },
            },
        }
    )


def _make_text(text: str, user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 101,
                "date": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "text": text,
            },
        }
    )


@pytest.mark.asyncio
async def test_full_happy_path_creates_member(
    committed_session: AsyncSession,
) -> None:
    a = Alumni(
        user_id="hp1",
        name="Happy Path",
        email="hp1@example.com",
        program="PGP",
        batch_year=2017,
        reg_number="PGP/2017/0042",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    # Simulate the Telegram invite-link API
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("X", (), {"invite_link": "https://t.me/+abc"})()
    )

    captured_code: dict[str, str] = {}

    async def fake_send_otp_email(*, to: str, code: str) -> None:
        captured_code["code"] = code

    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    with patch("src.bot.handlers.verify_email.send_otp_email", new=fake_send_otp_email):
        await dp.feed_update(bot, _make_text("PGP/2017/0042"))

    assert captured_code["code"], "OTP send was not called"

    # Submit the correct code
    await dp.feed_update(bot, _make_text(captured_code["code"]))
    # Accept the default display name
    await dp.feed_update(bot, _make_text("ok"))

    # A member row should now exist
    members = (await committed_session.execute(select(Member))).scalars().all()
    assert len(members) == 1
    m = members[0]
    assert m.alumni_id == "hp1"
    assert m.telegram_user_id == 42
    assert m.display_name == "Happy Path (PGP 2017)"
    assert m.status == "active"

    # Telegram invite-link API should have been called
    bot.create_chat_invite_link.assert_awaited_once()
    # Last DM should contain the invite link
    final_text = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "https://t.me/+abc" in final_text


@pytest.mark.asyncio
async def test_wrong_code_then_correct(committed_session: AsyncSession) -> None:
    a = Alumni(
        user_id="wc1",
        name="Wrong Code",
        email="wc1@example.com",
        program="PGP",
        batch_year=2018,
        reg_number="PGP/2018/0011",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("X", (), {"invite_link": "https://t.me/+xyz"})()
    )
    captured: dict[str, str] = {}

    async def fake_send(*, to: str, code: str) -> None:
        captured["code"] = code

    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    with patch("src.bot.handlers.verify_email.send_otp_email", new=fake_send):
        await dp.feed_update(bot, _make_text("PGP/2018/0011"))
    await dp.feed_update(bot, _make_text("000000"))  # wrong
    await dp.feed_update(bot, _make_text(captured["code"]))  # correct
    await dp.feed_update(bot, _make_text("ok"))

    members = (await committed_session.execute(select(Member))).scalars().all()
    assert len(members) == 1
