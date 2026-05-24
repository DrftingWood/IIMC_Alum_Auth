from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.display_name import canonical_display_name, mask_email
from src.shared.email import send_otp_email
from src.shared.models import Alumni, InviteLink, VerificationCase
from src.shared.otp import OtpResult, issue_otp, verify_otp_submission
from src.shared.verification import (
    AlreadyBoundError,
    AlumniAlreadyClaimedError,
    bind_member,
    lookup_alumni_by_reg,
)


class EmailVerify(StatesGroup):
    waiting_reg_number = State()
    waiting_otp_code = State()
    waiting_display_name = State()


async def handle_method_email(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(EmailVerify.waiting_reg_number)
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=(
            "Please reply with your IIM C registration number "
            "(e.g. PGP/2015/0123 or PGDM/2010/0456)."
        ),
    )


async def handle_reg_number(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text or not message.from_user:
        return
    reg = message.text.strip()
    async with session_scope() as s:
        alum = await lookup_alumni_by_reg(s, reg)
        if alum is None:
            await bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "We couldn't find that registration number in the directory. "
                    "Please double-check and try again, or contact an admin if you "
                    "believe this is wrong."
                ),
            )
            return
        if not alum.email:
            await bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "We found a record but it has no email on file. Please contact "
                    "an admin to verify manually."
                ),
            )
            await state.clear()
            return

        code = await issue_otp(
            s,
            telegram_user_id=message.from_user.id,
            alumni_id=alum.user_id,
        )

    await send_otp_email(to=alum.email, code=code)
    await state.update_data(alumni_id=alum.user_id, alum_email=alum.email)
    await state.set_state(EmailVerify.waiting_otp_code)
    await bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"A 6-digit code has been sent to {mask_email(alum.email)}.\n"
            "It expires in 10 minutes. Reply with the code to continue."
        ),
    )


async def handle_otp_code(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text or not message.from_user:
        return
    submitted = message.text.strip()
    data = await state.get_data()
    alumni_id: str | None = data.get("alumni_id")
    if alumni_id is None:
        await bot.send_message(chat_id=message.chat.id, text="Session expired. Please /start over.")
        await state.clear()
        return

    async with session_scope() as s:
        result = await verify_otp_submission(
            s,
            telegram_user_id=message.from_user.id,
            alumni_id=alumni_id,
            submitted=submitted,
        )

    if result == OtpResult.WRONG:
        await bot.send_message(chat_id=message.chat.id, text="That code didn't match. Try again.")
        return
    if result == OtpResult.NO_ACTIVE_OTP:
        await bot.send_message(
            chat_id=message.chat.id,
            text="No active code found. Please /start over to request a new one.",
        )
        await state.clear()
        return
    if result == OtpResult.EXPIRED:
        await bot.send_message(
            chat_id=message.chat.id,
            text="That code has expired. Please /start over to request a new one.",
        )
        await state.clear()
        return
    if result == OtpResult.EXHAUSTED:
        await bot.send_message(
            chat_id=message.chat.id,
            text=(
                "Too many incorrect attempts. Please /start over after a few minutes, "
                "or contact an admin."
            ),
        )
        await state.clear()
        return

    async with session_scope() as s:
        alum = await s.get(Alumni, alumni_id)
        if alum is None:
            await bot.send_message(
                chat_id=message.chat.id, text="Internal error. Please /start over."
            )
            await state.clear()
            return
        default_name = canonical_display_name(alum.name, alum.program, alum.batch_year)

    await state.update_data(default_display_name=default_name)
    await state.set_state(EmailVerify.waiting_display_name)
    await bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"✅ Verified.\n\nYour display name in the group will be:\n\n"
            f"  <b>{default_name}</b>\n\n"
            f"Reply 'ok' to accept, or send a different display name."
        ),
        parse_mode="HTML",
    )


async def handle_display_name(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text or not message.from_user:
        return
    data = await state.get_data()
    alumni_id: str | None = data.get("alumni_id")
    default: str | None = data.get("default_display_name")
    if alumni_id is None or default is None:
        await bot.send_message(chat_id=message.chat.id, text="Session expired. Please /start over.")
        await state.clear()
        return

    chosen = default if message.text.strip().lower() in {"ok", "yes", "y"} else message.text.strip()
    chosen = chosen[:64]

    async with session_scope() as s:
        case = VerificationCase(
            telegram_user_id=message.from_user.id,
            method="email_otp",
            claimed_alumni_id=alumni_id,
            status="auto_approved",
        )
        s.add(case)
        await s.flush()
        try:
            await bind_member(
                s,
                alumni_id=alumni_id,
                telegram_user_id=message.from_user.id,
                display_name=chosen,
                verified_via="email_otp",
                verification_case_id=case.id,
            )
        except AlumniAlreadyClaimedError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "This alumni record has already been claimed by another Telegram "
                    "account. If this is a mistake, please contact an admin."
                ),
            )
            await state.clear()
            return
        except AlreadyBoundError:
            await bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "Your Telegram account is already bound to another verified alum. "
                    "If this is a mistake, please contact an admin."
                ),
            )
            await state.clear()
            return

    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(hours=24)
    invite = await bot.create_chat_invite_link(
        chat_id=settings.telegram_group_chat_id,
        expire_date=expires,
        member_limit=1,
        name=f"verify-{message.from_user.id}",
    )

    async with session_scope() as s:
        s.add(
            InviteLink(
                telegram_user_id=message.from_user.id,
                alumni_id=alumni_id,
                invite_link=invite.invite_link,
                expires_at=expires,
            )
        )

    await bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"🎉 You're verified! Here is your one-time invite link "
            f"(valid for 24 hours, single use):\n\n{invite.invite_link}"
        ),
    )
    await state.clear()


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_email, F.data == "m:email")
    dp.message.register(handle_reg_number, EmailVerify.waiting_reg_number)
    dp.message.register(handle_otp_code, EmailVerify.waiting_otp_code)
    dp.message.register(handle_display_name, EmailVerify.waiting_display_name)
