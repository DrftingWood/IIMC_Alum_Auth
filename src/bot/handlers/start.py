from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
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
                    text="🔗 Verify with LinkedIn (coming soon)",
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


async def handle_linkedin_choice(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.message is not None:
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text="LinkedIn verification isn't available yet. Please use Email OTP for now.",
        )


def register(dp: Dispatcher) -> None:
    dp.message.register(handle_start, CommandStart())
    dp.callback_query.register(handle_linkedin_choice, F.data == "m:linkedin")
