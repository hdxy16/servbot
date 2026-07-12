from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from bot.keyboards.reply import get_main_menu
from database.models import User

# Базовий роутер для обробки базових команд до моменту створення CRM хендлерів
base_router = Router()

@base_router.message(CommandStart())
async def cmd_start(message: Message, user_db: User):
    await message.answer(
        f"Вітаю, {message.from_user.full_name}!\nВи успішно авторизовані.\n\nПоточний режим роботи: <b>{user_db.active_role}</b>",
        reply_markup=get_main_menu(user_db)
    )