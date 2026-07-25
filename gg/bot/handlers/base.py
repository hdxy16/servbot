import logging
from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from aiogram.utils.deep_linking import decode_payload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.reply import get_main_menu
from database.models import User
from bot.services.invite_service import link_client_to_trainer

logger = logging.getLogger(__name__)
base_router = Router()

@base_router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, command: CommandObject, user_db: User, session: AsyncSession):
    """Обробка команди /start із payload (запрошення від тренера)."""
    args = command.args
    try:
        payload = decode_payload(args)
        if payload.startswith("trainer_"):
            trainer_id = int(payload.split("_")[1])
            success = await link_client_to_trainer(session, trainer_id, user_db.id)
            
            if success:
                await message.answer(
                    "✅ <b>Вітаємо!</b>\nВи успішно приєдналися до свого тренера.\n"
                    "Тепер ви можете використовувати меню нижче для роботи з раціоном та тренуваннями.",
                    reply_markup=get_main_menu(user_db)
                )
                return
    except Exception as e:
        logger.error(f"Error decoding deep link payload: {e}")
        
    # Якщо посилання недійсне або виникла помилка, падаємо в стандартний /start
    await message.answer(
        f"Вітаю, {message.from_user.full_name}!\nВи успішно авторизовані.\n\nПоточний режим роботи: <b>{user_db.active_role}</b>",
        reply_markup=get_main_menu(user_db)
    )

@base_router.message(CommandStart())
async def cmd_start(message: Message, user_db: User):
    """Стандартна обробка команди /start."""
    await message.answer(
        f"Вітаю, {message.from_user.full_name}!\nВи успішно авторизовані.\n\nПоточний режим роботи: <b>{user_db.active_role}</b>",
        reply_markup=get_main_menu(user_db)
    )