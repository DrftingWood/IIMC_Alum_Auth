from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_email import register as register_verify_email
from src.bot.handlers.verify_linkedin import register as register_linkedin
from src.shared.models import Alumni


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    return dp


def _dp_with_linkedin() -> Dispatcher:
    """A dispatcher with start, verify_email, AND verify_linkedin registered."""
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_verify_email(dp)
    register_linkedin(dp)
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
async def test_email_choice_asks_for_reg_number() -> None:
    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    bot.send_message.assert_awaited()
    last = bot.send_message.await_args_list[-1].kwargs
    assert "reg" in last["text"].lower() or "registration" in last["text"].lower()


@pytest.mark.asyncio
async def test_reg_number_lookup_match_sends_otp(committed_session: AsyncSession) -> None:
    a = Alumni(
        user_id="bot1",
        name="Bot Alum",
        email="bot1@example.com",
        program="PGP",
        batch_year=2015,
        reg_number="PGP/2015/0001",
    )
    committed_session.add(a)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _make_callback("m:email"))
    bot.send_message.reset_mock()

    # Patch the email sender to assert it was called
    with patch("src.bot.handlers.verify_email.send_otp_email", new=AsyncMock()) as send:
        await dp.feed_update(bot, _make_text("PGP/2015/0001"))

    # Bot should reply with masked-email confirmation
    sent_messages = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "b••••@example.com" in sent_messages
    send.assert_awaited_once()
    assert send.await_args.kwargs["to"] == "bot1@example.com"


@pytest.mark.asyncio
async def test_email_otp_works_after_abandoning_linkedin_flow(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config
    from src.shared.models import Alumni

    config._settings = None

    a = Alumni(
        user_id="ab1",
        name="Abandoner",
        email="ab1@example.com",
        program="PGP",
        batch_year=2020,
        reg_number="PGP/2020/0099",
    )
    committed_session.add(a)
    await committed_session.commit()

    dp = _dp_with_linkedin()

    bot = AsyncMock(spec=Bot)
    bot.id = 1

    # User starts LinkedIn flow then abandons (just clicks the button — no completion)
    await dp.feed_update(bot, _make_callback("m:linkedin", user_id=99))
    # User goes back to start and picks Email
    await dp.feed_update(bot, _make_callback("m:email", user_id=99))
    bot.send_message.reset_mock()

    with patch("src.bot.handlers.verify_email.send_otp_email", new=AsyncMock()) as send:
        await dp.feed_update(bot, _make_text("PGP/2020/0099", user_id=99))

    send.assert_awaited_once()
