import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsClient
from database.models import User, WorkoutExercise, Exercise, WorkoutSession
from bot.keyboards.gym import (
    ClientGymCB,
    client_gym_main_kb,
    client_pick_day_kb,
    client_workout_kb,
    client_execute_ex_kb,
    search_cancel_kb
)
from bot.services import workout_service
from bot.states.gym_fsm import WorkoutExecutionFSM

logger = logging.getLogger(__name__)
client_gym_router = Router()
client_gym_router.message.filter(IsClient())
client_gym_router.callback_query.filter(IsClient())


# ==========================================
# ГОЛОВНЕ МЕНЮ ТРЕНУВАНЬ
# ==========================================

@client_gym_router.message(F.text == "🏋️ Моє тренування")
async def cmd_my_workout(message: Message, session: AsyncSession, user_db: User):
    try:
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
    except Exception as e:
        logger.error(f"Error getting workout: {e}")
        await message.answer("❌ Помилка завантаження тренування.")


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "main"))
async def cb_gym_main(callback: CallbackQuery, session: AsyncSession, user_db: User, state: FSMContext):
    await state.clear()
    try:
        active = await workout_service.get_active_session(session, user_db.id)
        await callback.message.edit_text(
            "🏋️ Меню тренувань:",
            reply_markup=client_gym_main_kb(active.id if active else 0)
        )
    except Exception as e:
        logger.error(f"Error gym main: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


# ==========================================
# ВИБІР ДНЯ
# ==========================================

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "pick_day"))
async def cb_pick_day(callback: CallbackQuery, session: AsyncSession, user_db: User):
    try:
        prog = await workout_service.get_client_program(session, user_db.id)
        if not prog:
            return await callback.answer("Програму не знайдено.", show_alert=True)
        
        days = await workout_service.get_program_days(session, prog.id)
        await callback.message.edit_text(
            "📅 <b>Оберіть день для початку:</b>",
            reply_markup=client_pick_day_kb(days)
        )
    except Exception as e:
        logger.error(f"Error picking day: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "start_day"))
async def cb_start_day(callback: CallbackQuery, callback_data: ClientGymCB, session: AsyncSession, user_db: User):
    try:
        prog = await workout_service.get_client_program(session, user_db.id)
        if not prog:
            return await callback.answer("Програму не знайдено.", show_alert=True)
        
        days = await workout_service.get_program_days(session, prog.id)
        day_name = next((d.name for d in days if d.id == callback_data.day_id), "Тренування")
        
        ws = await workout_service.start_workout(session, user_db.id, callback_data.day_id, day_name)
        await render_workout_process(callback.message, session, ws.id, callback_data.day_id)
        await callback.answer("Тренування почалось! 💪")
    except Exception as e:
        logger.error(f"Error starting workout: {e}")
        await callback.answer("❌ Помилка початку тренування.", show_alert=True)


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "resume"))
async def cb_resume(callback: CallbackQuery, callback_data: ClientGymCB, session: AsyncSession):
    try:
        ws = await session.get(WorkoutSession, callback_data.sess_id)
        if not ws:
            return await callback.answer("Тренування не знайдено.", show_alert=True)
        await render_workout_process(callback.message, session, ws.id, ws.workout_day_id)
    except Exception as e:
        logger.error(f"Error resuming workout: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


# ==========================================
# ПРОЦЕС ТРЕНУВАННЯ
# ==========================================

async def render_workout_process(message: Message, session: AsyncSession, sess_id: int, day_id: int):
    """Відображає процес виконання тренування."""
    try:
        exercises = await workout_service.get_day_exercises(session, day_id)
        status_list = []
        
        for we, ex in exercises:
            done_sets = await workout_service.get_done_sets(session, sess_id, we.id)
            is_done = len(done_sets) >= we.target_sets
            status_list.append((we.id, ex.name, is_done))
        
        await message.edit_text(
            "🏃 <b>Процес тренування:</b>\nОберіть вправу:",
            reply_markup=client_workout_kb(sess_id, status_list)
        )
    except Exception as e:
        logger.error(f"Error rendering workout: {e}")
        await message.edit_text("❌ Помилка завантаження тренування.")


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "do_ex"))
async def cb_do_ex(callback: CallbackQuery, callback_data: ClientGymCB, session: AsyncSession, user_db: User):
    try:
        we_id = callback_data.we_id
        sess_id = callback_data.sess_id
        
        # Отримуємо дані про вправу
        stmt = (
            select(WorkoutExercise, Exercise)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .where(WorkoutExercise.id == we_id)
        )
        result = (await session.execute(stmt)).first()
        
        if not result:
            return await callback.answer("Вправу не знайдено.", show_alert=True)
        
        we, ex = result
        
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
    except Exception as e:
        logger.error(f"Error showing exercise: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


# ==========================================
# ЗАПИС ПІДХОДУ
# ==========================================

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "log_set"))
async def cb_log_set(callback: CallbackQuery, callback_data: ClientGymCB, state: FSMContext):
    await state.set_state(WorkoutExecutionFSM.weight_reps_rpe)
    await state.update_data(sess_id=callback_data.sess_id, we_id=callback_data.we_id)
    await callback.message.edit_text(
        "Введіть результат підходу через пробіл:\n"
        "<code>ВАГА ПОВТОРИ RPE</code>\n"
        "Наприклад: <code>80 8 8</code> (80 кг, 8 повторень, RPE 8)",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()


@client_gym_router.message(WorkoutExecutionFSM.weight_reps_rpe)
async def process_log_set(message: Message, state: FSMContext, session: AsyncSession):
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
    
    try:
        await workout_service.save_set(session, data["sess_id"], data["we_id"], weight, reps, rpe)
        await message.answer("✅ Підхід записано!")
        await state.clear()
        
        # Повертаємося до вправи
        await render_workout_process(message, session, data["sess_id"], 0)  # day_id буде отримано з сесії
    except Exception as e:
        logger.error(f"Error saving set: {e}")
        await message.answer("❌ Помилка збереження підходу.")


# ==========================================
# ЗАВЕРШЕННЯ ТРЕНУВАННЯ
# ==========================================

@client_gym_router.callback_query(ClientGymCB.filter(F.action == "finish"))
async def cb_finish_workout(callback: CallbackQuery, callback_data: ClientGymCB, session: AsyncSession):
    try:
        await workout_service.finish_workout(session, callback_data.sess_id)
        await callback.message.edit_text(
            "🏆 <b>Тренування успішно завершено!</b>\nВідмінна робота! Відпочивайте."
        )
    except Exception as e:
        logger.error(f"Error finishing workout: {e}")
        await callback.answer("❌ Помилка завершення тренування.", show_alert=True)
    await callback.answer()