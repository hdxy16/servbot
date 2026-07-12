import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import TrainerClientCB
from bot.keyboards.gym import TrainerGymCB, trainer_program_card_kb, trainer_templates_kb, trainer_days_kb, trainer_day_exercises_kb, search_cancel_kb
from bot.services import workout_service, exercise_service, audit_service
from bot.states.gym_fsm import WorkoutCreateFSM, ExerciseCreateFSM

logger = logging.getLogger(__name__)
trainer_gym_router = Router()
trainer_gym_router.message.filter(IsTrainer())
trainer_gym_router.callback_query.filter(IsTrainer())

@trainer_gym_router.callback_query(F.data == "cancel_fsm")
async def cb_cancel_fsm(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Дію скасовано.")
    await callback.answer()

@trainer_gym_router.callback_query(TrainerClientCB.filter(F.action == "gym"))
async def cb_client_gym_card(callback: types.CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
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
async def cb_templates(callback: types.CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession, user_db: User):
    templates = await workout_service.get_trainer_programs(session, user_db.id)
    if not templates:
        return await callback.answer("У вас ще немає створених шаблонів.", show_alert=True)
    await callback.message.edit_text(
        "📂 <b>Виберіть шаблон для клієнта:</b>\n<i>(Система створить індивідуальну копію)</i>",
        reply_markup=trainer_templates_kb(callback_data.client_id, templates)
    )

@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "assign"))
async def cb_assign_template(callback: types.CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession, user_db: User):
    await callback.message.edit_text("⏳ Створення копії програми...")
    await workout_service.assign_program(session, callback_data.client_id, callback_data.prog_id)
    await audit_service.log_action(session, user_db.id, callback_data.client_id, "assigned_workout_program")
    
    prog = await workout_service.get_client_program(session, callback_data.client_id)
    await callback.message.edit_text(
        f"✅ <b>Програму успішно призначено!</b>\nНазва: {prog.name}",
        reply_markup=trainer_program_card_kb(callback_data.client_id, True)
    )

@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "view_prog"))
async def cb_view_prog(callback: types.CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession):
    prog = await workout_service.get_client_program(session, callback_data.client_id)
    if not prog: return await callback.answer("Програми немає", show_alert=True)
    
    days = await workout_service.get_program_days(session, prog.id)
    await callback.message.edit_text(
        f"📅 <b>Програма: {prog.name}</b>\nОберіть день для редагування:",
        reply_markup=trainer_days_kb(callback_data.client_id, prog.id, days)
    )

@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "view_day"))
async def cb_view_day(callback: types.CallbackQuery, callback_data: TrainerGymCB, session: AsyncSession):
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
            
    await callback.message.edit_text(text, reply_markup=trainer_day_exercises_kb(callback_data.client_id, callback_data.day_id))

# --- ДОДАВАННЯ ВПРАВИ ДО ДНЯ (FSM) ---
@trainer_gym_router.callback_query(TrainerGymCB.filter(F.action == "add_ex"))
async def cb_add_ex(callback: types.CallbackQuery, callback_data: TrainerGymCB, state: FSMContext):
    await state.set_state(ExerciseCreateFSM.waiting_for_search)
    await state.update_data(client_id=callback_data.client_id, day_id=callback_data.day_id)
    await callback.message.edit_text("🔍 Напишіть назву вправи (напр. 'Жим'):", reply_markup=search_cancel_kb())

@trainer_gym_router.message(ExerciseCreateFSM.waiting_for_search)
async def process_ex_search(message: types.Message, state: FSMContext, session: AsyncSession):
    results = await exercise_service.search_exercise(session, message.text.strip())
    if not results:
        # Для простоти (щоб не роздувати код), якщо вправи немає — одразу створюємо її в довіднику.
        ex = await exercise_service.create_exercise(session, name=message.text.strip(), muscle_group="Інше")
        await message.answer(f"➕ Створено нову вправу в базі: {ex.name}")
        results = [ex]
        
    ex = results[0] # Беремо першу знайдену
    await state.update_data(exercise_id=ex.id, exercise_name=ex.name)
    await state.set_state(ExerciseCreateFSM.sets)
    await message.answer(f"Обрано: <b>{ex.name}</b>\nСкільки підходів? (цифра):", reply_markup=search_cancel_kb())

@trainer_gym_router.message(ExerciseCreateFSM.sets)
async def process_ex_sets(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Потрібна цифра.")
    await state.update_data(sets=int(message.text))
    await state.set_state(ExerciseCreateFSM.reps)
    await message.answer("Скільки повторень? (напр: '8-12' або 'Max'):")

@trainer_gym_router.message(ExerciseCreateFSM.reps)
async def process_ex_reps(message: types.Message, state: FSMContext):
    await state.update_data(reps=message.text.strip())
    await state.set_state(ExerciseCreateFSM.note_and_rest)
    await message.answer("Напишіть нотатку та час відпочинку (напр: 'Не відривай таз. Відпочинок 90с'):")

@trainer_gym_router.message(ExerciseCreateFSM.note_and_rest)
async def process_ex_note(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    await workout_service.add_exercise_to_day(
        session, data["day_id"], data["exercise_id"], data["sets"], data["reps"], message.text.strip()
    )
    await message.answer(f"✅ Вправу <b>{data['exercise_name']}</b> додано до дня!")
    await state.clear()