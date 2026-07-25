import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsClient
from database.models import User, WorkoutProgram, WorkoutDay, WorkoutExercise, Exercise, WorkoutSession, WorkoutSet, AssignedProgram
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


@client_gym_router.message(F.text == "🏋️ Моє тренування")
async def cmd_my_workout(message: Message, session: AsyncSession, user_db: User):
    try:
        # Отримуємо програму клієнта
        stmt = select(AssignedProgram).where(AssignedProgram.user_id == user_db.id)
        assigned = (await session.execute(stmt)).scalar_one_or_none()
        
        if not assigned:
            return await message.answer("Тренер ще не призначив вам програму тренувань.")
        
        prog_id = assigned.program_data.get("cloned_program_id")
        if not prog_id:
            return await message.answer("Помилка: програму не знайдено.")
        
        prog = await session.get(WorkoutProgram, prog_id)
        if not prog:
            return await message.answer("Програму не знайдено.")
        
        # Шукаємо активну сесію
        stmt = select(WorkoutSession).where(
            WorkoutSession.client_id == user_db.id,
            WorkoutSession.completed == False
        ).order_by(WorkoutSession.date.desc())
        active_session = (await session.execute(stmt)).scalar_one_or_none()
        
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
        stmt = select(WorkoutSession).where(
            WorkoutSession.client_id == user_db.id,
            WorkoutSession.completed == False
        ).order_by(WorkoutSession.date.desc())
        active = (await session.execute(stmt)).scalar_one_or_none()
        
        await callback.message.edit_text(
            "🏋️ Меню тренувань:",
            reply_markup=client_gym_main_kb(active.id if active else 0)
        )
    except Exception as e:
        logger.error(f"Error gym main: {e}")
        await callback.answer("❌ Помилка.", show_alert=True)
    await callback.answer()


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "pick_day"))
async def cb_pick_day(callback: CallbackQuery, session: AsyncSession, user_db: User):
    try:
        stmt = select(AssignedProgram).where(AssignedProgram.user_id == user_db.id)
        assigned = (await session.execute(stmt)).scalar_one_or_none()
        
        if not assigned:
            return await callback.answer("Програму не знайдено.", show_alert=True)
        
        prog_id = assigned.program_data.get("cloned_program_id")
        if not prog_id:
            return await callback.answer("Помилка програми.", show_alert=True)
        
        stmt = select(WorkoutDay).where(WorkoutDay.program_id == prog_id).order_by(WorkoutDay.order)
        days = (await session.execute(stmt)).scalars().all()
        
        if not days:
            return await callback.answer("У програмі немає днів.", show_alert=True)
        
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
        day = await session.get(WorkoutDay, callback_data.day_id)
        if not day:
            return await callback.answer("День не знайдено.", show_alert=True)
        
        # Створюємо сесію
        ws = WorkoutSession(
            client_id=user_db.id,
            workout_day_id=day.id,
            day_name=day.name
        )
        session.add(ws)
        await session.commit()
        await session.refresh(ws)
        
        await render_workout_process(callback.message, session, ws.id, day.id)
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


async def render_workout_process(message: Message, session: AsyncSession, sess_id: int, day_id: int):
    try:
        # Отримуємо вправи дня
        stmt = (
            select(WorkoutExercise, Exercise)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .where(WorkoutExercise.workout_day_id == day_id)
            .order_by(WorkoutExercise.id)
        )
        exercises = (await session.execute(stmt)).all()
        
        if not exercises:
            await message.edit_text("❌ У цьому дні немає вправ.")
            return
        
        status_list = []
        for we, ex in exercises:
            stmt = select(WorkoutSet).where(
                WorkoutSet.session_id == sess_id,
                WorkoutSet.workout_exercise_id == we.id
            ).order_by(WorkoutSet.set_number)
            done_sets = (await session.execute(stmt)).scalars().all()
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
        
        # Отримуємо виконані підходи
        stmt = select(WorkoutSet).where(
            WorkoutSet.session_id == sess_id,
            WorkoutSet.workout_exercise_id == we_id
        ).order_by(WorkoutSet.set_number)
        done_sets = (await session.execute(stmt)).scalars().all()
        
        # Отримуємо історію
        stmt = (
            select(WorkoutSet)
            .join(WorkoutSession, WorkoutSession.id == WorkoutSet.session_id)
            .where(
                WorkoutSession.client_id == user_db.id,
                WorkoutSet.workout_exercise_id == we_id,
                WorkoutSession.completed == True
            )
            .order_by(WorkoutSession.date.desc(), WorkoutSet.set_number)
            .limit(3)
        )
        history = (await session.execute(stmt)).scalars().all()
        
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
    sess_id = data["sess_id"]
    we_id = data["we_id"]
    
    try:
        # Отримуємо номер підходу
        stmt = select(WorkoutSet).where(
            WorkoutSet.session_id == sess_id,
            WorkoutSet.workout_exercise_id == we_id
        ).order_by(WorkoutSet.set_number)
        done_sets = (await session.execute(stmt)).scalars().all()
        set_num = len(done_sets) + 1
        
        w_set = WorkoutSet(
            session_id=sess_id,
            workout_exercise_id=we_id,
            weight=weight,
            reps=reps,
            set_number=set_num,
            rpe=rpe
        )
        session.add(w_set)
        await session.commit()
        
        await message.answer("✅ Підхід записано!")
        await state.clear()
        
        # Повертаємося до вправи
        # Отримуємо дані сесії
        ws = await session.get(WorkoutSession, sess_id)
        if ws:
            await render_workout_process(message, session, sess_id, ws.workout_day_id)
    except Exception as e:
        logger.error(f"Error saving set: {e}")
        await message.answer("❌ Помилка збереження підходу.")


@client_gym_router.callback_query(ClientGymCB.filter(F.action == "finish"))
async def cb_finish_workout(callback: CallbackQuery, callback_data: ClientGymCB, session: AsyncSession):
    try:
        ws = await session.get(WorkoutSession, callback_data.sess_id)
        if ws:
            ws.completed = True
            await session.commit()
            await callback.message.edit_text(
                "🏆 <b>Тренування успішно завершено!</b>\nВідмінна робота! Відпочивайте."
            )
        else:
            await callback.message.edit_text("❌ Тренування не знайдено.")
    except Exception as e:
        logger.error(f"Error finishing workout: {e}")
        await callback.answer("❌ Помилка завершення тренування.", show_alert=True)
    await callback.answer()