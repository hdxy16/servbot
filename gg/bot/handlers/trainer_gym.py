import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import TrainerClientCB
from bot.keyboards.gym import (
    TrainerGymCB,
    trainer_program_card_kb,
    trainer_templates_kb,
    trainer_days_kb,
    trainer_day_exercises_kb,
    search_cancel_kb
)
from bot.services import workout_service, exercise_service, audit_service
from bot.states.gym_fsm import WorkoutCreateFSM, ExerciseCreateFSM

logger = logging.getLogger(__name__)
trainer_gym_router = Router()
trainer_gym_router.message.filter(IsTrainer())
trainer_gym_router.callback_query.filter(IsTrainer())


@trainer_gym_router.callback_query(F.data == "cancel_fsm")
async def cb_cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Дію скасовано.")
    await callback.answer()


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "new_prog"))
async def cb_new_program(callback: CallbackQuery, callback_data: TrainerGymCB, state: FSMContext):
    await state.set_state(WorkoutCreateFSM.program_name)
    await state.update_data(client_id=callback_data.client_id)
    await callback.message.edit_text(
        "Введіть назву нової програми:",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()


@trainer_gym_router.message(WorkoutCreateFSM.program_name)
async def process_program_name(message: Message, state: FSMContext):
    await state.update_data(program_name=message.text.strip())
    await state.set_state(WorkoutCreateFSM.description)
    await message.answer(
        "Введіть опис програми (або надішліть '-' для пропуску):",
        reply_markup=search_cancel_kb()
    )


@trainer_gym_router.message(WorkoutCreateFSM.description)
async def process_program_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(WorkoutCreateFSM.days_count)
    await message.answer(
        "Скільки днів буде в програмі? (наприклад, 3):",
        reply_markup=search_cancel_kb()
    )


@trainer_gym_router.message(WorkoutCreateFSM.days_count)
async def process_days_count(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    if not message.text.isdigit():
        return await message.answer("Введіть число.")
    days = int(message.text)
    data = await state.get_data()
    
    program = await workout_service.create_program(
        session, user_db.id, data["program_name"], data["description"]
    )
    for i in range(1, days+1):
        await workout_service.create_day(session, program.id, f"День {i}", i)
    
    await audit_service.log_action(session, user_db.id, data["client_id"], "created_workout_program", details={"program_id": program.id})
    await state.clear()
    
    await workout_service.assign_program(session, data["client_id"], program.id)
    
    await message.answer(
        f"✅ Програму <b>{program.name}</b> створено та призначено клієнту!",
        reply_markup=trainer_program_card_kb(data["client_id"], True)
    )


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "del_prog"))
async def cb_delete_program(callback: CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession, user_db: User):
    client_id = callback_data.client_id
    prog = await workout_service.get_client_program(session, client_id)
    if not prog:
        return await callback.answer("Програми немає.", show_alert=True)
    
    from database.models import AssignedProgram
    stmt = select(AssignedProgram).where(AssignedProgram.user_id == client_id)
    result = await session.execute(stmt)
    assigned = result.scalar_one_or_none()
    if assigned:
        await session.delete(assigned)
        await session.commit()
    
    await audit_service.log_action(session, user_db.id, client_id, "deleted_workout_program")
    await callback.message.edit_text(
        "🗑 Програму відкріплено від клієнта.",
        reply_markup=trainer_program_card_kb(client_id, False)
    )
    await callback.answer()


@trainer_gym_router.callback_query(TrainerClientCB.filter(F.action == "gym"))
async def cb_client_gym_card(callback: CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
    client_id = callback_data.client_id
    prog = await workout_service.get_client_program(session, client_id)
    
    if not prog:
        text = "🏋️ <b>Тренування клієнта</b>\n\nПрограму ще не призначено."
    else:
        text = (
            f"🏋️ <b>Поточна програма:</b>\n"
            f"Назва: <b>{prog.name}</b>\n"
            f"Опис: <i>{prog.description or '-'}</i>"
        )
        
    await callback.message.edit_text(text, reply_markup=trainer_program_card_kb(client_id, bool(prog)))
    await callback.answer()


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "templates"))
async def cb_templates(callback: CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession, user_db: User):
    templates = await workout_service.get_trainer_programs(session, user_db.id)
    if not templates:
        return await callback.answer("У вас ще немає створених шаблонів.", show_alert=True)
    await callback.message.edit_text(
        "📂 <b>Виберіть шаблон для клієнта:</b>\n<i>(Система створить індивідуальну копію)</i>",
        reply_markup=trainer_templates_kb(callback_data.client_id, templates)
    )


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "assign"))
async def cb_assign_template(callback: CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession, user_db: User):
    await callback.message.edit_text("⏳ Створення копії програми...")
    try:
        await workout_service.assign_program(session, callback_data.client_id, callback_data.prog_id)
        await audit_service.log_action(session, user_db.id, callback_data.client_id, "assigned_workout_program")
        prog = await workout_service.get_client_program(session, callback_data.client_id)
        await callback.message.edit_text(
            f"✅ <b>Програму успішно призначено!</b>\nНазва: {prog.name}",
            reply_markup=trainer_program_card_kb(callback_data.client_id, True)
        )
    except Exception as e:
        logger.error(f"Error assigning program: {e}")
        await callback.answer("❌ Помилка призначення програми.", show_alert=True)
    await callback.answer()


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "view_prog"))
async def cb_view_prog(callback: CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession):
    prog = await workout_service.get_client_program(session, callback_data.client_id)
    if not prog:
        return await callback.answer("Програми немає", show_alert=True)
    
    days = await workout_service.get_program_days(session, prog.id)
    await callback.message.edit_text(
        f"📅 <b>Програма: {prog.name}</b>\nОберіть день для редагування:",
        reply_markup=trainer_days_kb(callback_data.client_id, prog.id, days)
    )
    await callback.answer()


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "view_day"))
async def cb_view_day(callback: CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession):
    exercises = await workout_service.get_day_exercises(session, callback_data.day_id)
    text = f"🏋️ <b>Вправи дня:</b>\n\n"
    
    if not exercises:
        text += "<i>Поки немає жодної вправи.</i>"
    else:
        for i, (we, ex) in enumerate(exercises, 1):
            text += f"{i}. <b>{ex.name}</b>\n  ▫️ {we.target_sets} підходів × {we.target_reps}\n"
            if we.trainer_note:
                text += f"  📝 <i>{we.trainer_note}</i>\n"
            text += "\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=trainer_day_exercises_kb(callback_data.client_id, callback_data.day_id)
    )
    await callback.answer()


@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "add_ex"))
async def cb_add_ex(callback: CallbackQuery, callback_data: TrainerGymCB, state: FSMContext):
    await state.set_state(ExerciseCreateFSM.waiting_for_search)
    await state.update_data(client_id=callback_data.client_id, day_id=callback_data.day_id)
    await callback.message.edit_text(
        "🔍 Напишіть назву вправи (напр. 'Жим'):",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()


@trainer_gym_router.message(ExerciseCreateFSM.waiting_for_search)
async def process_ex_search(message: Message, state: FSMContext, session: AsyncSession):
    try:
        results = await exercise_service.search_exercise(session, message.text.strip())
        if not results:
            ex = await exercise_service.create_exercise(
                session,
                name=message.text.strip(),
                muscle_group="Інше"
            )
            await message.answer(f"➕ Створено нову вправу в базі: {ex.name}")
            results = [ex]
        
        ex = results[0]
        await state.update_data(exercise_id=ex.id, exercise_name=ex.name)
        await state.set_state(ExerciseCreateFSM.sets)
        await message.answer(
            f"Обрано: <b>{ex.name}</b>\nСкільки підходів? (цифра):",
            reply_markup=search_cancel_kb()
        )
    except Exception as e:
        logger.error(f"Error searching exercise: {e}")
        await message.answer("❌ Помилка пошуку вправи.")


@trainer_gym_router.message(ExerciseCreateFSM.sets)
async def process_ex_sets(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Потрібна цифра.")
    await state.update_data(sets=int(message.text))
    await state.set_state(ExerciseCreateFSM.reps)
    await message.answer(
        "Скільки повторень? (напр: '8-12' або 'Max'):",
        reply_markup=search_cancel_kb()
    )


@trainer_gym_router.message(ExerciseCreateFSM.reps)
async def process_ex_reps(message: Message, state: FSMContext):
    await state.update_data(reps=message.text.strip())
    await state.set_state(ExerciseCreateFSM.note_and_rest)
    await message.answer(
        "Напишіть нотатку та час відпочинку (напр: 'Не відривай таз. Відпочинок 90с'):",
        reply_markup=search_cancel_kb()
    )


@trainer_gym_router.message(ExerciseCreateFSM.note_and_rest)
async def process_ex_note(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    try:
        await workout_service.add_exercise_to_day(
            session,
            data["day_id"],
            data["exercise_id"],
            data["sets"],
            data["reps"],
            message.text.strip()
        )
        await message.answer(f"✅ Вправу <b>{data['exercise_name']}</b> додано до дня!")
        await state.clear()
    except Exception as e:
        logger.error(f"Error adding exercise: {e}")
        await message.answer("❌ Помилка додавання вправи.")