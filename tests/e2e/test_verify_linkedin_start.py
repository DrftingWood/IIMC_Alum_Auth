from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.start import register as register_start
from src.bot.handlers.verify_linkedin import register as register_linkedin
from src.shared.models import LinkedInAuthSession


def _dp() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    register_start(dp)
    register_linkedin(dp)
    return dp


def _click_linkedin(user_id: int = 42) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "c1",
                "from": {"id": user_id, "is_bot": False, "first_name": "Alum"},
                "chat_instance": "ci",
                "data": "m:linkedin",
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


@pytest.mark.asyncio
async def test_linkedin_choice_dms_auth_url_and_creates_session(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "test-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _click_linkedin(user_id=42))

    # The bot should have DM'd an authorization URL
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "linkedin.com/oauth/v2/authorization" in sent
    assert "state=" in sent

    # A LinkedInAuthSession row should exist for this tg user
    sessions = (
        (
            await committed_session.execute(
                select(LinkedInAuthSession).where(LinkedInAuthSession.telegram_user_id == 42)
            )
        )
        .scalars()
        .all()
    )
    assert len(sessions) == 1
    assert sessions[0].consumed_at is None


@pytest.mark.asyncio
async def test_linkedin_choice_unconfigured_shows_coming_soon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "")
    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "")
    from src.shared import config

    config._settings = None

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()
    await dp.feed_update(bot, _click_linkedin(user_id=43))

    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "not configured" in sent.lower() or "not available" in sent.lower()
