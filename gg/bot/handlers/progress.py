import datetime
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsClient, IsTrainer
from bot.keyboards.trainer import TrainerClientCB, client_card_keyboard
from bot.services.progress_service import (
    add_measurement,
    get_measurements,
    add_progress_photo,
    get_progress_photos,
    get_latest_measurement
)
from bot.services.analytics_service import get_client_full_analytics
from database.models import User


# Роутери
client_progress_router = Router()
trainer_progress_router = Router()

client_progress_router.message.filter(IsClient())
client_progress_router.callback_query.filter(IsClient())

trainer_progress_router.message.filter(IsTrainer())
trainer_progress_router.callback_query.filter(IsTrainer())


# ====================
# КЛІЄНТ - ПРОГРЕС
# ====================

@client_progress_router.message(F.text == "📈 Мій прогрес")
async def cmd_my_progress(message: Message, session: AsyncSession, user_db: User):
    """Показати прогрес клієнта."""
    try:
        analytics = await get_client_full_analytics(session, user_db.id)
        
        if not analytics:
            await message.answer("📊 Дані про прогрес ще не накопичено.\n\nДодайте заміри через команду:\n<code>⚖️ Додати замір</code>")
            return
        
        # Отримуємо останній замір для деталей
        latest = await get_latest_measurement(session, user_db.id)
        
        text = (
            f"📈 <b>Мій прогрес</b>\n\n"
            f"⚖️ <b>Вага:</b>\n"
            f"  Стартова: {analytics['weight']['start_weight'] or '?'} кг\n"
            f"  Поточна: {analytics['weight']['current_weight'] or '?'} кг\n"
            f"  Зміна: {analytics['weight']['diff_total'] or '?'} кг\n\n"
        )
        
        if latest and (latest.chest or latest.waist or latest.hips):
            text += f"📐 <b>Останні заміри:</b>\n"
            if latest.chest:
                text += f"  Груди: {latest.chest} см\n"
            if latest.waist:
                text += f"  Талія: {latest.waist} см\n"
            if latest.hips:
                text += f"  Стегна: {latest.hips} см\n"
            text += "\n"
        
        text += (
            f"🏋️ <b>Тренування:</b>\n"
            f"  Всього: {analytics['workouts']['total_count']}\n\n"
            f"🍎 <b>Харчування:</b>\n"
            f"  Днів трекінгу: {analytics['nutrition']['days_tracked']}\n\n"
            f"<i>Додайте новий замір: ⚖️ Додати замір</i>"
        )
        
        await message.answer(text)
    except Exception as e:
        await message.answer(f"❌ Помилка: {str(e)}")


@client_progress_router.message(F.text == "⚖️ Додати замір")
async def cmd_add_measurement(message: Message, state: FSMContext):
    """Початок додавання заміру."""
    await state.set_state("waiting_measurement")
    await message.answer(
        "📝 Введіть заміри через пробіл:\n\n"
        "Формат: <code>вага груди талія стегна руки</code>\n"
        "Наприклад: <code>75 100 80 95 35</code>\n\n"
        "Можна ввести тільки вагу: <code>75</code>\n"
        "Можна ввести вагу та обхвати: <code>75 100 80</code>\n\n"
        "Для скасування натисніть /cancel"
    )


@client_progress_router.message(F.text == "📸 Фото прогресу")
async def cmd_progress_photo(message: Message, state: FSMContext):
    """Початок додавання фото прогресу."""
    await state.set_state("waiting_progress_photo")
    await message.answer(
        "📸 Надішліть фото прогресу.\n"
        "В описі вкажіть ракурс (front/side/back):\n\n"
        "Наприклад: <code>front</code>\n"
        "За замовчуванням: front\n\n"
        "Для скасування натисніть /cancel"
    )


@client_progress_router.message(F.text == "/cancel")
async def cmd_cancel(state: FSMContext):
    """Скасування поточної дії."""
    await state.clear()
    await message.answer("❌ Дію скасовано.")


@client_progress_router.message("waiting_measurement")
async def process_measurement(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    """Обробка введених замірів."""
    try:
        parts = message.text.strip().replace(",", ".").split()
        values = [float(p) for p in parts]
        
        weight = values[0] if len(values) > 0 else None
        chest = values[1] if len(values) > 1 else None
        waist = values[2] if len(values) > 2 else None
        hips = values[3] if len(values) > 3 else None
        arms = values[4] if len(values) > 4 else None
        
        await add_measurement(session, user_db.id, weight, chest, waist, hips, arms)
        await state.clear()
        await message.answer("✅ Заміри успішно збережено!")
        
        # Показуємо оновлений прогрес
        await cmd_my_progress(message, session, user_db)
    except ValueError:
        await message.answer("❌ Введіть коректні числа. Приклад: <code>75 100 80 95 35</code>")
    except Exception as e:
        await message.answer(f"❌ Помилка: {str(e)}")


@client_progress_router.message("waiting_progress_photo", F.photo)
async def process_progress_photo(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    """Обробка фото прогресу."""
    try:
        file_id = message.photo[-1].file_id
        view = message.caption or "front"
        view = view.strip().lower()
        if view not in ["front", "side", "back"]:
            view = "front"
        
        await add_progress_photo(session, user_db.id, file_id, view)
        await state.clear()
        await message.answer("✅ Фото прогресу збережено!")
    except Exception as e:
        await message.answer(f"❌ Помилка: {str(e)}")


@client_progress_router.message("waiting_progress_photo")
async def process_progress_photo_invalid(message: Message):
    """Обробка неправильного вводу для фото."""
    await message.answer("❌ Будь ласка, надішліть фото.")


# ====================
# ТРЕНЕР - ПРОГРЕС КЛІЄНТА
# ====================

@trainer_progress_router.callback_query(TrainerClientCB.filter(F.action == "progress"))
async def cb_client_progress(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
    """Показати прогрес клієнта для тренера."""
    try:
        client_id = callback_data.client_id
        analytics = await get_client_full_analytics(session, client_id)
        
        if not analytics:
            await callback.message.edit_text(
                "📊 Дані про прогрес клієнта ще не накопичено.",
                reply_markup=client_card_keyboard(client_id)
            )
            await callback.answer()
            return
        
        # Отримуємо останній замір
        latest = await get_latest_measurement(session, client_id)
        
        text = (
            f"📈 <b>Прогрес клієнта</b>\n\n"
            f"⚖️ <b>Вага:</b>\n"
            f"  Стартова: {analytics['weight']['start_weight'] or '?'} кг\n"
            f"  Поточна: {analytics['weight']['current_weight'] or '?'} кг\n"
            f"  Зміна: {analytics['weight']['diff_total'] or '?'} кг\n\n"
        )
        
        if latest and (latest.chest or latest.waist or latest.hips):
            text += f"📐 <b>Останні заміри:</b>\n"
            if latest.chest:
                text += f"  Груди: {latest.chest} см\n"
            if latest.waist:
                text += f"  Талія: {latest.waist} см\n"
            if latest.hips:
                text += f"  Стегна: {latest.hips} см\n"
            text += "\n"
        
        text += (
            f"🏋️ <b>Тренування:</b>\n"
            f"  Всього: {analytics['workouts']['total_count']}\n\n"
            f"🍎 <b>Харчування:</b>\n"
            f"  Днів трекінгу: {analytics['nutrition']['days_tracked']}"
        )
        
        await callback.message.edit_text(text, reply_markup=client_card_keyboard(client_id))
    except Exception as e:
        await callback.answer(f"❌ Помилка: {str(e)}", show_alert=True)
    await callback.answer()