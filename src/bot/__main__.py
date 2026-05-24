import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher

from src.bot.handlers import group_events, start, verify_email, verify_linkedin
from src.bot.http.oauth_callback import build_app
from src.shared.config import get_settings


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    start.register(dp)
    verify_email.register(dp)
    verify_linkedin.register(dp)
    group_events.register(dp)
    return dp


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()

    app = build_app(bot)
    server_config = uvicorn.Config(
        app,
        host="0.0.0.0",  # noqa: S104  intentional — needs external reach for OAuth callback
        port=settings.http_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(server_config)

    bot_task = asyncio.create_task(dp.start_polling(bot))
    web_task = asyncio.create_task(server.serve())

    try:
        await asyncio.gather(bot_task, web_task)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
