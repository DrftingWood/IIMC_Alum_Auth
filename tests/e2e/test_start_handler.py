from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from src.bot.handlers.start import register as register_start


@pytest.mark.asyncio
async def test_start_command_replies_with_method_choice() -> None:
    bot = AsyncMock(spec=Bot)
    bot.id = 1
    dp = Dispatcher()
    register_start(dp)

    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Alum"},
                "text": "/start",
            },
        }
    )
    await dp.feed_update(bot, update)

    bot.send_message.assert_awaited_once()
    sent = bot.send_message.await_args.kwargs
    assert sent["chat_id"] == 42
    assert "verify" in sent["text"].lower()
    # the inline keyboard should advertise both methods
    keyboard = sent["reply_markup"].inline_keyboard
    button_texts = [b.text.lower() for row in keyboard for b in row]
    assert any("email" in t for t in button_texts)
    assert any("linkedin" in t for t in button_texts)
