"""LinkedIn OIDC helpers — state generation, session lifecycle, userinfo fetch."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import LinkedInAuthSession

SESSION_TTL = timedelta(minutes=15)
AUTHORIZATION_ENDPOINT = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_ENDPOINT = "https://www.linkedin.com/oauth/v2/accessToken"  # noqa: S105
USERINFO_ENDPOINT = "https://api.linkedin.com/v2/userinfo"


def generate_state() -> str:
    """Return a URL-safe random 32-byte token (~43 chars after base64)."""
    return secrets.token_urlsafe(32)


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile email",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def create_session(session: AsyncSession, *, telegram_user_id: int) -> str:
    """Insert a new auth session and return the state token."""
    state = generate_state()
    session.add(
        LinkedInAuthSession(
            state=state,
            telegram_user_id=telegram_user_id,
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    return state


async def consume_session(session: AsyncSession, *, state: str) -> int | None:
    """Atomically consume an auth session. Returns telegram_user_id on success,
    None if not found / already consumed / expired."""
    now = datetime.now(UTC)
    row = (
        await session.execute(select(LinkedInAuthSession).where(LinkedInAuthSession.state == state))
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.consumed_at is not None:
        return None
    if row.expires_at <= now:
        return None
    row.consumed_at = now
    return row.telegram_user_id


async def exchange_code_for_token(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, str]:
    """Exchange an authorization code for an access token + id_token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(*, access_token: str) -> dict[str, str]:
    """Fetch the OIDC userinfo claims (name, email, sub, picture)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
