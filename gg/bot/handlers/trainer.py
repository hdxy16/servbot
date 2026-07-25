import asyncio
import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import (
    TrainerClientCB,
    clients_list_keyboard,
    client_card_keyboard,
    client_edit_keyboard,
    cancel_edit_keyboard
)
from bot.services import client_service, audit_service

logger = logging.getLogger(__name__)
trainer_router = Router()
trainer_router.message.filter(IsTrainer())
trainer_router.callback_query.filter(IsTrainer())

class TrainerEditFSM(StatesGroup):
    waiting_for_value = State()


@trainer_router.message(F.text == "🍎 Харчування")
async def trainer_food_menu(message: Message, session: AsyncSession, user_db: User):
    await cmd_clients(message, session, user_db)


@trainer_router.message(F.text == "🏋️ Тренування")
async def trainer_gym_menu(message: Message, session: AsyncSession, user_db: User):
    await cmd_clients(message, session, user_db)


@trainer_router.message(F.text == "👥 Клієнти")
async def cmd_clients(message: Message, session: AsyncSession, user_db: User):
    try:
        clients_data, total_pages = await client_service.get_trainer_clients(session, user_db.id, page=1)
        
        if not clients_data:
            await message.answer("У вас поки немає прикріплених клієнтів.")
            return
        
        await message.answer(
            "👥 <b>Ваші клієнти:</b>\n<i>Оберіть клієнта для перегляду деталей:</i>",
            reply_markup=clients_list_keyboard(clients_data, page=1, total_pages=total_pages)
        )
    except Exception as e:
        logger.error(f"Error getting clients: {e}")
        await message.answer("❌ Помилка завантаження списку клієнтів.")


@trainer_router.callback_query(TrainerClientCB.filter(F.action == "list"))
async def cb_clients_list(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession, user_db: User):
    try:
        page = callback_data.page
        clients_data, total_pages = await client_service.get_trainer_clients(session, user_db.id, page=page)
        
        await callback.message.edit_text(
            f"👥 <b>Ваші клієнти (Сторінка {page}/{total_pages}):</b>",
            reply_markup=clients_list_keyboard(clients_data, page=page, total_pages=total_pages)
        )
    except Exception as e:
        logger.error(f"Error pagination: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


@trainer_router.callback_query(TrainerClientCB.filter(F.action == "card"))
async def cb_client_card(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession, state: FSMContext):
    await state.clear()
    try:
        client_data = await client_service.get_client_by_id(session, callback_data.client_id)
        if not client_data:
            return await callback.answer("Клієнта не знайдено.", show_alert=True)
        
        user, profile = client_data
        
        text = (
            f"👤 <b>Картка клієнта: {user.full_name}</b>\n\n"
            f"⚖️ Вага: <b>{profile.current_weight or 'Не вказано'} кг</b>\n"
            f"🎯 Ціль: <b>{profile.goal or 'Не вказано'}</b>\n"
            f"📅 Старт: <b>{profile.start_date.strftime('%d.%m.%Y')}</b>\n"
            f"🟢 Статус: <b>{'Активний' if profile.is_active else 'Неактивний'}</b>\n\n"
            f"<i>Оберіть дію:</i>"
        )
        
        await callback.message.edit_text(text, reply_markup=client_card_keyboard(user.id))
    except Exception as e:
        logger.error(f"Error getting client card: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


@trainer_router.callback_query(TrainerClientCB.filter(F.action == "info"))
async def cb_client_info(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
    try:
        client_data = await client_service.get_client_by_id(session, callback_data.client_id)
        if not client_data:
            return await callback.answer("Помилка даних клієнта.", show_alert=True)
        
        user, profile = client_data
        
        text = (
            f"📊 <b>Детальна інформація | {user.full_name}</b>\n\n"
            f"Вік: <b>{profile.age or '?'}</b>\n"
            f"Стать: <b>{profile.gender or '?'}</b>\n"
            f"Ріст: <b>{profile.height or '?'} см</b>\n"
            f"Стартова вага: <b>{profile.start_weight or '?'} кг</b>\n"
            f"Поточна вага: <b>{profile.current_weight or '?'} кг</b>\n"
            f"Ціль: <b>{profile.goal or '?'}</b>\n"
            f"Рівень: <b>{profile.level or '?'}</b>\n"
            f"Дата початку: <b>{profile.start_date.strftime('%d.%m.%Y')}</b>\n"
            f"Наступний чекін: <b>{profile.next_checkin.strftime('%d.%m.%Y') if profile.next_checkin else 'Не задано'}</b>\n\n"
            f"📝 Нотатки:\n<i>{profile.notes or 'Немає нотаток.'}</i>"
        )
        
        await callback.message.edit_text(text, reply_markup=client_edit_keyboard(user.id))
    except Exception as e:
        logger.error(f"Error getting client info: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


@trainer_router.callback_query(TrainerClientCB.filter(F.action == "edit_field"))
async def cb_edit_field(callback: CallbackQuery, callback_data: TrainerClientCB, state: FSMContext):
    field_map_ru = {
        "name": "Ім'я",
        "age": "Вік",
        "gender": "Стать",
        "height": "Ріст (см)",
        "start_weight": "Стартову вагу (кг)",
        "current_weight": "Поточну вагу (кг)",
        "goal": "Ціль",
        "level": "Рівень",
        "next_checkin": "Дату наступного чекіну (ДД.ММ.РРРР)",
        "notes": "Нотатки"
    }
    field_name = field_map_ru.get(callback_data.field, callback_data.field)
    
    await state.set_state(TrainerEditFSM.waiting_for_value)
    await state.update_data(client_id=callback_data.client_id, field=callback_data.field)
    
    await callback.message.edit_text(
        f"✏️ <b>Введіть нове значення для поля:</b> {field_name}",
        reply_markup=cancel_edit_keyboard(callback_data.client_id)
    )
    await callback.answer()


@trainer_router.message(TrainerEditFSM.waiting_for_value)
async def process_edit_value(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    data = await state.get_data()
    client_id = data["client_id"]
    field = data["field"]
    new_value = message.text.strip()
    
    try:
        old_val, new_val_saved = await client_service.update_client_profile(session, client_id, field, new_value)
        
        await audit_service.log_action(
            session,
            actor_id=user_db.id,
            target_user_id=client_id,
            action="update_profile",
            details={"field": field, "old": old_val, "new": str(new_val_saved)}
        )
        
        await message.answer(f"✅ Поле оновлено: <b>{old_val} ➡️ {new_val_saved}</b>")
    except ValueError as e:
        await message.answer(f"❌ Помилка формату: {str(e)}\nСпробуйте ще раз або скасуйте.")
        return
    except Exception as e:
        logger.error(f"Error updating client {client_id}: {e}")
        await message.answer("❌ Виникла системна помилка при збереженні.")
        return
    
    await state.clear()
    
    await message.answer(
        "🔙 Повернення до картки...",
        reply_markup=client_card_keyboard(client_id)
    )


@trainer_router.callback_query(TrainerClientCB.filter(F.action == "delete"))
async def cb_delete_client(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession, user_db: User):
    client_id = callback_data.client_id
    success = await client_service.delete_client(session, user_db.id, client_id)
    
    if success:
        await audit_service.log_action(session, user_db.id, client_id, "unlinked_client")
        await callback.message.edit_text("🗑 Клієнта успішно відкріплено від вас.")
    else:
        await callback.message.edit_text("❌ Помилка відкріплення. Клієнта не знайдено.")
    
    await asyncio.sleep(2)
    
    clients_data, total_pages = await client_service.get_trainer_clients(session, user_db.id, page=1)
    await callback.message.answer(
        "👥 <b>Ваші клієнти:</b>",
        reply_markup=clients_list_keyboard(clients_data, page=1, total_pages=total_pages)
    )
    await callback.answer()


@trainer_router.message(F.text == "📊 Статистика")
async def cmd_statistics(message: Message, session: AsyncSession, user_db: User):
    try:
        stats = await client_service.get_trainer_statistics(session, user_db.id)
        
        text = (
            f"📊 <b>Ваша статистика як тренера:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Всього клієнтів: <b>{stats['total']}</b>\n"
            f"🟢 Активних: <b>{stats['active']}</b>\n"
            f"🆕 Нових за місяць: <b>{stats['new_month']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚖️ Середня вага клієнтів: <b>{stats['avg_weight']:.1f} кг</b>\n"
            f"📉 Середня втрата ваги: <b>{stats['avg_change']:.1f} кг</b>\n"
        )
        
        await message.answer(text)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await message.answer("❌ Помилка завантаження статистики.")