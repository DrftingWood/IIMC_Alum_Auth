from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.http.oauth_callback import build_app
from src.shared.db import reset_engine_for_tests, session_scope
from src.shared.linkedin import create_session
from src.shared.models import Alumni, AuditLog, InviteLink, Member


@pytest.mark.asyncio
async def test_linkedin_callback_with_matching_email_auto_verifies(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-1009999")
    from src.shared import config

    config._settings = None

    # GIVEN an alum in the directory with email matching what LinkedIn will return
    a = Alumni(
        user_id="liu1",
        name="LinkedIn User",
        email="liu1@example.com",
        program="PGP",
        batch_year=2019,
    )
    committed_session.add(a)
    await committed_session.commit()

    # AND a pre-existing LinkedIn auth session for tg user 333
    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=333)

    bot = AsyncMock()
    bot.create_chat_invite_link = AsyncMock(
        return_value=type("L", (), {"invite_link": "https://t.me/+linkedinlink"})()
    )

    app = build_app(bot)

    # TestClient runs the app in its own thread + event loop. Dispose the shared
    # engine cached on the outer test loop so the handler builds a fresh one
    # bound to TestClient's loop.
    await reset_engine_for_tests()

    with respx.mock(assert_all_called=True) as r:
        r.post("https://www.linkedin.com/oauth/v2/accessToken").mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        r.get("https://api.linkedin.com/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": "li-xyz",
                    "name": "LinkedIn User",
                    "email": "liu1@example.com",
                    "email_verified": True,
                    "picture": "https://media.licdn.com/pic.jpg",
                },
            )
        )

        with TestClient(app) as client:
            resp = client.get(
                "/oauth/linkedin/callback",
                params={"code": "li-code-abc", "state": state},
            )

    assert resp.status_code == 200
    assert "verified" in resp.text.lower()

    # Member row exists, bound to alumni
    member = (
        await committed_session.execute(select(Member).where(Member.telegram_user_id == 333))
    ).scalar_one()
    assert member.alumni_id == "liu1"
    assert member.verified_via == "linkedin"
    assert member.display_name == "LinkedIn User (PGP 2019)"

    # Invite link created and DM'd
    invite = (
        await committed_session.execute(
            select(InviteLink).where(InviteLink.telegram_user_id == 333)
        )
    ).scalar_one()
    assert invite.invite_link == "https://t.me/+linkedinlink"
    bot.send_message.assert_awaited()

    # Audit log row exists
    actions = [
        row.action for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "member_created" in actions
