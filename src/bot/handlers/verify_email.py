from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.shared.db import session_scope
from src.shared.display_name import mask_email
from src.shared.email import send_otp_email
from src.shared.otp import issue_otp
from src.shared.verification import lookup_alumni_by_reg


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


def register(dp: Dispatcher) -> None:
    dp.callback_query.register(handle_method_email, F.data == "m:email")
    dp.message.register(handle_reg_number, EmailVerify.waiting_reg_number)
