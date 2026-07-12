import datetime
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.checkin_fsm import CheckinFSM
from bot.keyboards.checkin import scale_keyboard, trainer_checkins_keyboard, checkin_answer_keyboard
from bot.filters.role_filter import IsTrainer
from database.models import CheckIn, User


client_checkin_router = Router()
trainer_checkin_router = Router()

trainer_checkin_router.message.filter(IsTrainer())
trainer_checkin_router.callback_query.filter(IsTrainer())


# ====================
# КЛІЄНТ - ЧЕКІН
# ====================

@client_checkin_router.message(F.text == "📋 Чекін")
async def start_checkin(message: Message, state: FSMContext):
    """Початок чекіну."""
    await state.set_state(CheckinFSM.sleep)
    await message.answer(
        "😴 Оціни сон від 1 до 5",
        reply_markup=scale_keyboard("sleep")
    )


@client_checkin_router.callback_query(CheckinFSM.sleep, F.data.regexp(r"^sleep:[1-5]$"))
async def save_sleep(callback: CallbackQuery, state: FSMContext):
    """Збереження оцінки сну."""
    value = int(callback.data.split(":")[1])
    await state.update_data(sleep=value)
    await state.set_state(CheckinFSM.energy)
    await callback.message.edit_text(
        "⚡ Оціни енергію (1-5)",
        reply_markup=scale_keyboard("energy")
    )
    await callback.answer()


@client_checkin_router.callback_query(CheckinFSM.energy, F.data.regexp(r"^energy:[1-5]$"))
async def save_energy(callback: CallbackQuery, state: FSMContext):
    """Збереження оцінки енергії."""
    value = int(callback.data.split(":")[1])
    await state.update_data(energy=value)
    await state.set_state(CheckinFSM.hunger)
    await callback.message.edit_text(
        "🍽 Оціни голод (1-5)",
        reply_markup=scale_keyboard("hunger")
    )
    await callback.answer()


@client_checkin_router.callback_query(CheckinFSM.hunger, F.data.regexp(r"^hunger:[1-5]$"))
async def save_hunger(callback: CallbackQuery, state: FSMContext):
    """Збереження оцінки голоду."""
    value = int(callback.data.split(":")[1])
    await state.update_data(hunger=value)
    await state.set_state(CheckinFSM.stress)
    await callback.message.edit_text(
        "😰 Оціни стрес (1-5)",
        reply_markup=scale_keyboard("stress")
    )
    await callback.answer()


@client_checkin_router.callback_query(CheckinFSM.stress, F.data.regexp(r"^stress:[1-5]$"))
async def save_stress(callback: CallbackQuery, state: FSMContext):
    """Збереження оцінки стресу."""
    value = int(callback.data.split(":")[1])
    await state.update_data(stress=value)
    await state.set_state(CheckinFSM.feeling)
    await callback.message.edit_text("📝 Напиши коротко самопочуття")
    await callback.answer()


@client_checkin_router.message(CheckinFSM.feeling)
async def finish_checkin(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user_db: User
):
    """Завершення чекіну."""
    try:
        data = await state.get_data()
        
        checkin = CheckIn(
            client_id=user_db.id,
            date=datetime.date.today(),
            sleep=data.get("sleep", 0),
            energy=data.get("energy", 0),
            hunger=data.get("hunger", 0),
            stress=data.get("stress", 0),
            feeling=message.text.strip()
        )
        
        session.add(checkin)
        await session.commit()
        await state.clear()
        
        await message.answer("✅ Чекін успішно збережено!")
    except Exception as e:
        await state.clear()
        await message.answer(f"❌ Помилка: {str(e)}")