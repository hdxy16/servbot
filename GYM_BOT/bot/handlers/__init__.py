from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.keyboards.reply import get_main_menu
from database.models import User

base_router = Router()


@base_router.message(CommandStart())
async def cmd_start(message: Message, user_db: User):
    await message.answer(
        f"👋 Вітаю, {message.from_user.full_name}!\n"
        f"Ви успішно авторизовані.\n\n"
        f"🎭 Поточний режим роботи: <b>{user_db.active_role}</b>\n\n"
        f"Оберіть дію з меню нижче 👇",
        reply_markup=get_main_menu(user_db)
    )


@base_router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Глобальна команда скасування."""
    await state.clear()
    await message.answer("❌ Дію скасовано.")