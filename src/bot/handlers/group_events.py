import contextlib

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ChatMemberUpdated
from sqlalchemy import select

from src.shared.config import get_settings
from src.shared.db import session_scope
from src.shared.models import Member


async def _is_active_member(telegram_user_id: int) -> Member | None:
    async with session_scope() as s:
        stmt = select(Member).where(
            Member.telegram_user_id == telegram_user_id,
            Member.status == "active",
        )
        return (await s.execute(stmt)).scalar_one_or_none()


async def handle_chat_member(event: ChatMemberUpdated, bot: Bot) -> None:
    settings = get_settings()
    if event.chat.id != settings.telegram_group_chat_id:
        return
    if event.new_chat_member.status not in {"member", "restricted"}:
        return
    if event.old_chat_member.status in {"member", "restricted", "administrator"}:
        return  # already a member; this is a status change, not a fresh join

    tg_id = event.new_chat_member.user.id
    member = await _is_active_member(tg_id)

    if member is None:
        # Kick (ban + unban so they can retry after verifying)
        try:
            await bot.ban_chat_member(chat_id=event.chat.id, user_id=tg_id)
        finally:
            await bot.unban_chat_member(chat_id=event.chat.id, user_id=tg_id)
        # user may have DMs closed; nothing we can do in that case
        with contextlib.suppress(TelegramForbiddenError):
            await bot.send_message(
                chat_id=tg_id,
                text=(
                    "You tried to join the IIM C alumni group but you're not "
                    "verified yet. Please DM @IIMCAlumBot and run /start first."
                ),
            )
        return

    # Bound and active — welcome.
    await bot.send_message(
        chat_id=event.chat.id,
        text=f"👋 Welcome <b>{member.display_name}</b>!",
        parse_mode="HTML",
    )


def register(dp: Dispatcher) -> None:
    dp.chat_member.register(handle_chat_member)
