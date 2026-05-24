from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.linkedin import build_authorization_url, create_session


async def handle_method_linkedin(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    if callback.message is None or callback.from_user is None:
        return

    settings = get_settings()
    if not (
        settings.linkedin_client_id
        and settings.linkedin_client_secret
        and settings.linkedin_redirect_uri
    ):
        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=(
                "LinkedIn verification is not configured on this bot yet. "
                "Please use Email OTP for now."
            ),
        )
        return

    async with session_scope() as s:
        state = await create_session(s, telegram_user_id=callback.from_user.id)

    auth_url = build_authorization_url(
        client_id=settings.linkedin_client_id,
        redirect_uri=settings.linkedin_redirect_uri,
        state=state,
    )

    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=(
            "Tap the link below to sign in with LinkedIn. After you approve, "
            "you'll be redirected back to a confirmation page and we'll let "
            "you know here whether your record matched.\n\n"
            f"{auth_url}\n\n"
            "(Link expires in 15 minutes.)"
        ),
    )


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_linkedin, F.data == "m:linkedin")
