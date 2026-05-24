import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.bot.handlers import group_events, start, verify_email
from src.shared.config import get_settings


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    start.register(dp)
    verify_email.register(dp)
    group_events.register(dp)
    return dp


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
