import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.filters.role_filter import IsClient
from bot.keyboards.reply import get_main_menu
from database.models import User, ClientProfile, FAQ, TrainerClient

logger = logging.getLogger(__name__)
client_router = Router()
client_router.message.filter(IsClient())
client_router.callback_query.filter(IsClient())


# ==========================================
# ПРОФІЛЬ
# ==========================================

@client_router.message(F.text == "⚙️ Профіль")
async def cmd_profile(message: Message, session: AsyncSession, user_db: User):
    """Показати профіль клієнта."""
    try:
        profile = await session.get(ClientProfile, user_db.id)
        
        text = (
            f"👤 <b>Мій профіль</b>\n\n"
            f"Ім'я: {user_db.full_name}\n"
            f"Телеграм: @{user_db.username or 'немає'}\n"
            f"ID: {user_db.telegram_id}\n"
            f"Роль: {user_db.active_role}\n\n"
        )
        
        if profile:
            text += (
                f"📊 <b>Дані клієнта:</b>\n"
                f"Вік: {profile.age or 'не вказано'}\n"
                f"Стать: {profile.gender or 'не вказано'}\n"
                f"Зріст: {profile.height or 'не вказано'} см\n"
                f"Вага: {profile.current_weight or 'не вказано'} кг\n"
                f"Ціль: {profile.goal or 'не вказано'}\n"
                f"Рівень: {profile.level or 'не вказано'}\n"
                f"Статус: {'✅ Активний' if profile.is_active else '❌ Неактивний'}\n"
            )
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        await message.answer("❌ Помилка завантаження профілю.")


# ==========================================
# НАПИСАТИ ТРЕНЕРУ
# ==========================================

@client_router.message(F.text == "💬 Написати тренеру")
async def cmd_write_trainer(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    """Початок листування з тренером."""
    try:
        # Перевіряємо, чи є у клієнта тренер
        stmt = select(TrainerClient).where(
            TrainerClient.client_id == user_db.id,
            TrainerClient.is_active == True
        )
        trainer_link = (await session.execute(stmt)).scalar_one_or_none()
        
        if not trainer_link:
            await message.answer(
                "❌ У вас ще немає прикріпленого тренера.\n"
                "Зверніться до адміністратора."
            )
            return
        
        trainer = await session.get(User, trainer_link.trainer_id)
        
        await state.set_state("waiting_trainer_message")
        await state.update_data(trainer_id=trainer.id)
        
        await message.answer(
            f"💬 <b>Написати тренеру</b>\n\n"
            f"Ваш тренер: <b>{trainer.full_name}</b>\n\n"
            f"Напишіть ваше повідомлення нижче.\n"
            f"Тренер отримає його і зможе відповісти.\n\n"
            f"Для скасування натисніть /cancel"
        )
    except Exception as e:
        logger.error(f"Error writing to trainer: {e}")
        await message.answer("❌ Помилка.")


@client_router.message(F.text == "/cancel")
async def client_cancel(message: Message, state: FSMContext):
    """Скасування поточної дії."""
    await state.clear()
    await message.answer("❌ Дію скасовано.")


@client_router.message("waiting_trainer_message")
async def process_trainer_message(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    """Обробка повідомлення тренеру."""
    data = await state.get_data()
    trainer_id = data.get("trainer_id")
    
    if not trainer_id:
        await message.answer("❌ Помилка. Спробуйте ще раз.")
        await state.clear()
        return
    
    try:
        from config import BOT_TOKEN
        from aiogram import Bot
        
        bot = Bot(token=BOT_TOKEN)
        
        await bot.send_message(
            trainer_id,
            f"💬 <b>Повідомлення від клієнта</b>\n"
            f"👤 {user_db.full_name}\n\n"
            f"{message.text}"
        )
        await bot.session.close()
        
        await message.answer("✅ Ваше повідомлення надіслано тренеру!")
        await state.clear()
    except Exception as e:
        logger.error(f"Error sending message to trainer: {e}")
        await message.answer("❌ Помилка надсилання повідомлення.")


# ==========================================
# FAQ
# ==========================================

@client_router.message(F.text == "📚 FAQ")
async def cmd_faq(message: Message, session: AsyncSession):
    """Показати FAQ."""
    try:
        stmt = select(FAQ).order_by(FAQ.category)
        faqs = (await session.execute(stmt)).scalars().all()
        
        if not faqs:
            await message.answer(
                "📚 <b>FAQ</b>\n\n"
                "Поки немає запитань.\n"
                "Зверніться до тренера з вашими питаннями."
            )
            return
        
        categories = {}
        for faq in faqs:
            if faq.category not in categories:
                categories[faq.category] = []
            categories[faq.category].append(faq)
        
        text = "📚 <b>FAQ</b>\n\n"
        for category, items in categories.items():
            text += f"<b>{category}</b>\n"
            for faq in items:
                text += f"❓ {faq.question}\n"
                text += f"✅ {faq.answer}\n\n"
        
        await message.answer(text[:4000])
    except Exception as e:
        logger.error(f"Error getting FAQ: {e}")
        await message.answer("❌ Помилка завантаження FAQ.")