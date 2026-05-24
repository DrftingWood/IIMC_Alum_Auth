"""FastAPI app exposing the LinkedIn OAuth callback endpoint."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select

from src.shared.audit import write_audit
from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.display_name import canonical_display_name
from src.shared.linkedin import (
    consume_session,
    exchange_code_for_token,
    fetch_userinfo,
)
from src.shared.models import Alumni, InviteLink, VerificationCase
from src.shared.verification import (
    AlreadyBoundError,
    AlumniAlreadyClaimedError,
    bind_member,
)


def build_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="IIMC Alum Auth — OAuth callback")
    app.state.bot = bot

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/oauth/linkedin/callback", response_class=HTMLResponse)
    async def linkedin_callback(
        code: str = Query(...),
        state: str = Query(...),
    ) -> str:
        settings = get_settings()

        # 1. Validate state and recover the originating Telegram user
        async with session_scope() as s:
            tg_id = await consume_session(s, state=state)
        if tg_id is None:
            return _page(
                "Invalid or expired link",
                "This verification link is no longer valid. Please start over from the bot.",
            )

        # 2. Exchange the code for an access token
        try:
            token_resp = await exchange_code_for_token(
                client_id=settings.linkedin_client_id,
                client_secret=settings.linkedin_client_secret,
                redirect_uri=settings.linkedin_redirect_uri,
                code=code,
            )
        except Exception:  # noqa: BLE001
            return _page(
                "Something went wrong",
                "LinkedIn refused our request. Please start over from the bot.",
            )

        access_token = token_resp.get("access_token")
        if not access_token:
            return _page(
                "Something went wrong",
                "LinkedIn didn't return an access token. Please start over.",
            )

        # 3. Pull userinfo
        try:
            userinfo = await fetch_userinfo(access_token=access_token)
        except Exception:  # noqa: BLE001
            return _page(
                "Something went wrong",
                "Could not fetch your LinkedIn profile. Please start over.",
            )

        verified_email = userinfo.get("email")
        if not verified_email or not userinfo.get("email_verified"):
            return _page(
                "Email not verified",
                "We need a LinkedIn-verified email to proceed. Please verify "
                "your email on LinkedIn or use the Email OTP method instead.",
            )

        # 4. Match against directory
        bot_ref: Bot = app.state.bot
        async with session_scope() as s:
            stmt = select(Alumni).where(
                or_(
                    Alumni.email == verified_email,
                    Alumni.personal_email == verified_email,
                )
            )
            alum = (await s.execute(stmt)).scalar_one_or_none()

            if alum is None:
                # 4a. No match → queue for admin review
                case = VerificationCase(
                    telegram_user_id=tg_id,
                    method="linkedin",
                    claimed_alumni_id=None,
                    submitted_name=userinfo.get("name"),
                    linkedin_url=userinfo.get("sub")
                    and f"https://www.linkedin.com/in/{userinfo['sub']}",
                    linkedin_email=verified_email,
                    linkedin_pic_url=userinfo.get("picture"),
                    status="pending",
                )
                s.add(case)
                await s.flush()
                await write_audit(
                    s,
                    actor_email="system@bot",
                    action="linkedin_no_match_queued",
                    subject_type="verification_case",
                    subject_id=str(case.id),
                    details={"linkedin_email": verified_email},
                )
                # DM the user (best-effort)
                with contextlib.suppress(Exception):
                    await bot_ref.send_message(
                        chat_id=tg_id,
                        text=(
                            "Your LinkedIn profile didn't auto-match our directory. "
                            "We've queued your verification for an admin to review. "
                            "You'll hear back within 24 hours."
                        ),
                    )
                return _page(
                    "Queued for review",
                    "Your LinkedIn verification has been queued for an admin to "
                    "review. We'll DM you on Telegram once it's processed.",
                )

            # 4b. Match → claim, bind, issue invite link
            case = VerificationCase(
                telegram_user_id=tg_id,
                method="linkedin",
                claimed_alumni_id=alum.user_id,
                submitted_name=userinfo.get("name"),
                linkedin_email=verified_email,
                linkedin_pic_url=userinfo.get("picture"),
                status="auto_approved",
            )
            s.add(case)
            await s.flush()
            display_name = canonical_display_name(alum.name, alum.program, alum.batch_year)
            try:
                await bind_member(
                    s,
                    alumni_id=alum.user_id,
                    telegram_user_id=tg_id,
                    display_name=display_name,
                    verified_via="linkedin",
                    verification_case_id=case.id,
                )
            except AlumniAlreadyClaimedError:
                return _page(
                    "Already claimed",
                    "This alumni record has already been claimed by another "
                    "Telegram account. Please contact an admin if this is a mistake.",
                )
            except AlreadyBoundError:
                return _page(
                    "Already bound",
                    "Your Telegram account is already bound to another verified "
                    "alum. Please contact an admin if this is a mistake.",
                )

        # 5. Issue invite link and DM
        expires = datetime.now(UTC) + timedelta(hours=24)
        invite = await bot_ref.create_chat_invite_link(
            chat_id=settings.telegram_group_chat_id,
            expire_date=expires,
            member_limit=1,
            name=f"verify-{tg_id}",
        )

        async with session_scope() as s:
            s.add(
                InviteLink(
                    telegram_user_id=tg_id,
                    alumni_id=alum.user_id,
                    invite_link=invite.invite_link,
                    expires_at=expires,
                )
            )

        with contextlib.suppress(Exception):
            await bot_ref.send_message(
                chat_id=tg_id,
                text=(
                    f"🎉 You're verified via LinkedIn! Here is your one-time invite "
                    f"link (valid 24 hours, single use):\n\n{invite.invite_link}"
                ),
            )

        return _page(
            "Verified ✅",
            "You've been verified. Check your Telegram DMs for your one-time "
            "invite link to the group.",
        )

    return app


def _page(title: str, body: str) -> str:
    """Render a tiny HTML page so users see something meaningful in the browser."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;max-width:560px;margin:60px auto;"
        "padding:0 20px;color:#222;line-height:1.5}"
        "h1{font-size:1.5rem;margin-bottom:.5rem}"
        "p{font-size:1rem}"
        "</style></head>"
        f"<body><h1>{title}</h1><p>{body}</p></body></html>"
    )
