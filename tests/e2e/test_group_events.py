from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.group_events import register as register_group
from src.shared.models import Alumni, Member


def _dp() -> Dispatcher:
    dp = Dispatcher()
    register_group(dp)
    return dp


def _chat_member_joined(user_id: int, chat_id: int) -> Update:
    return Update.model_validate(
        {
            "update_id": 99,
            "chat_member": {
                "chat": {"id": chat_id, "type": "supergroup", "title": "G"},
                "from": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                "date": 0,
                "old_chat_member": {
                    "user": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                    "status": "left",
                },
                "new_chat_member": {
                    "user": {"id": user_id, "is_bot": False, "first_name": "Joiner"},
                    "status": "member",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_unbound_joiner_is_kicked(committed_session: AsyncSession) -> None:
    from src.shared.config import get_settings

    chat_id = get_settings().telegram_group_chat_id

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()

    await dp.feed_update(bot, _chat_member_joined(user_id=777, chat_id=chat_id))

    bot.ban_chat_member.assert_awaited_once()
    bot.unban_chat_member.assert_awaited_once()
    # And a DM should be attempted (may swallow if user has DMs off)
    bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_bound_joiner_gets_welcome(committed_session: AsyncSession) -> None:
    from src.shared.config import get_settings

    chat_id = get_settings().telegram_group_chat_id

    a = Alumni(user_id="g1", name="Greeted", program="PGP", batch_year=2019)
    committed_session.add(a)
    m = Member(
        alumni_id="g1",
        telegram_user_id=888,
        display_name="Greeted (PGP 2019)",
        status="active",
        verified_via="email_otp",
    )
    committed_session.add(m)
    await committed_session.commit()

    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = _dp()

    await dp.feed_update(bot, _chat_member_joined(user_id=888, chat_id=chat_id))

    bot.ban_chat_member.assert_not_awaited()
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "Greeted (PGP 2019)" in sent
