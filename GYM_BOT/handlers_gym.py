import logging
import html
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, desc, and_, delete, or_

from config import ADMIN_IDS
from database import (
    AsyncSessionLocal, User, Exercise, WorkoutPlan, PlanExercise,
    AssignedPlan, WorkoutSession, WorkoutSet
)
from keyboards import (
    gym_plans_keyboard, gym_workout_keyboard, gym_set_input_keyboard,
    gym_confirm_finish_keyboard, trainer_gym_manage_keyboard,
    gym_exercise_catalog_keyboard, gym_templates_keyboard,
    gym_client_selection_keyboard, gym_exercise_list_keyboard,
    gym_exercise_detail_keyboard, gym_edit_exercise_keyboard
)
from handlers_client import is_trainer

logger = logging.getLogger(__name__)
router = Router()

# ==================== FSM ====================
class WorkoutFSM(StatesGroup):
    selecting_plan = State()
    viewing_exercises = State()
    exercise_detail = State()
    entering_set = State()
    finishing = State()

class TrainerGymFSM(StatesGroup):
    creating_exercise = State()
    creating_plan = State()
    adding_exercise = State()
    editing_plan = State()
    editing_exercise = State()
    assigning_plan = State()
    adding_exercise_to_plan = State()
    setting_exercise_params = State()
    bulk_create_exercises = State()
    copy_plan_to_client = State()
    editing_plan_exercise = State()
    editing_exercise_name = State()

# ==================== ДОПОМІЖНІ ФУНКЦІЇ ====================

async def get_user_by_telegram_id(telegram_id: int):
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()

async def get_active_plans(client_id: int):
    async with AsyncSessionLocal() as session:
        assigned = (await session.execute(select(AssignedPlan).where(AssignedPlan.client_id == client_id, AssignedPlan.is_active == True))).scalars().all()
        plans = []
        today = datetime.now().strftime("%Y-%m-%d")
        for a in assigned:
            plan = await session.get(WorkoutPlan, a.plan_id)
            if plan:
                session_today = (await session.execute(select(WorkoutSession).where(WorkoutSession.client_id == client_id, WorkoutSession.plan_id == plan.id, WorkoutSession.date == today, WorkoutSession.completed == True))).scalars().first()
                plans.append({"id": plan.id, "name": plan.name, "assigned": a, "done_today": bool(session_today)})
        return plans

async def get_plan_exercises(plan_id: int):
    async with AsyncSessionLocal() as session:
        plan_exercises = (await session.execute(select(PlanExercise).where(PlanExercise.plan_id == plan_id).order_by(PlanExercise.order))).scalars().all()
        result = []
        for pe in plan_exercises:
            exercise = await session.get(Exercise, pe.exercise_id)
            if exercise:
                result.append({
                    "id": pe.id,
                    "exercise": exercise,
                    "sets": pe.sets,
                    "reps_min": pe.reps_min,
                    "reps_max": pe.reps_max,
                    "start_weight": pe.start_weight,
                    "technical_tip": pe.technical_tip
                })
        return result

async def get_last_weight(client_id: int, plan_exercise_id: int):
    async with AsyncSessionLocal() as session:
        last_set = (await session.execute(
            select(WorkoutSet)
            .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
            .where(
                WorkoutSession.client_id == client_id,
                WorkoutSet.plan_exercise_id == plan_exercise_id,
                WorkoutSet.is_completed == True
            )
            .order_by(desc(WorkoutSet.id))
            .limit(1)
        )).scalars().first()
        return last_set.weight if last_set else None

async def calculate_total_volume(session_id: int):
    async with AsyncSessionLocal() as db:
        sets = (await db.execute(select(WorkoutSet).where(WorkoutSet.session_id == session_id))).scalars().all()
        return sum(s.weight * s.reps for s in sets if s.is_completed)

def _safe_get_int_from_callback(callback_data: str, prefix: str = None) -> int | None:
    parts = callback_data.split("_")
    for part in reversed(parts):
        if part.isdigit(): return int(part)
    return None

def _safe_get_ids_from_callback(callback_data: str, count: int) -> list[int] | None:
    parts = callback_data.split("_")
    ids = []
    for part in reversed(parts):
        if part.isdigit(): ids.append(int(part))
        else: break
    if len(ids) >= count: return list(reversed(ids[-count:]))
    return None

# ==================== КЛІЄНТСЬКІ ХЕНДЛЕРИ ====================

@router.message(F.text == "🏋️ Спортзал")
async def cmd_gym(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено.")
    
    plans = await get_active_plans(user.id)
    if not plans: return await message.answer("🏋️ У вас поки немає призначених тренувань. Зверніться до тренера.")
    
    await state.set_state(WorkoutFSM.selecting_plan)
    await state.update_data(client_id=user.id)
    
    kb = gym_plans_keyboard(plans)
    await message.answer("🏋️ <b>Виберіть тренування:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("gym_plan_"))
async def cal_gym_select_plan(callback: types.CallbackQuery, state: FSMContext):
    plan_id = _safe_get_int_from_callback(callback.data, "gym_plan_")
    if not plan_id: return await callback.answer("❌ Помилка: некоректний план.", show_alert=True)
    
    data = await state.get_data()
    client_id = data.get("client_id")
    if not client_id: return await callback.answer("❌ Помилка. Почніть заново /start", show_alert=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(WorkoutSession).where(WorkoutSession.client_id == client_id, WorkoutSession.plan_id == plan_id, WorkoutSession.date == today, WorkoutSession.completed == True))).scalars().first()
        if existing:
            return await callback.answer("❌ Це тренування вже виконано сьогодні!", show_alert=True)
    
    # Отримуємо вправи плану
    plan_exercises = await get_plan_exercises(plan_id)
    if not plan_exercises:
        return await callback.answer("❌ У цьому плані немає вправ. Зверніться до тренера.", show_alert=True)
    
    # Ініціалізуємо стан тренування
    await state.update_data(
        plan_id=plan_id,
        plan_exercises=plan_exercises,
        completed_exercises=[],
        sets_data={}
    )
    await state.set_state(WorkoutFSM.viewing_exercises)
    
    await show_exercise_list(callback.message, state)
    await callback.answer()

async def show_exercise_list(target, state: FSMContext):
    data = await state.get_data()
    plan_exercises = data.get("plan_exercises", [])
    completed_ids = data.get("completed_exercises", [])
    
    text = "🏋️ <b>Ваше тренування</b>\n\n"
    text += "Оберіть вправу для виконання:\n\n"
    
    for pe in plan_exercises:
        status = "✅" if pe["id"] in completed_ids else "⬜"
        text += f"{status} {pe['exercise'].name}\n"
    
    kb = gym_exercise_list_keyboard(plan_exercises, completed_ids)
    
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(StateFilter(WorkoutFSM.viewing_exercises), F.data.startswith("gym_exercise_"))
async def cal_gym_select_exercise(callback: types.CallbackQuery, state: FSMContext):
    pe_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    plan_exercises = data.get("plan_exercises", [])
    completed_ids = data.get("completed_exercises", [])
    
    if pe_id in completed_ids:
        return await callback.answer("✅ Цю вправу вже виконано!", show_alert=True)
    
    pe = next((p for p in plan_exercises if p["id"] == pe_id), None)
    if not pe:
        return await callback.answer("❌ Вправу не знайдено.", show_alert=True)
    
    client_id = data.get("client_id")
    last_weight = await get_last_weight(client_id, pe_id)
    
    await state.update_data(current_pe=pe, last_weight=last_weight, current_set_num=1, current_sets=[])
    await state.set_state(WorkoutFSM.exercise_detail)
    
    await show_exercise_detail(callback.message, state)
    await callback.answer()

async def show_exercise_detail(target, state: FSMContext):
    data = await state.get_data()
    pe = data.get("current_pe")
    if not pe:
        return await target.answer("❌ Помилка: вправу не вибрано.")
    
    exercise = pe["exercise"]
    last_weight = data.get("last_weight")
    current_sets = data.get("current_sets", [])
    
    text = f"🏋️ <b>{exercise.name}</b>\n"
    text += f"📋 {pe['sets']} підходів × {pe['reps_min']}–{pe['reps_max']} повторень\n"
    if last_weight:
        text += f"💡 Остання вага: {last_weight} кг\n"
    text += "\n"
    if current_sets:
        text += "📝 <b>Введені підходи:</b>\n"
        for i, s in enumerate(current_sets, 1):
            text += f"  Підхід {i}: {s['weight']} кг × {s['reps']}\n"
    else:
        text += "Підходів ще не додано.\n"
    
    remaining = pe["sets"] - len(current_sets)
    kb = gym_exercise_detail_keyboard(pe["id"], remaining, last_weight)
    
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(StateFilter(WorkoutFSM.exercise_detail), F.data.startswith("gym_add_set_"))
async def cal_gym_add_set(callback: types.CallbackQuery, state: FSMContext):
    pe_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    current_pe = data.get("current_pe")
    if not current_pe or current_pe["id"] != pe_id:
        return await callback.answer("❌ Помилка: не та вправа.", show_alert=True)
    
    await state.set_state(WorkoutFSM.entering_set)
    await callback.message.edit_text(
        f"🏋️ <b>Введіть дані для підходу {len(data.get('current_sets', [])) + 1}</b>\n\n"
        "Введіть у форматі: <code>вага повторення</code>\n"
        "Наприклад: <code>50 8</code>\n"
        "Якщо залишити вагу порожньою, буде використана остання вага.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(StateFilter(WorkoutFSM.entering_set))
async def process_set_input(message: types.Message, state: FSMContext, bot: Bot):
    text = message.text.strip()
    data = await state.get_data()
    last_weight = data.get("last_weight")
    current_pe = data.get("current_pe")
    
    parts = text.split()
    if len(parts) == 2:
        try:
            weight = float(parts[0].replace(",", "."))
            reps = int(parts[1])
        except ValueError:
            return await message.answer("❌ Введіть коректні числа!")
    elif len(parts) == 1 and last_weight is not None:
        try:
            weight = last_weight
            reps = int(parts[0])
        except ValueError:
            return await message.answer("❌ Введіть число повторень!")
    else:
        return await message.answer(
            "❌ Введіть у форматі: <code>вага повторення</code> або тільки <code>повторення</code> (буде використано останню вагу)",
            parse_mode="HTML"
        )
    
    current_sets = data.get("current_sets", [])
    current_sets.append({"weight": weight, "reps": reps})
    await state.update_data(current_sets=current_sets, last_weight=weight)
    await state.set_state(WorkoutFSM.exercise_detail)
    
    await message.answer(f"✅ Підхід {len(current_sets)}: {weight} кг × {reps} повторень – збережено!")
    await show_exercise_detail(message, state)

@router.callback_query(StateFilter(WorkoutFSM.exercise_detail), F.data.startswith("gym_complete_exercise_"))
async def cal_gym_complete_exercise(callback: types.CallbackQuery, state: FSMContext):
    pe_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    current_sets = data.get("current_sets", [])
    current_pe = data.get("current_pe")
    
    if not current_pe or current_pe["id"] != pe_id:
        return await callback.answer("❌ Помилка: не та вправа.", show_alert=True)
    
    if len(current_sets) < current_pe["sets"]:
        return await callback.answer(f"❌ Виконано лише {len(current_sets)} з {current_pe['sets']} підходів. Додайте решту.", show_alert=True)
    
    session_id = data.get("session_id")
    if not session_id:
        client_id = data.get("client_id")
        plan_id = data.get("plan_id")
        today = datetime.now().strftime("%Y-%m-%d")
        start_time = datetime.now().strftime("%H:%M")
        async with AsyncSessionLocal() as db:
            session_obj = WorkoutSession(
                client_id=client_id,
                plan_id=plan_id,
                date=today,
                start_time=start_time,
                completed=False
            )
            db.add(session_obj)
            await db.commit()
            await db.refresh(session_obj)
            session_id = session_obj.id
            await state.update_data(session_id=session_id)
    
    async with AsyncSessionLocal() as db:
        for i, s in enumerate(current_sets, 1):
            set_obj = WorkoutSet(
                session_id=session_id,
                plan_exercise_id=pe_id,
                set_number=i,
                weight=s["weight"],
                reps=s["reps"],
                is_completed=True
            )
            db.add(set_obj)
        await db.commit()
    
    completed = data.get("completed_exercises", [])
    if pe_id not in completed:
        completed.append(pe_id)
    await state.update_data(completed_exercises=completed, current_sets=[], current_pe=None)
    await state.set_state(WorkoutFSM.viewing_exercises)
    
    await callback.answer("✅ Вправу завершено!")
    await show_exercise_list(callback.message, state)

@router.callback_query(F.data == "gym_back_to_list")
async def cal_gym_back_to_list(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(WorkoutFSM.viewing_exercises)
    await show_exercise_list(callback.message, state)
    await callback.answer()

@router.callback_query(StateFilter(WorkoutFSM.viewing_exercises), F.data == "gym_finish_workout")
async def cal_gym_finish_workout(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan_exercises = data.get("plan_exercises", [])
    completed = data.get("completed_exercises", [])
    if len(completed) < len(plan_exercises):
        return await callback.answer("❌ Ще не всі вправи виконані!", show_alert=True)
    
    await state.set_state(WorkoutFSM.finishing)
    await callback.message.edit_text(
        "🔚 <b>Завершити тренування?</b>\nВсі вправи виконані. Буде збережено підсумковий звіт.",
        reply_markup=gym_confirm_finish_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "gym_confirm_finish")
async def cal_gym_confirm_finish(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await finish_workout(callback.message, state, bot, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "gym_continue")
async def cal_gym_continue(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(WorkoutFSM.viewing_exercises)
    await show_exercise_list(callback.message, state)
    await callback.answer()

async def finish_workout(target, state: FSMContext, bot: Bot, user_id: int):
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        await state.clear()
        return await target.answer("❌ Немає активного тренування або ви не зробили жодного підходу.")
    
    async with AsyncSessionLocal() as db:
        session_obj = await db.get(WorkoutSession, session_id)
        if session_obj:
            session_obj.end_time = datetime.now().strftime("%H:%M")
            session_obj.completed = True
            session_obj.total_volume = await calculate_total_volume(session_id)
            session_obj.total_sets = (await db.execute(select(func.count(WorkoutSet.id)).where(WorkoutSet.session_id == session_id))).scalar()
            await db.commit()
    
    report = await generate_workout_report(session_id)
    if isinstance(target, types.Message):
        await target.answer(f"✅ <b>Тренування завершено!</b>\n\n{report}", parse_mode="HTML")
    else:
        await target.edit_text(f"✅ <b>Тренування завершено!</b>\n\n{report}", parse_mode="HTML")
        
    await send_trainer_report(bot, user_id, session_id)
    await state.clear()

async def generate_workout_report(session_id: int) -> str:
    async with AsyncSessionLocal() as db:
        session_obj = await db.get(WorkoutSession, session_id)
        if not session_obj: return "❌ Тренування не знайдено."
        sets = (await db.execute(select(WorkoutSet).where(WorkoutSet.session_id == session_id))).scalars().all()
        plan = await db.get(WorkoutPlan, session_obj.plan_id)
        lines = [
            f"📋 <b>{html.escape(plan.name)}</b>",
            f"📅 Дата: {session_obj.date}",
            f"⏱️ Час: {session_obj.start_time} – {session_obj.end_time}",
            f"🏋️ Загальний обсяг: <b>{session_obj.total_volume:.1f} кг</b>",
            f"✔️ Виконано підходів: {len(sets)}"
        ]
        exercise_sets = {}
        for s in sets:
            pe = await db.get(PlanExercise, s.plan_exercise_id)
            if pe:
                ex = await db.get(Exercise, pe.exercise_id)
                key = pe.id
                if key not in exercise_sets: exercise_sets[key] = {"name": ex.name, "sets": []}
                exercise_sets[key]["sets"].append((s.set_number, s.weight, s.reps))
        
        if exercise_sets:
            lines.append("\n📝 <b>Деталі:</b>")
            for pe_id, d in exercise_sets.items():
                lines.append(f"\n<b>{html.escape(d['name'])}</b>")
                for set_num, weight, reps in d["sets"]:
                    lines.append(f"  Підхід {set_num}: {weight} кг × {reps}")
        else:
            lines.append("\n📝 Немає збережених підходів.")
        return "\n".join(lines)

async def send_trainer_report(bot: Bot, user_id: int, session_id: int):
    async with AsyncSessionLocal() as db:
        session_obj = await db.get(WorkoutSession, session_id)
        if not session_obj: return
        client = await db.get(User, session_obj.client_id)
        if not client: return
        
        plan = await db.get(WorkoutPlan, session_obj.plan_id)
        sets = (await db.execute(select(WorkoutSet).where(WorkoutSet.session_id == session_id))).scalars().all()
        
        report_lines = [
            f"📋 <b>ЗВІТ ПРО ТРЕНУВАННЯ</b>",
            f"👤 Клієнт: {html.escape(client.full_name)}",
            f"📅 Дата: {session_obj.date}",
            f"⏱️ Час: {session_obj.start_time} – {session_obj.end_time}",
            f"📋 План: {html.escape(plan.name)}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🏋️ Загальний обсяг: <b>{session_obj.total_volume:.1f} кг</b>",
            f"✔️ Виконано підходів: {len(sets)}",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "📝 <b>Деталі вправ:</b>"
        ]
        exercise_sets = {}
        for s in sets:
            pe = await db.get(PlanExercise, s.plan_exercise_id)
            if pe:
                ex = await db.get(Exercise, pe.exercise_id)
                key = pe.id
                if key not in exercise_sets: exercise_sets[key] = {"name": ex.name, "sets": []}
                exercise_sets[key]["sets"].append((s.set_number, s.weight, s.reps))
        
        for pe_id, d in exercise_sets.items():
            report_lines.append(f"\n<b>{html.escape(d['name'])}</b>")
            for set_num, weight, reps in d["sets"]:
                report_lines.append(f"  Підхід {set_num}: {weight} кг × {reps}")
        
        report = "\n".join(report_lines)
        for admin_id in ADMIN_IDS:
            try: await bot.send_message(admin_id, report, parse_mode="HTML")
            except: pass

# ==================== ХЕНДЛЕРИ ДЛЯ ТРЕНЕРА ====================

@router.callback_query(F.data.startswith("tr_gym_manage_"))
async def cal_tr_gym_manage(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_manage_")
    if not client_id:
        data = await state.get_data()
        client_id = data.get("client_id")
        if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    await state.update_data(client_id=client_id)
    kb = trainer_gym_manage_keyboard(client_id)
    await callback.message.edit_text("🏋️ <b>Керування тренуваннями клієнта</b>\nОберіть дію:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ========== КАТАЛОГ ВПРАВ ==========

@router.callback_query(F.data.startswith("tr_gym_exercises_"))
async def cal_tr_gym_exercises(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_exercises_")
    if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise).order_by(Exercise.name))).scalars().all()
    
    builder = InlineKeyboardBuilder()
    if exercises:
        for ex in exercises[:15]:
            builder.button(text=f"{ex.emoji or '🏋️'} {ex.name}", callback_data=f"tr_gym_exercise_detail_{client_id}_{ex.id}")
        if len(exercises) > 15:
            builder.button(text="📋 Всі вправи (завантажити)", callback_data=f"tr_gym_exercises_all_{client_id}")
    builder.button(text="📝 Додати кілька вправ", callback_data=f"tr_gym_bulk_create_{client_id}")
    builder.button(text="➕ Створити нову вправу", callback_data=f"tr_gym_create_exercise_standalone_{client_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    builder.adjust(2)
    
    await callback.message.edit_text(
        "🏋️ <b>Каталог вправ</b>\n\nТут зберігаються всі доступні вправи. Ви можете додати нову, відредагувати назву або видалити.",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()

# ========== СТВОРЕННЯ ОДНІЄЇ ВПРАВИ ==========

@router.callback_query(F.data.startswith("tr_gym_create_exercise_standalone_"))
async def cal_tr_gym_create_exercise_standalone(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_create_exercise_standalone_")
    if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    await state.set_state(TrainerGymFSM.creating_exercise)
    await state.update_data(client_id=client_id, standalone=True, plan_id=None)
    await callback.message.edit_text("🏋️ <b>Створення нової вправи</b>\n\nВведіть назву вправи (наприклад: «Жим лежачи»).\nПісля створення ви зможете додати її до будь-якого плану через каталог.", parse_mode="HTML")
    await callback.answer()

# ========== ПАКЕТНЕ СТВОРЕННЯ ВПРАВ ==========

@router.callback_query(F.data.startswith("tr_gym_bulk_create_"))
async def cal_tr_gym_bulk_create(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_bulk_create_")
    if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    await state.set_state(TrainerGymFSM.bulk_create_exercises)
    await state.update_data(client_id=client_id)
    await callback.message.edit_text(
        "📝 <b>Швидке створення вправ</b>\n\n"
        "Введіть список вправ, кожну з нового рядка.\n"
        "Наприклад:\n"
        "Жим лежачи\n"
        "Тяга штанги в нахилі\n"
        "Присідання зі штангою\n\n"
        "Всі вправи будуть створені в каталозі за одну операцію.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.bulk_create_exercises))
async def process_bulk_create_exercises(message: types.Message, state: FSMContext):
    lines = [line.strip() for line in message.text.split('\n') if line.strip()]
    if not lines:
        return await message.answer("❌ Введіть хоча б одну вправу.")
    
    data = await state.get_data()
    client_id = data.get("client_id")
    trainer = await get_user_by_telegram_id(message.from_user.id)
    if not trainer:
        return await message.answer("❌ Ваш профіль не знайдено.")
    
    created = []
    skipped = []
    async with AsyncSessionLocal() as session:
        for name in lines:
            existing = (await session.execute(select(Exercise).where(Exercise.name == name))).scalars().first()
            if existing:
                skipped.append(name)
                continue
            exercise = Exercise(name=name, created_by=trainer.id)
            session.add(exercise)
            created.append(name)
        await session.commit()
    
    result = f"✅ Створено вправ: {len(created)}\n"
    if created:
        result += "📝 " + ", ".join(created) + "\n"
    if skipped:
        result += f"⚠️ Пропущено (вже існують): {', '.join(skipped)}"
    
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 До каталогу", callback_data=f"tr_gym_exercises_{client_id}")
    await message.answer(result, reply_markup=kb.as_markup(), parse_mode="HTML")

# ========== ПЕРЕГЛЯД ДЕТАЛЕЙ ВПРАВИ ==========

@router.callback_query(F.data.startswith("tr_gym_exercise_detail_"))
async def cal_tr_gym_exercise_detail(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, exercise_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        exercise = await session.get(Exercise, exercise_id)
        if not exercise: return await callback.answer("❌ Вправу не знайдено.", show_alert=True)
    
    text = (f"🏋️ <b>{html.escape(exercise.name)}</b>\n📝 Опис: {html.escape(exercise.description) if exercise.description else 'не вказано'}\n"
            f"💪 Група м'язів: {exercise.muscle_group or 'не вказано'}\n📅 Створено: {exercise.created_at.strftime('%d.%m.%Y') if exercise.created_at else 'невідомо'}")
    
    kb = gym_edit_exercise_keyboard(exercise_id, client_id)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ========== РЕДАГУВАННЯ НАЗВИ ВПРАВИ ==========

@router.callback_query(F.data.startswith("tr_gym_edit_exercise_name_"))
async def cal_tr_gym_edit_exercise_name(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    exercise_id = _safe_get_int_from_callback(callback.data, "tr_gym_edit_exercise_name_")
    if not exercise_id: return await callback.answer("❌ Помилка: некоректна вправа.", show_alert=True)
    
    await state.set_state(TrainerGymFSM.editing_exercise_name)
    await state.update_data(exercise_id=exercise_id, client_id=_safe_get_int_from_callback(callback.data, "tr_gym_edit_exercise_name_", 2) or 0)
    await callback.message.edit_text(
        "✏️ <b>Редагування назви вправи</b>\n\n"
        "Введіть нову назву:",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.editing_exercise_name))
async def process_edit_exercise_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        return await message.answer("❌ Назва не може бути порожньою.")
    
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    client_id = data.get("client_id")
    
    async with AsyncSessionLocal() as session:
        exercise = await session.get(Exercise, exercise_id)
        if not exercise:
            return await message.answer("❌ Вправу не знайдено.")
        existing = (await session.execute(select(Exercise).where(Exercise.name == new_name, Exercise.id != exercise_id))).scalars().first()
        if existing:
            return await message.answer(f"❌ Вправа з назвою <b>{html.escape(new_name)}</b> вже існує.", parse_mode="HTML")
        exercise.name = new_name
        await session.commit()
    
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 До каталогу", callback_data=f"tr_gym_exercises_{client_id}")
    await message.answer(f"✅ Назву вправи змінено на <b>{html.escape(new_name)}</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

# ========== ВИДАЛЕННЯ ВПРАВИ ==========

@router.callback_query(F.data.startswith("tr_gym_delete_exercise_"))
async def cal_tr_gym_delete_exercise(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    exercise_id = _safe_get_int_from_callback(callback.data, "tr_gym_delete_exercise_")
    if not exercise_id: return await callback.answer("❌ Помилка: некоректна вправа.", show_alert=True)
    
    async with AsyncSessionLocal() as session:
        exercise = await session.get(Exercise, exercise_id)
        if not exercise:
            return await callback.answer("❌ Вправу не знайдено.", show_alert=True)
        used = (await session.execute(select(func.count(PlanExercise.id)).where(PlanExercise.exercise_id == exercise_id))).scalar()
        if used > 0:
            return await callback.answer(f"❌ Вправу <b>{html.escape(exercise.name)}</b> використовується в планах ({used}). Спочатку видаліть її з планів.", show_alert=True, parse_mode="HTML")
        await session.delete(exercise)
        await session.commit()
    
    await callback.answer("🗑️ Вправу видалено!", show_alert=True)
    # Повертаємося до каталогу
    await cal_tr_gym_exercises(callback)

# ========== ДОДАТИ ВПРАВУ З КАТАЛОГУ ДО ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_add_existing_to_plan_"))
async def cal_tr_gym_add_existing_to_plan(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, exercise_id = ids[0], ids[1]
    
    data = await state.get_data()
    plan_id = data.get("plan_id")
    if not plan_id: return await callback.answer("❌ Спочатку виберіть або створіть план.", show_alert=True)
    
    await state.update_data(exercise_id=exercise_id)
    await state.set_state(TrainerGymFSM.setting_exercise_params)
    await callback.message.edit_text("⚙️ <b>Налаштування вправи для плану</b>\n\nВведіть параметри у форматі:\n<code>підходи повторення_від повторення_до</code>\n\nНаприклад: <code>3 8 12</code> (крок ваги більше не використовується)", parse_mode="HTML")
    await callback.answer()

# ========== ШАБЛОНИ ==========

@router.callback_query(F.data.startswith("tr_gym_templates_"))
async def cal_tr_gym_templates(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_templates_")
    if not client_id:
        data = await state.get_data()
        client_id = data.get("client_id")
        if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    trainer = await get_user_by_telegram_id(callback.from_user.id)
    if not trainer: return await callback.answer("❌ Ваш профіль не знайдено.", show_alert=True)
    
    async with AsyncSessionLocal() as session:
        templates = (await session.execute(
            select(WorkoutPlan).where(
                WorkoutPlan.created_by == trainer.id,
                WorkoutPlan.is_template == True,
                WorkoutPlan.client_id == None
            ).order_by(WorkoutPlan.name)
        )).scalars().all()
    
    kb = InlineKeyboardBuilder()
    if templates:
        for t in templates:
            kb.button(text=f"📋 {t.name}", callback_data=f"tr_gym_assign_template_{client_id}_{t.id}")
    kb.button(text="➕ Створити новий шаблон", callback_data=f"tr_gym_create_template_{client_id}")
    kb.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "📋 <b>Шаблони планів</b>\n\n"
        "Тут зберігаються ваші готові шаблони тренувань. "
        "Ви можете призначити будь-який шаблон клієнту одним натисканням.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tr_gym_create_template_"))
async def cal_tr_gym_create_template(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_create_template_")
    if not client_id:
        data = await state.get_data()
        client_id = data.get("client_id")
        if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    await state.set_state(TrainerGymFSM.creating_plan)
    await state.update_data(client_id=client_id, is_template=True)
    await callback.message.edit_text(
        "📝 <b>Створення нового шаблону</b>\n\n"
        "Введіть назву шаблону (наприклад: «Верх А»).\n"
        "Після створення ви зможете додати вправи так само, як і в звичайному плані.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tr_gym_assign_template_"))
async def cal_tr_gym_assign_template(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    parts = callback.data.split("_")
    if len(parts) < 5: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id = int(parts[3])
    template_id = int(parts[4])
    
    async with AsyncSessionLocal() as session:
        template = await session.get(WorkoutPlan, template_id)
        if not template: return await callback.answer("❌ Шаблон не знайдено.", show_alert=True)
        new_plan = WorkoutPlan(
            name=template.name,
            description=template.description,
            created_by=template.created_by,
            is_template=False,
            client_id=client_id
        )
        session.add(new_plan)
        await session.commit()
        await session.refresh(new_plan)
        template_exercises = (await session.execute(select(PlanExercise).where(PlanExercise.plan_id == template_id))).scalars().all()
        for pe in template_exercises:
            new_pe = PlanExercise(
                plan_id=new_plan.id,
                exercise_id=pe.exercise_id,
                order=pe.order,
                sets=pe.sets,
                reps_min=pe.reps_min,
                reps_max=pe.reps_max,
                start_weight=pe.start_weight,
                technical_tip=pe.technical_tip
            )
            session.add(new_pe)
        await session.commit()
        assigned = AssignedPlan(client_id=client_id, plan_id=new_plan.id, is_active=True)
        session.add(assigned)
        await session.commit()
    
    await callback.answer("✅ Шаблон призначено клієнту!", show_alert=True)
    await cal_tr_gym_manage(callback, None)

# ========== КОПІЮВАННЯ ПЛАНУ ДЛЯ ІНШОГО КЛІЄНТА ==========

@router.callback_query(F.data.startswith("tr_gym_copy_plan_"))
async def cal_tr_gym_copy_plan(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    await state.update_data(plan_id=plan_id, client_id=client_id)
    await state.set_state(TrainerGymFSM.copy_plan_to_client)
    
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client").order_by(User.full_name))).scalars().all()
    
    kb = gym_client_selection_keyboard(clients, plan_id)
    await callback.message.edit_text(
        "📋 <b>Виберіть клієнта для копіювання плану</b>",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(StateFilter(TrainerGymFSM.copy_plan_to_client), F.data.startswith("tr_gym_copy_to_client_"))
async def cal_tr_gym_copy_to_client(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    parts = callback.data.split("_")
    if len(parts) < 5: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    new_client_id = int(parts[4])
    
    data = await state.get_data()
    source_plan_id = data.get("plan_id")
    if not source_plan_id:
        return await callback.answer("❌ Помилка: план не вибрано.", show_alert=True)
    
    async with AsyncSessionLocal() as session:
        source_plan = await session.get(WorkoutPlan, source_plan_id)
        if not source_plan: return await callback.answer("❌ План не знайдено.", show_alert=True)
        new_plan = WorkoutPlan(
            name=source_plan.name + " (копія)",
            description=source_plan.description,
            created_by=source_plan.created_by,
            is_template=False,
            client_id=new_client_id
        )
        session.add(new_plan)
        await session.commit()
        await session.refresh(new_plan)
        exercises = (await session.execute(select(PlanExercise).where(PlanExercise.plan_id == source_plan_id))).scalars().all()
        for pe in exercises:
            new_pe = PlanExercise(
                plan_id=new_plan.id,
                exercise_id=pe.exercise_id,
                order=pe.order,
                sets=pe.sets,
                reps_min=pe.reps_min,
                reps_max=pe.reps_max,
                start_weight=pe.start_weight,
                technical_tip=pe.technical_tip
            )
            session.add(new_pe)
        await session.commit()
        assigned = AssignedPlan(client_id=new_client_id, plan_id=new_plan.id, is_active=True)
        session.add(assigned)
        await session.commit()
    
    await state.clear()
    await callback.answer("✅ План скопійовано!", show_alert=True)
    await cal_tr_gym_manage(callback, None)

# ========== КОПІЮВАННЯ ПЛАНУ ЯК ШАБЛОН ==========

@router.callback_query(F.data.startswith("tr_gym_copy_as_template_"))
async def cal_tr_gym_copy_as_template(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        source_plan = await session.get(WorkoutPlan, plan_id)
        if not source_plan: return await callback.answer("❌ План не знайдено.", show_alert=True)
        new_template = WorkoutPlan(
            name=source_plan.name + " (шаблон)",
            description=source_plan.description,
            created_by=source_plan.created_by,
            is_template=True,
            client_id=None
        )
        session.add(new_template)
        await session.commit()
        await session.refresh(new_template)
        exercises = (await session.execute(select(PlanExercise).where(PlanExercise.plan_id == plan_id))).scalars().all()
        for pe in exercises:
            new_pe = PlanExercise(
                plan_id=new_template.id,
                exercise_id=pe.exercise_id,
                order=pe.order,
                sets=pe.sets,
                reps_min=pe.reps_min,
                reps_max=pe.reps_max,
                start_weight=pe.start_weight,
                technical_tip=pe.technical_tip
            )
            session.add(new_pe)
        await session.commit()
    
    await callback.answer("✅ Шаблон створено!", show_alert=True)
    await cal_tr_gym_plan_detail(callback)

# ========== СПИСОК ПЛАНІВ КЛІЄНТА ==========

@router.callback_query(F.data.startswith("tr_gym_plans_"))
async def cal_tr_gym_plans(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_plans_")
    if not client_id:
        data = await state.get_data()
        client_id = data.get("client_id")
        if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    async with AsyncSessionLocal() as session:
        assigned = (await session.execute(select(AssignedPlan).where(AssignedPlan.client_id == client_id))).scalars().all()
        plans = []
        for a in assigned:
            plan = await session.get(WorkoutPlan, a.plan_id)
            if plan: plans.append({"id": plan.id, "name": plan.name, "is_active": a.is_active})
    
    if not plans:
        kb = InlineKeyboardBuilder().button(text="➕ Створити перший план", callback_data=f"tr_gym_create_plan_{client_id}")
        kb.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
        kb.adjust(1)
        return await callback.message.edit_text("📭 У клієнта немає призначених планів.", reply_markup=kb.as_markup(), parse_mode="HTML")
    
    builder = InlineKeyboardBuilder()
    for p in plans:
        status = "✅" if p["is_active"] else "⛔"
        builder.button(text=f"{status} {p['name']}", callback_data=f"tr_gym_plan_detail_{client_id}_{p['id']}")
    builder.button(text="➕ Створити новий", callback_data=f"tr_gym_create_plan_{client_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    builder.adjust(1)
    
    await callback.message.edit_text("📋 <b>Плани клієнта:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# ========== СТВОРЕННЯ ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_create_plan_"))
async def cal_tr_gym_create_plan(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    client_id = _safe_get_int_from_callback(callback.data, "tr_gym_create_plan_")
    if not client_id:
        data = await state.get_data()
        client_id = data.get("client_id")
        if not client_id: return await callback.answer("❌ Помилка: не вибрано клієнта.", show_alert=True)
    
    await state.set_state(TrainerGymFSM.creating_plan)
    await state.update_data(client_id=client_id, is_template=False)
    await callback.message.edit_text("📝 <b>Створення нового плану</b>\n\nВведіть назву плану (наприклад: «День 1 – Верх А»):", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.creating_plan))
async def process_create_plan_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name: return await message.answer("❌ Назва не може бути порожньою.")
    
    data = await state.get_data()
    client_id = data.get("client_id")
    is_template = data.get("is_template", False)
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id) if not is_template else None
        trainer = await get_user_by_telegram_id(message.from_user.id)
        if not trainer: return await message.answer("❌ Ваш профіль не знайдено.")
        
        plan = WorkoutPlan(
            name=name,
            created_by=trainer.id,
            is_template=is_template,
            client_id=None if is_template else client.id
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        plan_id = plan.id
    
    await state.update_data(plan_id=plan_id)
    await state.set_state(TrainerGymFSM.adding_exercise_to_plan)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати вправу", callback_data=f"tr_gym_add_exercise_{plan_id}")
    kb.button(text="✅ Завершити створення", callback_data=f"tr_gym_finish_plan_{client_id}_{plan_id}")
    kb.button(text="🔙 Скасувати", callback_data=f"tr_gym_manage_{client_id}")
    kb.adjust(1)
    
    await message.answer(f"✅ План <b>{html.escape(name)}</b> створено!\n\nТепер додайте вправи. Натисніть кнопку, щоб вибрати вправу з каталогу.", reply_markup=kb.as_markup(), parse_mode="HTML")

# ========== ДОДАВАННЯ ВПРАВИ ДО ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_add_exercise_"))
async def cal_tr_gym_add_exercise(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    plan_id = _safe_get_int_from_callback(callback.data, "tr_gym_add_exercise_")
    if not plan_id:
        data = await state.get_data()
        plan_id = data.get("plan_id")
        if not plan_id: return await callback.answer("❌ Помилка: некоректний план.", show_alert=True)
    
    await state.update_data(plan_id=plan_id)
    
    async with AsyncSessionLocal() as session:
        exercises = (await session.execute(select(Exercise).order_by(Exercise.name))).scalars().all()
    
    if not exercises:
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Створити першу вправу", callback_data=f"tr_gym_create_exercise_{plan_id}")
        data = await state.get_data()
        client_id = data.get("client_id")
        if client_id: kb.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
        else: kb.button(text="🔙 Назад", callback_data=f"tr_gym_manage_0")
        kb.adjust(1)
        await callback.message.edit_text("🏋️ <b>Каталог вправ порожній</b>\n\nСтворіть першу вправу, щоб додати її до плану.", reply_markup=kb.as_markup(), parse_mode="HTML")
        return await callback.answer()
    
    kb = gym_exercise_catalog_keyboard(exercises, plan_id)
    await callback.message.edit_text("🏋️ <b>Виберіть вправу для додавання до плану:</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_gym_select_exercise_"))
async def cal_tr_gym_select_exercise(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    plan_id, exercise_id = ids[0], ids[1]
    
    await state.update_data(plan_id=plan_id, exercise_id=exercise_id)
    await state.set_state(TrainerGymFSM.setting_exercise_params)
    await callback.message.edit_text("⚙️ <b>Налаштування вправи</b>\n\nВведіть параметри у форматі:\n<code>підходи повторення_від повторення_до</code>\n\nНаприклад: <code>3 8 12</code>", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.setting_exercise_params))
async def process_exercise_params(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 3:
        return await message.answer("❌ Введіть 3 числа: <code>підходи повторення_від повторення_до</code>", parse_mode="HTML")
    
    try:
        sets = int(parts[0])
        reps_min = int(parts[1])
        reps_max = int(parts[2])
    except ValueError:
        return await message.answer("❌ Введіть коректні числа!")
    
    data = await state.get_data()
    plan_id = data.get("plan_id")
    exercise_id = data.get("exercise_id")
    client_id = data.get("client_id")
    
    if not plan_id or not exercise_id:
        return await message.answer("❌ Помилка: втрачено контекст плану або вправи. Спробуйте ще раз.")
    
    async with AsyncSessionLocal() as session:
        max_order = (await session.execute(select(func.max(PlanExercise.order)).where(PlanExercise.plan_id == plan_id))).scalar() or 0
        pe = PlanExercise(
            plan_id=plan_id,
            exercise_id=exercise_id,
            order=max_order + 1,
            sets=sets,
            reps_min=reps_min,
            reps_max=reps_max,
            start_weight=None
        )
        session.add(pe)
        await session.commit()
    
    await state.set_state(TrainerGymFSM.adding_exercise_to_plan)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати ще вправу", callback_data=f"tr_gym_add_exercise_{plan_id}")
    kb.button(text="✅ Завершити створення", callback_data=f"tr_gym_finish_plan_{client_id}_{plan_id}")
    kb.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    kb.adjust(1)
    
    await message.answer("✅ Вправу додано до плану!\n\nЩо робимо далі?", reply_markup=kb.as_markup())

# ========== СТВОРЕННЯ ВПРАВИ З ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_create_exercise_"))
async def cal_tr_gym_create_exercise(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    if callback.data.startswith("tr_gym_create_exercise_standalone_"): return
    
    plan_id = _safe_get_int_from_callback(callback.data, "tr_gym_create_exercise_")
    if not plan_id: return await callback.answer("❌ Помилка: некоректний план.", show_alert=True)
    
    await state.update_data(plan_id=plan_id, standalone=False)
    await state.set_state(TrainerGymFSM.creating_exercise)
    await callback.message.edit_text("🏋️ <b>Створення нової вправи</b>\n\nВведіть назву вправи (наприклад: «Жим лежачи»):", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.creating_exercise))
async def process_create_exercise(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name: return await message.answer("❌ Назва не може бути порожньою.")
    
    data = await state.get_data()
    plan_id = data.get("plan_id")
    client_id = data.get("client_id")
    standalone = data.get("standalone", False)
    
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(Exercise).where(Exercise.name == name))).scalars().first()
        if existing: return await message.answer(f"❌ Вправа з назвою <b>{html.escape(name)}</b> вже існує. Оберіть іншу назву.", parse_mode="HTML")
        
        trainer = await get_user_by_telegram_id(message.from_user.id)
        if not trainer: return await message.answer("❌ Ваш профіль не знайдено.")
        
        exercise = Exercise(name=name, created_by=trainer.id)
        session.add(exercise)
        await session.commit()
        await session.refresh(exercise)
        exercise_id = exercise.id
    
    if standalone or not plan_id:
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 До каталогу", callback_data=f"tr_gym_exercises_{client_id}")
        await message.answer(
            f"✅ Вправу <b>{html.escape(name)}</b> створено!\n\nТепер ви можете додати її до будь-якого плану через каталог.",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        return
    
    await state.update_data(exercise_id=exercise_id)
    await state.set_state(TrainerGymFSM.setting_exercise_params)
    await message.answer(f"✅ Вправу <b>{html.escape(name)}</b> створено!\n\nТепер налаштуйте параметри для додавання до плану:\n<code>підходи повторення_від повторення_до</code>\n\nНаприклад: <code>3 8 12</code>", parse_mode="HTML")

# ========== ЗАВЕРШЕННЯ ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_finish_plan_"))
async def cal_tr_gym_finish_plan(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        count = (await session.execute(select(func.count(PlanExercise.id)).where(PlanExercise.plan_id == plan_id))).scalar()
    
    if count == 0: return await callback.answer("❌ План не може бути порожнім! Додайте хоча б одну вправу.", show_alert=True)
    
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Призначити клієнту", callback_data=f"tr_gym_assign_{client_id}_{plan_id}")
    kb.button(text="🔙 До керування", callback_data=f"tr_gym_manage_{client_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(f"✅ План успішно створено!\n\nВправи: {count}\nТепер призначте його клієнту.", reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

# ========== ПРИЗНАЧЕННЯ ПЛАНУ КЛІЄНТУ ==========

@router.callback_query(F.data.startswith("tr_gym_assign_"))
async def cal_tr_gym_assign_plan(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        if not client: return await callback.answer("❌ Клієнта не знайдено.", show_alert=True)
        existing = (await session.execute(select(AssignedPlan).where(AssignedPlan.client_id == client_id, AssignedPlan.plan_id == plan_id))).scalars().first()
        if existing:
            existing.is_active = True
            await session.commit()
            return await callback.answer("✅ План вже був призначений, активовано!", show_alert=True)
        assigned = AssignedPlan(client_id=client_id, plan_id=plan_id, is_active=True)
        session.add(assigned)
        await session.commit()
    
    await callback.answer("✅ План успішно призначено клієнту!", show_alert=True)
    kb = InlineKeyboardBuilder().button(text="🔙 До керування", callback_data=f"tr_gym_manage_{client_id}")
    await callback.message.edit_text("✅ План призначено!\n\nКлієнт тепер бачить це тренування у розділі «Спортзал».", reply_markup=kb.as_markup(), parse_mode="HTML")

# ========== ДЕТАЛІ ПЛАНУ (з редагуванням) ==========

@router.callback_query(F.data.startswith("tr_gym_plan_detail_"))
async def cal_tr_gym_plan_detail(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        plan = await session.get(WorkoutPlan, plan_id)
        if not plan: return await callback.answer("❌ План не знайдено.", show_alert=True)
        exercises = await get_plan_exercises(plan_id)
        assigned = (await session.execute(select(AssignedPlan).where(AssignedPlan.client_id == client_id, AssignedPlan.plan_id == plan_id))).scalars().first()
    
    text = f"📋 <b>{html.escape(plan.name)}</b>\n\n"
    if exercises:
        text += "📝 <b>Вправи:</b>\n"
        for i, pe in enumerate(exercises, 1):
            text += f"{i}. {pe['exercise'].name} — {pe['sets']}×{pe['reps_min']}–{pe['reps_max']}\n"
    else: text += "📭 Немає вправ.\n"
    text += f"\n📊 Статус: {'✅ Активний' if assigned and assigned.is_active else '⛔ Неактивний'}"
    
    builder = InlineKeyboardBuilder()
    if assigned:
        new_status = "⛔ Деактивувати" if assigned.is_active else "✅ Активувати"
        builder.button(text=new_status, callback_data=f"tr_gym_toggle_{client_id}_{plan_id}")
    builder.button(text="📋 Копіювати для іншого", callback_data=f"tr_gym_copy_plan_{client_id}_{plan_id}")
    builder.button(text="📋 Копіювати як шаблон", callback_data=f"tr_gym_copy_as_template_{client_id}_{plan_id}")
    if exercises:
        builder.button(text="✏️ Редагувати вправи", callback_data=f"tr_gym_edit_exercises_{client_id}_{plan_id}")
    builder.button(text="➕ Додати вправу", callback_data=f"tr_gym_add_exercise_{plan_id}")
    builder.button(text="🗑️ Видалити план", callback_data=f"tr_gym_delete_{client_id}_{plan_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_plans_{client_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# ========== РЕДАГУВАННЯ ВПРАВ У ПЛАНІ ==========

@router.callback_query(F.data.startswith("tr_gym_edit_exercises_"))
async def cal_tr_gym_edit_exercises(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    await state.update_data(client_id=client_id, plan_id=plan_id)
    
    async with AsyncSessionLocal() as session:
        exercises = await get_plan_exercises(plan_id)
    
    if not exercises:
        return await callback.answer("❌ У плані немає вправ.", show_alert=True)
    
    kb = InlineKeyboardBuilder()
    for pe in exercises:
        kb.button(text=f"✏️ {pe['exercise'].name} (id:{pe['id']})", callback_data=f"tr_gym_edit_exercise_{client_id}_{pe['id']}")
    kb.button(text="🔙 Назад", callback_data=f"tr_gym_plan_detail_{client_id}_{plan_id}")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "✏️ <b>Виберіть вправу для редагування</b>\n\n"
        "Ви можете змінити кількість підходів або діапазон повторень.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tr_gym_edit_exercise_"))
async def cal_tr_gym_edit_exercise(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, pe_id = ids[0], ids[1]
    
    await state.update_data(client_id=client_id, pe_id=pe_id)
    await state.set_state(TrainerGymFSM.editing_plan_exercise)
    
    async with AsyncSessionLocal() as session:
        pe = await session.get(PlanExercise, pe_id)
        if not pe: return await callback.answer("❌ Вправу не знайдено.", show_alert=True)
        exercise = await session.get(Exercise, pe.exercise_id)
    
    await callback.message.edit_text(
        f"✏️ <b>Редагування вправи: {exercise.name}</b>\n\n"
        f"Поточні параметри:\n"
        f"Підходи: {pe.sets}\n"
        f"Повторення: {pe.reps_min}–{pe.reps_max}\n\n"
        "Введіть нові параметри у форматі:\n"
        "<code>підходи повторення_від повторення_до</code>\n"
        "Наприклад: <code>4 10 15</code>\n\n"
        "Або натисніть кнопку для скасування.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(StateFilter(TrainerGymFSM.editing_plan_exercise))
async def process_edit_plan_exercise(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 3:
        return await message.answer("❌ Введіть 3 числа: <code>підходи повторення_від повторення_до</code>", parse_mode="HTML")
    
    try:
        sets = int(parts[0])
        reps_min = int(parts[1])
        reps_max = int(parts[2])
    except ValueError:
        return await message.answer("❌ Введіть коректні числа!")
    
    data = await state.get_data()
    pe_id = data.get("pe_id")
    client_id = data.get("client_id")
    plan_id = data.get("plan_id")
    
    async with AsyncSessionLocal() as session:
        pe = await session.get(PlanExercise, pe_id)
        if not pe:
            return await message.answer("❌ Вправу не знайдено.")
        pe.sets = sets
        pe.reps_min = reps_min
        pe.reps_max = reps_max
        await session.commit()
    
    await state.clear()
    await message.answer("✅ Параметри вправи оновлено!")
    await cal_tr_gym_plan_detail(None)

# ========== ВКЛЮЧЕННЯ/ВИМКНЕННЯ ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_toggle_"))
async def cal_tr_gym_toggle(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        assigned = (await session.execute(select(AssignedPlan).where(AssignedPlan.client_id == client_id, AssignedPlan.plan_id == plan_id))).scalars().first()
        if assigned:
            assigned.is_active = not assigned.is_active
            await session.commit()
    
    await callback.answer("✅ Статус оновлено!")
    await cal_tr_gym_plan_detail(callback)

# ========== ВИДАЛЕННЯ ПЛАНУ ==========

@router.callback_query(F.data.startswith("tr_gym_delete_"))
async def cal_tr_gym_delete_plan(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return await callback.answer("⛔ Доступ заборонено.", show_alert=True)
    ids = _safe_get_ids_from_callback(callback.data, 2)
    if not ids or len(ids) != 2: return await callback.answer("❌ Помилка: некоректний формат.", show_alert=True)
    client_id, plan_id = ids[0], ids[1]
    
    async with AsyncSessionLocal() as session:
        plan = await session.get(WorkoutPlan, plan_id)
        if not plan: return await callback.answer("❌ План не знайдено.", show_alert=True)
        await session.execute(delete(AssignedPlan).where(AssignedPlan.client_id == client_id, AssignedPlan.plan_id == plan_id))
        await session.execute(delete(PlanExercise).where(PlanExercise.plan_id == plan_id))
        await session.delete(plan)
        await session.commit()
    
    await callback.answer("🗑️ План видалено!", show_alert=True)
    await cal_tr_gym_plans(callback)