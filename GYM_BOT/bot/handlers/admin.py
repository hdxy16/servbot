import logging
import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsAdmin
from database.models import User, AuditLog, Broadcast, Notification
from bot.keyboards.reply import get_main_menu

logger = logging.getLogger(__name__)
admin_router = Router()
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())


# ==========================================
# ТЕСТОВИЙ ХЕНДЛЕР - ЛОВИТЬ ВСІ ПОВІДОМЛЕННЯ
# ==========================================

@admin_router.message()
async def admin_any_message(message: Message, user_db: User):
    """Тестовий хендлер - ловить всі повідомлення адміна."""
    logger.info(f"ADMIN got message: '{message.text}' from {user_db.full_name}")
    await message.answer(f"📩 Отримано: '{message.text}' (тест)")


# ==========================================
# ОСНОВНІ ХЕНДЛЕРИ
# ==========================================

@admin_router.message(F.text == "👥 Клієнти")
async def admin_clients(message: Message, session: AsyncSession):
    """Показати всіх клієнтів."""
    try:
        stmt = select(User).where(User.is_client == True).limit(50)
        clients = (await session.execute(stmt)).scalars().all()
        
        if not clients:
            await message.answer("Клієнтів поки немає.")
            return
        
        text = "👥 <b>Всі клієнти:</b>\n\n"
        for client in clients:
            text += f"• {client.full_name} (@{client.username or 'без ніка'}) [ID: {client.telegram_id}]\n"
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting admin clients: {e}")
        await message.answer(f"❌ Помилка: {str(e)}")


@admin_router.message(F.text == "📊 Статистика")
async def admin_statistics(message: Message, session: AsyncSession):
    """Показати загальну статистику."""
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
        await message.answer(f"❌ Помилка: {str(e)}")


@admin_router.message(F.text == "📢 Розсилки")
async def admin_broadcast(message: Message, state: FSMContext):
    """Початок створення розсилки."""
    await state.set_state("broadcast_text")
    await message.answer(
        "📢 <b>Створення розсилки</b>\n\n"
        "Введіть текст повідомлення для розсилки.\n"
        "Для скасування натисніть /cancel"
    )


@admin_router.message(Command("cancel"))
@admin_router.message(F.text == "/cancel")
async def admin_cancel(message: Message, state: FSMContext):
    """Скасування поточної дії."""
    await state.clear()
    await message.answer("❌ Дію скасовано.")


@admin_router.message("broadcast_text")
async def process_broadcast(message: Message, state: FSMContext):
    """Обробка тексту розсилки."""
    await state.update_data(text=message.text)
    await state.set_state("broadcast_target")
    await message.answer(
        "Оберіть цільову аудиторію:\n"
        "1 - Всі користувачі\n"
        "2 - Активні\n"
        "3 - Неактивні\n\n"
        "Напишіть цифру:"
    )


@admin_router.message("broadcast_target")
async def process_broadcast_target(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    """Обробка вибору аудиторії."""
    target_map = {"1": "all", "2": "active", "3": "inactive"}
    target = target_map.get(message.text.strip())
    
    if not target:
        return await message.answer("❌ Введіть 1, 2 або 3.")
    
    data = await state.get_data()
    broadcast_text = data["text"]
    
    try:
        stmt = select(User)
        if target == "active":
            stmt = stmt.where(User.is_client == True)
        elif target == "inactive":
            stmt = stmt.where(User.is_client == False)
        
        users = (await session.execute(stmt)).scalars().all()
        
        broadcast = Broadcast(
            author_id=user_db.id,
            text=broadcast_text,
            target=target
        )
        session.add(broadcast)
        
        for user in users:
            notification = Notification(
                user_id=user.id,
                type="broadcast",
                text=broadcast_text,
                scheduled_at=datetime.datetime.utcnow(),
                is_sent=False
            )
            session.add(notification)
        
        await session.commit()
        
        await message.answer(
            f"✅ Розсилку створено!\n"
            f"Текст: {broadcast_text[:100]}...\n"
            f"Аудиторія: {target}\n"
            f"Отримувачів: {len(users)}"
        )
    except Exception as e:
        logger.error(f"Error creating broadcast: {e}")
        await message.answer(f"❌ Помилка: {str(e)}")
    
    await state.clear()


@admin_router.message(F.text == "📝 Логи")
async def admin_logs(message: Message, session: AsyncSession):
    """Показати останні логи аудиту."""
    try:
        stmt = select(AuditLog).order_by(AuditLog.date.desc()).limit(20)
        logs = (await session.execute(stmt)).scalars().all()
        
        if not logs:
            await message.answer("📝 Логів поки немає.")
            return
        
        text = "📝 <b>Останні логи аудиту:</b>\n\n"
        for log in logs:
            date_str = log.date.strftime('%d.%m %H:%M')
            actor = await session.get(User, log.actor_id)
            actor_name = actor.full_name if actor else f"ID:{log.actor_id}"
            
            text += f"• {date_str} | {actor_name} | {log.action}\n"
            if log.details:
                text += f"  {log.details}\n"
        
        await message.answer(text[:4000])
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        await message.answer(f"❌ Помилка: {str(e)}")


@admin_router.message(F.text == "⚙️ Налаштування")
async def admin_settings(message: Message, session: AsyncSession, user_db: User):
    """Налаштування адміна."""
    text = (
        f"⚙️ <b>Налаштування</b>\n\n"
        f"👤 Користувач: {user_db.full_name}\n"
        f"🆔 ID: {user_db.telegram_id}\n"
        f"🎭 Роль: {user_db.active_role}\n"
        f"📋 Ролі: {', '.join(user_db.roles)}\n"
    )
    await message.answer(text)


@admin_router.message(F.text == "🔄 Переключити режим")
async def admin_switch_role(message: Message, user_db: User, session: AsyncSession):
    """Переключення ролі."""
    try:
        if len(user_db.roles) <= 1:
            return await message.answer("У вас тільки одна роль.")
        
        current_index = user_db.roles.index(user_db.active_role)
        next_index = (current_index + 1) % len(user_db.roles)
        new_role = user_db.roles[next_index]
        
        user_db.active_role = new_role
        await session.commit()
        await session.refresh(user_db)
        
        await message.answer(
            f"🔄 Режим змінено на: <b>{new_role}</b>",
            reply_markup=get_main_menu(user_db)
        )
    except Exception as e:
        logger.error(f"Error switching role: {e}")
        await message.answer(f"❌ Помилка: {str(e)}")