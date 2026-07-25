import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsAdmin
from database.models import User, AuditLog, Broadcast
from bot.keyboards.trainer import TrainerClientCB

logger = logging.getLogger(__name__)
admin_router = Router()
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())


class BroadcastFSM(StatesGroup):
    text = State()
    target = State()


@admin_router.message(F.text == "👥 Клієнти")
async def admin_clients(message: Message, session: AsyncSession):
    try:
        stmt = select(User).where(User.is_client == True).limit(20)
        result = await session.execute(stmt)
        clients = result.scalars().all()
        
        if not clients:
            await message.answer("Клієнтів поки немає.")
            return
        
        text = "👥 <b>Всі клієнти:</b>\n\n"
        for client in clients:
            text += f"• {client.full_name} (@{client.username or 'без ніка'}) [ID: {client.telegram_id}]\n"
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting admin clients: {e}")
        await message.answer("❌ Помилка.")


@admin_router.message(F.text == "📊 Статистика")
async def admin_statistics(message: Message, session: AsyncSession):
    try:
        total_users = await session.scalar(select(func.count()).select_from(User))
        total_clients = await session.scalar(
            select(func.count()).select_from(User).where(User.is_client == True)
        )
        total_trainers = await session.scalar(
            select(func.count()).select_from(User).where(User.is_trainer == True)
        )
        
        text = (
            f"📊 <b>Загальна статистика</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Всього користувачів: <b>{total_users or 0}</b>\n"
            f"👤 Клієнтів: <b>{total_clients or 0}</b>\n"
            f"👨‍🏫 Тренерів: <b>{total_trainers or 0}</b>\n"
        )
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        await message.answer("❌ Помилка.")


@admin_router.message(F.text == "📢 Розсилки")
async def admin_broadcast(message: Message, state: FSMContext):
    await state.set_state(BroadcastFSM.text)
    await message.answer(
        "📢 <b>Створення розсилки</b>\n\n"
        "Введіть текст повідомлення для розсилки.\n"
        "Для скасування натисніть /cancel"
    )


@admin_router.message(StateFilter(BroadcastFSM.text))
async def process_broadcast_text(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    await state.update_data(text=message.text)
    await state.set_state(BroadcastFSM.target)
    await message.answer(
        "Оберіть цільову аудиторію:\n"
        "1 - Всі користувачі\n"
        "2 - Активні\n"
        "3 - Неактивні\n\n"
        "Напишіть цифру:"
    )


@admin_router.message(StateFilter(BroadcastFSM.target))
async def process_broadcast_target(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    target_map = {
        "1": "all",
        "2": "active",
        "3": "inactive"
    }
    
    target = target_map.get(message.text.strip())
    if not target:
        return await message.answer("❌ Введіть 1, 2 або 3.")
    
    data = await state.get_data()
    
    broadcast = Broadcast(
        author_id=user_db.id,
        text=data["text"],
        target=target
    )
    session.add(broadcast)
    await session.commit()
    
    await message.answer(
        f"✅ Розсилку створено!\n"
        f"Текст: {data['text'][:100]}...\n"
        f"Аудиторія: {target}\n\n"
        f"⚠️ Відправка розсилки потребує додаткової реалізації."
    )
    await state.clear()


@admin_router.message(F.text == "📝 Логи")
async def admin_logs(message: Message, session: AsyncSession):
    try:
        stmt = select(AuditLog).order_by(AuditLog.date.desc()).limit(10)
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        if not logs:
            await message.answer("Логів поки немає.")
            return
        
        text = "📝 <b>Останні логи аудиту:</b>\n\n"
        for log in logs:
            actor_name = f"ID:{log.actor_id}"
            text += f"• {log.date.strftime('%H:%M')} | {actor_name} | {log.action}\n"
            if log.details:
                text += f"  {log.details}\n"
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        await message.answer("❌ Помилка.")


@admin_router.message(F.text == "⚙️ Налаштування")
async def admin_settings(message: Message):
    await message.answer(
        "⚙️ <b>Налаштування</b>\n\n"
        "Функціонал в розробці."
    )


@admin_router.message(F.text == "🔄 Переключити режим")
async def admin_switch_role(message: Message, user_db: User, session: AsyncSession):
    if len(user_db.roles) <= 1:
        return await message.answer("У вас тільки одна роль.")
    
    current_index = user_db.roles.index(user_db.active_role)
    next_index = (current_index + 1) % len(user_db.roles)
    new_role = user_db.roles[next_index]
    
    user_db.active_role = new_role
    await session.commit()
    
    await message.answer(f"🔄 Режим змінено на: <b>{new_role}</b>")