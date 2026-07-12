from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.checkin_fsm import CheckinFSM
from bot.keyboards.checkin import scale_keyboard

from database.models import CheckInLog, User

import datetime
from sqlalchemy import select, desc, func

from bot.filters.role_filter import IsTrainer
from bot.keyboards.checkin import (
    trainer_checkins_keyboard,
    checkin_answer_keyboard
)

from database.models import (
    User,
    CheckInLog
)


client_checkin_router = Router()
trainer_checkin_router = Router()

trainer_checkin_router.message.filter(IsTrainer())
trainer_checkin_router.callback_query.filter(IsTrainer())


@client_checkin_router.message(
    F.text=="📋 Чекін"
)
async def start_checkin(
    message:types.Message,
    state:FSMContext
):

    await state.set_state(
        CheckinFSM.sleep
    )


    await message.answer(
        "😴 Оціни сон від 1 до 5",
        reply_markup=scale_keyboard("sleep")
    )



@client_checkin_router.callback_query(
    F.data.startswith("sleep:")
)
async def save_sleep(
    callback:types.CallbackQuery,
    state:FSMContext
):

    value=int(
        callback.data.split(":")[1]
    )

    await state.update_data(
        sleep=value
    )


    await state.set_state(
        CheckinFSM.energy
    )


    await callback.message.edit_text(
        "⚡ Оціни енергію",
        reply_markup=scale_keyboard("energy")
    )



@client_checkin_router.callback_query(
    F.data.startswith("energy:")
)
async def save_energy(
    callback,
    state:FSMContext
):

    value=int(
        callback.data.split(":")[1]
    )


    await state.update_data(
        energy=value
    )


    await state.set_state(
        CheckinFSM.hunger
    )


    await callback.message.edit_text(
        "🍽 Оціни голод",
        reply_markup=scale_keyboard("hunger")
    )



@client_checkin_router.callback_query(
    F.data.startswith("hunger:")
)
async def save_hunger(
    callback,
    state:FSMContext
):

    value=int(
        callback.data.split(":")[1]
    )


    await state.update_data(
        hunger=value
    )


    await state.set_state(
        CheckinFSM.stress
    )


    await callback.message.edit_text(
        "😰 Оціни стрес",
        reply_markup=scale_keyboard("stress")
    )



@client_checkin_router.callback_query(
    F.data.startswith("stress:")
)
async def save_stress(
    callback,
    state:FSMContext
):

    value=int(
        callback.data.split(":")[1]
    )


    await state.update_data(
        stress=value
    )


    await state.set_state(
        CheckinFSM.feeling
    )


    await callback.message.answer(
        "📝 Напиши коротко самопочуття"
    )



@client_checkin_router.message(
    CheckinFSM.feeling
)
async def finish_checkin(
    message:types.Message,
    state:FSMContext,
    session:AsyncSession,
    user_db:User
):

    data=await state.get_data()


    checkin=CheckInLog(

        user_id=user_db.id,

        date=datetime.date.today(),

        sleep=data["sleep"],

        energy=data["energy"],

        hunger=data["hunger"],

        stress=data["stress"],

        feeling=message.text

    )


    session.add(checkin)

    await session.commit()


    await state.clear()


    await message.answer(
        "✅ Чекін успішно збережено!"
    )