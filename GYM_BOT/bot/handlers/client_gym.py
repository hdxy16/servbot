import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsClient
from database.models import User
from bot.keyboards.gym import ClientGymCB, client_gym_main_kb, client_pick_day_kb, client_workout_kb, client_execute_ex_kb, search_cancel_kb
from bot.services import workout_service
from bot.states.gym_fsm import WorkoutExecutionFSM

logger = logging.getLogger(__name__)
client_gym_router = Router()
client_gym_router.message.filter(IsClient())
client_gym_router.callback_query.filter(IsClient())

@client_gym_router.message(F.text == "🏋️ Моє тренування")
async def cmd_my_workout(message: types.Message, session: AsyncSession, user_db: User):
    prog = await workout_service.get_client_program(session, user_db.id)
    if not prog:
        return await message.answer("Тренер ще не призначив вам програму тренувань.")
        
    active_session = await workout_service.get_active_session(session, user_db.id)
    text = f"🏋️ <b>Ваша програма: {prog.name}</b>\n\n"
    if active_session:
        text += f"У вас є незавершене тренування: <b>{active_session.day_name}</b>"
    else:
        text += "Готові почати тренування?"
        
    await message.answer(text, reply_markup=client_gym_main_kb(active_session.id if active_session else 0))

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "main"))
async def cb_gym_main(callback: types.CallbackQuery, session: AsyncSession, user_db: User, state: FSMContext):
    await state.clear()
    active = await workout_service.get_active_session(session, user_db.id)
    await callback.message.edit_text("🏋️ Меню тренувань:", reply_markup=client_gym_main_kb(active.id if active else 0))

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "pick_day"))
async def cb_pick_day(callback: types.CallbackQuery, session: AsyncSession, user_db: User):
    prog = await workout_service.get_client_program(session, user_db.id)
    days = await workout_service.get_program_days(session, prog.id)
    await callback.message.edit_text("📅 <b>Оберіть день для початку:</b>", reply_markup=client_pick_day_kb(days))

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "start_day"))
async def cb_start_day(callback: types.CallbackQuery, callback_data: ClientGymCB, session: AsyncSession, user_db: User):
    # Отримуємо назву дня (в реальності краще зробити окремий запит, але для швидкості витягнемо з програми)
    prog = await workout_service.get_client_program(session, user_db.id)
    days = await workout_service.get_program_days(session, prog.id)
    day_name = next((d.name for d in days if d.id == callback_data.day_id), "Тренування")
    
    ws = await workout_service.start_workout(session, user_db.id, callback_data.day_id, day_name)
    await render_workout_process(callback.message, session, ws.id, callback_data.day_id)
    await callback.answer("Тренування почалось! 💪")

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "resume"))
async def cb_resume(callback: types.CallbackQuery, callback_data: ClientGymCB, session: AsyncSession):
    ws = await session.get(workout_service.WorkoutSession, callback_data.sess_id)
    await render_workout_process(callback.message, session, ws.id, ws.workout_day_id)
    await callback.answer()

async def render_workout_process(message: types.Message, session: AsyncSession, sess_id: int, day_id: int):
    exercises = await workout_service.get_day_exercises(session, day_id)
    status_list = []
    
    for we, ex in exercises:
        done_sets = await workout_service.get_done_sets(session, sess_id, we.id)
        is_done = len(done_sets) >= we.target_sets
        status_list.append((we.id, ex.name, is_done))
        
    await message.edit_text("🏃 <b>Процес тренування:</b>\nОберіть вправу:", reply_markup=client_workout_kb(sess_id, status_list))

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "do_ex"))
async def cb_do_ex(callback: types.CallbackQuery, callback_data: ClientGymCB, session: AsyncSession, user_db: User):
    we_id = callback_data.we_id
    sess_id = callback_data.sess_id
    
    # Отримуємо дані
    stmt = workout_service.select(workout_service.WorkoutExercise, workout_service.Exercise).join(workout_service.Exercise).where(workout_service.WorkoutExercise.id == we_id)
    we, ex = (await session.execute(stmt)).first()
    
    done_sets = await workout_service.get_done_sets(session, sess_id, we_id)
    history = await workout_service.get_exercise_history(session, user_db.id, ex.id, limit=3)
    
    text = (
        f"💪 <b>{ex.name}</b>\n"
        f"Ціль: {we.target_sets} підходів × {we.target_reps}\n"
    )
    if we.trainer_note:
        text += f"📝 <i>Від тренера: {we.trainer_note}</i>\n\n"
        
    if history:
        text += "🔙 <b>Минулого разу:</b>\n"
        for h in history:
            text += f"▫️ {h.weight} кг × {h.reps} (RPE {h.rpe or '-'})\n"
        text += "\n"
        
    text += "⏱ <b>Сьогодні зроблено:</b>\n"
    if not done_sets:
        text += "<i>Ще немає підходів.</i>\n"
    else:
        for s in done_sets:
            text += f"Підхід {s.set_number}: {s.weight} кг × {s.reps}\n"
            
    await callback.message.edit_text(text, reply_markup=client_execute_ex_kb(sess_id, we_id))

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "log_set"))
async def cb_log_set(callback: types.CallbackQuery, callback_data: ClientGymCB, state: FSMContext):
    await state.set_state(WorkoutExecutionFSM.weight_reps_rpe)
    await state.update_data(sess_id=callback_data.sess_id, we_id=callback_data.we_id)
    await callback.message.edit_text(
        "Введіть результат підходу через пробіл:\n"
        "<code>ВАГА ПОВТОРИ RPE</code>\n"
        "Наприклад: <code>80 8 8</code> (80 кг, 8 повторень, RPE 8)",
        reply_markup=search_cancel_kb()
    )

@client_gym_router.message(WorkoutExecutionFSM.weight_reps_rpe)
async def process_log_set(message: types.Message, state: FSMContext, session: AsyncSession):
    parts = message.text.strip().replace(",", ".").split()
    if len(parts) < 2:
        return await message.answer("❌ Формат: ВАГА ПОВТОРИ [RPE]. Спробуйте ще раз.")
        
    try:
        weight = float(parts[0])
        reps = int(parts[1])
        rpe = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        return await message.answer("❌ Введіть числа коректно.")
        
    data = await state.get_data()
    await workout_service.save_set(session, data["sess_id"], data["we_id"], weight, reps, rpe)
    
    await message.answer("✅ Підхід записано!")
    await state.clear()
    
    # Емулюємо натискання кнопки повернення до вправи
    fake_cb = types.CallbackQuery(id="0", from_user=message.from_user, chat_instance="", message=message, data="")
    await cb_do_ex(fake_cb, ClientGymCB(action="do_ex", sess_id=data["sess_id"], we_id=data["we_id"]), session, message.from_user) # type: ignore

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "finish"))
async def cb_finish_workout(callback: types.CallbackQuery, callback_data: ClientGymCB, session: AsyncSession):
    await workout_service.finish_workout(session, callback_data.sess_id)
    await callback.message.edit_text("🏆 <b>Тренування успішно завершено!</b>\nВідмінна робота! Відпочивайте.")
    await callback.answer()