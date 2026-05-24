from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


def _method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📧 Verify with Email OTP", callback_data="m:email"),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Verify with LinkedIn",
                    callback_data="m:linkedin",
                ),
            ],
        ]
    )


async def handle_start(message: Message, bot: Bot) -> None:
    text = (
        "👋 Welcome to the IIM C Alumni verification bot.\n\n"
        "To join the alumni Telegram group, you'll need to verify that you're "
        "in the official directory. Choose how you'd like to verify:"
    )
    await bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=_method_kb(),
    )


def register(dp: Dispatcher) -> None:
    dp.message.register(handle_start, CommandStart())
