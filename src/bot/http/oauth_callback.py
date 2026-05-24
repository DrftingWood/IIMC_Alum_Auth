"""FastAPI app exposing the LinkedIn OAuth callback endpoint."""

from __future__ import annotations

from aiogram import Bot
from fastapi import FastAPI


def build_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="IIMC Alum Auth — OAuth callback")
    app.state.bot = bot

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # /oauth/linkedin/callback is added in Task 7
    return app
