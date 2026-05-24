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
from src.shared.models import AuditLog, Member, VerificationCase


@pytest.mark.asyncio
async def test_linkedin_callback_no_match_creates_pending_case(
    committed_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "csecret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI",
        "https://example.com/oauth/linkedin/callback",
    )
    from src.shared import config

    config._settings = None

    # GIVEN no alum with the LinkedIn email exists in the directory
    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=444)

    # Reset the shared engine so TestClient's loop gets its own
    await reset_engine_for_tests()

    bot = AsyncMock()
    app = build_app(bot)

    with respx.mock(assert_all_called=True) as r:
        r.post("https://www.linkedin.com/oauth/v2/accessToken").mock(
            return_value=httpx.Response(200, json={"access_token": "at"})
        )
        r.get("https://api.linkedin.com/v2/userinfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "sub": "stranger-xyz",
                    "name": "Some Stranger",
                    "email": "nobody@example.com",
                    "email_verified": True,
                    "picture": "https://media.licdn.com/stranger.jpg",
                },
            )
        )

        with TestClient(app) as client:
            resp = client.get(
                "/oauth/linkedin/callback",
                params={"code": "li-code-no-match", "state": state},
            )

    assert resp.status_code == 200
    assert "queued" in resp.text.lower() or "review" in resp.text.lower()

    # No member created
    members = (await committed_session.execute(select(Member))).scalars().all()
    assert members == []

    # A pending verification_case row exists
    cases = (
        (
            await committed_session.execute(
                select(VerificationCase).where(VerificationCase.telegram_user_id == 444)
            )
        )
        .scalars()
        .all()
    )
    assert len(cases) == 1
    case = cases[0]
    assert case.method == "linkedin"
    assert case.status == "pending"
    assert case.claimed_alumni_id is None
    assert case.linkedin_email == "nobody@example.com"
    assert case.submitted_name == "Some Stranger"

    # Audit log captures the no-match event
    actions = [
        row.action for row in (await committed_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "linkedin_no_match_queued" in actions

    # User got a DM
    bot.send_message.assert_awaited()
    sent = " ".join(c.kwargs.get("text", "") for c in bot.send_message.await_args_list)
    assert "queue" in sent.lower() or "review" in sent.lower()
