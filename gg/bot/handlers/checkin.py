import datetime
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.checkin_fsm import CheckinFSM
from bot.keyboards.checkin import scale_keyboard, trainer_checkins_keyboard, checkin_answer_keyboard
from bot.filters.role_filter import IsTrainer
from database.models import CheckIn, User, TrainerClient


client_checkin_router = Router()
trainer_checkin_router = Router()

trainer_checkin_router.message.filter(IsTrainer())
trainer_checkin_router.callback_query.filter(IsTrainer())


# ====================
# КЛІЄНТ - ЧЕКІН
# ====================

@client_checkin_router.message(F.text == "📋 Чекін")
async def start_checkin(message: Message, state: FSMContext):
    await state.set_state(CheckinFSM.sleep)
    await message.answer(
        "😴 Оціни сон від 1 до 5",
        reply_markup=scale_keyboard("sleep")
    )


@client_checkin_router.callback_query(StateFilter(CheckinFSM.sleep), F.data.regexp(r"^sleep:[1-5]$"))
async def save_sleep(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split(":")[1])
    await state.update_data(sleep=value)
    await state.set_state(CheckinFSM.energy)
    await callback.message.edit_text(
        "⚡ Оціни енергію (1-5)",
        reply_markup=scale_keyboard("energy")
    )
    await callback.answer()


@client_checkin_router.callback_query(StateFilter(CheckinFSM.energy), F.data.regexp(r"^energy:[1-5]$"))
async def save_energy(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split(":")[1])
    await state.update_data(energy=value)
    await state.set_state(CheckinFSM.hunger)
    await callback.message.edit_text(
        "🍽 Оціни голод (1-5)",
        reply_markup=scale_keyboard("hunger")
    )
    await callback.answer()


@client_checkin_router.callback_query(StateFilter(CheckinFSM.hunger), F.data.regexp(r"^hunger:[1-5]$"))
async def save_hunger(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split(":")[1])
    await state.update_data(hunger=value)
    await state.set_state(CheckinFSM.stress)
    await callback.message.edit_text(
        "😰 Оціни стрес (1-5)",
        reply_markup=scale_keyboard("stress")
    )
    await callback.answer()


@client_checkin_router.callback_query(StateFilter(CheckinFSM.stress), F.data.regexp(r"^stress:[1-5]$"))
async def save_stress(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split(":")[1])
    await state.update_data(stress=value)
    await state.set_state(CheckinFSM.feeling)
    await callback.message.edit_text("📝 Напиши коротко самопочуття")
    await callback.answer()


@client_checkin_router.message(StateFilter(CheckinFSM.feeling))
async def finish_checkin(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user_db: User
):
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


# ====================
# ТРЕНЕР - ПЕРЕГЛЯД ЧЕКІНІВ
# ====================

@trainer_checkin_router.message(F.text == "📋 Чекіни клієнтів")
async def trainer_checkins_list(message: Message, session: AsyncSession, user_db: User):
    stmt = (
        select(User)
        .join(TrainerClient, TrainerClient.client_id == User.id)
        .where(TrainerClient.trainer_id == user_db.id)
    )
    result = await session.execute(stmt)
    clients = result.scalars().all()
    
    if not clients:
        await message.answer("У вас немає клієнтів.")
        return
    
    await message.answer(
        "👥 Оберіть клієнта для перегляду чекінів:",
        reply_markup=trainer_checkins_keyboard(clients)
    )


@trainer_checkin_router.callback_query(F.data.startswith("trainer_checkin:"))
async def show_client_checkins(callback: CallbackQuery, session: AsyncSession):
    client_id = int(callback.data.split(":")[1])
    stmt = (
        select(CheckIn)
        .where(CheckIn.client_id == client_id)
        .order_by(desc(CheckIn.date))
        .limit(10)
    )
    result = await session.execute(stmt)
    checkins = result.scalars().all()
    
    if not checkins:
        await callback.message.edit_text("Цей клієнт ще не заповнював чекіни.")
        return
    
    text = f"📋 <b>Останні чекіни клієнта</b>\n\n"
    for c in checkins:
        text += (
            f"📅 {c.date.strftime('%d.%m.%Y')}\n"
            f"😴 Сон: {c.sleep} | ⚡ Енергія: {c.energy} | 🍽 Голод: {c.hunger} | 😰 Стрес: {c.stress}\n"
            f"📝 {c.feeling or 'Без коментаря'}\n"
            f"💬 Відповідь тренера: {c.trainer_feedback or 'Немає'}\n\n"
        )
    
    if checkins:
        last_checkin = checkins[0]
        await callback.message.edit_text(
            text,
            reply_markup=checkin_answer_keyboard(last_checkin.id)
        )
    else:
        await callback.message.edit_text(text)
    await callback.answer()


@trainer_checkin_router.callback_query(F.data.startswith("reply_checkin:"))
async def reply_to_checkin(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    checkin_id = int(callback.data.split(":")[1])
    await state.update_data(checkin_id=checkin_id)
    await state.set_state("trainer_checkin_reply")
    await callback.message.edit_text("✏️ Напишіть відповідь на чекін у чат.")


@trainer_checkin_router.message(StateFilter("trainer_checkin_reply"))
async def process_checkin_reply(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    checkin_id = data["checkin_id"]
    reply_text = message.text.strip()
    
    checkin = await session.get(CheckIn, checkin_id)
    if checkin:
        checkin.trainer_feedback = reply_text
        await session.commit()
        await message.answer("✅ Відповідь збережено!")
    else:
        await message.answer("❌ Чекін не знайдено.")
    
    await state.clear()