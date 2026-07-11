# FILE: ./bot/handlers_gym.py
import asyncio
import logging
import re
from datetime import datetime

from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, delete

from database.engine import GymSessionLocal as AsyncSessionLocal
from database.models import User, WorkoutSession, WorkoutSet
from bot.security import HasPermission
from config import ALLOWED_USER_ID
from bot.gym_data import WORKOUT_PROGRAM, DAY_ORDER, get_exercise_name
from bot import sheets_sync

logger = logging.getLogger(__name__)
router = Router()


class GymState(StatesGroup):
    waiting_for_set_input = State()


# ==========================================
# ДОПОМІЖНІ ФУНКЦІЇ
# ==========================================
def _parse_weight_reps(text: str) -> tuple[float, int] | None:
    """Приймає '60x8', '60 8', '60,8', '60/8' — все, що людина природно напише."""
    match = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[xх×,/\s]\s*(\d+)\s*$", text.strip(), re.IGNORECASE)
    if not match:
        return None
    weight = float(match.group(1).replace(",", "."))
    reps = int(match.group(2))
    return weight, reps


async def _get_sets_done(session, session_id: int, exercise_key: str) -> list[WorkoutSet]:
    stmt = select(WorkoutSet).where(
        WorkoutSet.session_id == session_id,
        WorkoutSet.exercise_key == exercise_key,
    ).order_by(WorkoutSet.set_number)
    return (await session.execute(stmt)).scalars().all()


async def _get_last_set_for_exercise(session, user_id: int, exercise_key: str, exclude_session_id: int) -> WorkoutSet | None:
    """Останній записаний підхід по цій вправі з БУДЬ-ЯКОГО попереднього тренування."""
    stmt = (
        select(WorkoutSet)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSet.exercise_key == exercise_key,
            WorkoutSession.id != exclude_session_id,
        )
        .order_by(WorkoutSet.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _is_personal_record(session, user_id: int, exercise_key: str, weight: float, reps: int) -> bool:
    """Рекорд, якщо вага×повтори перевищує будь-який попередній підхід по цій вправі."""
    stmt = (
        select(func.max(WorkoutSet.weight_kg * WorkoutSet.reps))
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user_id, WorkoutSet.exercise_key == exercise_key)
    )
    best = (await session.execute(stmt)).scalar_one_or_none()
    return best is None or (weight * reps) > best


async def _rest_timer(chat_id: int, bot: Bot, seconds: int):
    try:
        await asyncio.sleep(seconds)
        await bot.send_message(chat_id, "⏰ Час відпочинку вийшов, наступний підхід!")
    except Exception:
        pass


# ==========================================
# ГОЛОВНЕ МЕНЮ СПОРТЗАЛУ
# ==========================================
@router.message(F.text == "🏋️ Спортзал", HasPermission("gym"))
async def gym_menu(message: types.Message):
    async with AsyncSessionLocal() as session:
        active = (await session.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == message.from_user.id,
                WorkoutSession.finished_at.is_(None),
            ).order_by(WorkoutSession.started_at.desc())
        )).scalars().first()

    builder = InlineKeyboardBuilder()
    if active:
        title = WORKOUT_PROGRAM[active.day_key]["title"]
        builder.button(text=f"▶️ Продовжити: {title}", callback_data=f"gym_open_{active.id}")
    else:
        builder.button(text="🏁 Почати тренування", callback_data="gym_start_confirm")

    builder.button(text="📊 Історія тренувань", callback_data="gym_history")
    builder.adjust(1)

    status = sheets_sync.sync_status()
    await message.answer(
        f"🏋️ <b>Спортзал</b>\n<i>Бекап в Google Sheets: {status}</i>",
        reply_markup=builder.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data == "gym_start_confirm", HasPermission("gym"))
async def gym_start_confirm(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        next_day_key = DAY_ORDER[user.next_workout_index % len(DAY_ORDER)]

    title = WORKOUT_PROGRAM[next_day_key]["title"]
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Почати: {title}", callback_data=f"gym_begin_{next_day_key}")
    builder.button(text="🔀 Обрати інший день", callback_data="gym_pick_day")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📅 За розкладом сьогодні: <b>{title}</b>\nПочинаємо?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "gym_pick_day", HasPermission("gym"))
async def gym_pick_day(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for day_key in DAY_ORDER:
        builder.button(text=WORKOUT_PROGRAM[day_key]["title"], callback_data=f"gym_begin_{day_key}")
    builder.adjust(2)
    await callback.message.edit_text("Обери день тренування вручну:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("gym_begin_"), HasPermission("gym"))
async def gym_begin(callback: types.CallbackQuery):
    day_key = callback.data.replace("gym_begin_", "")
    uid = callback.from_user.id

    async with AsyncSessionLocal() as session:
        new_session = WorkoutSession(user_id=uid, day_key=day_key)
        session.add(new_session)

        # Просуваємо автоматичну ротацію на наступний день, тільки якщо
        # почали саме той день, що йшов за розкладом (а не обраний вручну "не по черзі")
        user = await session.get(User, uid)
        current_auto_day = DAY_ORDER[user.next_workout_index % len(DAY_ORDER)]
        if day_key == current_auto_day:
            user.next_workout_index = (user.next_workout_index + 1) % len(DAY_ORDER)

        await session.commit()
        await session.refresh(new_session)
        session_id = new_session.id
        started_at = new_session.started_at

    asyncio.create_task(sheets_sync.sync_session(
        session_id, uid, day_key, WORKOUT_PROGRAM[day_key]["title"], started_at, None,
    ))

    await _render_exercise_list(callback.message, session_id, day_key, edit=True)
    await callback.answer("Тренування почалось 💪")


@router.callback_query(F.data.startswith("gym_open_"), HasPermission("gym"))
async def gym_open_session(callback: types.CallbackQuery):
    session_id = int(callback.data.replace("gym_open_", ""))
    async with AsyncSessionLocal() as session:
        ws = await session.get(WorkoutSession, session_id)
    if not ws:
        return await callback.answer("Тренування не знайдено.", show_alert=True)
    await _render_exercise_list(callback.message, session_id, ws.day_key, edit=True)
    await callback.answer()


# ==========================================
# СПИСОК ВПРАВ ДНЯ
# ==========================================
async def _render_exercise_list(message: types.Message, session_id: int, day_key: str, edit: bool):
    day = WORKOUT_PROGRAM[day_key]
    builder = InlineKeyboardBuilder()

    async with AsyncSessionLocal() as session:
        all_done = True
        for ex in day["exercises"]:
            done_sets = await _get_sets_done(session, session_id, ex["key"])
            done_count = len(done_sets)
            total = ex["sets"]
            mark = "✅" if done_count >= total else f"{done_count}/{total}"
            if done_count < total:
                all_done = False
            builder.button(
                text=f"{mark} {ex['name']}",
                callback_data=f"gym_ex_{session_id}_{ex['key']}",
            )

    builder.button(text="🏁 Завершити тренування", callback_data=f"gym_finish_{session_id}")
    builder.adjust(1)

    text = f"🏋️ <b>{day['title']}</b>\n\nОбери вправу:"
    if all_done:
        text += "\n\n🎉 Всі вправи виконано — можна завершувати!"

    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("gym_ex_"), HasPermission("gym"))
async def gym_show_exercise(callback: types.CallbackQuery):
    _, _, session_id_str, exercise_key = callback.data.split("_", 3)
    session_id = int(session_id_str)
    await _render_set_prompt(callback.message, session_id, exercise_key, callback.from_user.id, edit=True)
    await callback.answer()


# ==========================================
# ЕКРАН "ЗАПИСАТИ ПІДХІД"
# ==========================================
async def _render_set_prompt(message: types.Message, session_id: int, exercise_key: str, user_id: int, edit: bool):
    ex_name = get_exercise_name(exercise_key)

    async with AsyncSessionLocal() as session:
        ws = await session.get(WorkoutSession, session_id)
        day = WORKOUT_PROGRAM[ws.day_key]
        ex_def = next(e for e in day["exercises"] if e["key"] == exercise_key)

        done_sets = await _get_sets_done(session, session_id, exercise_key)
        next_set_number = len(done_sets) + 1
        last_set = await _get_last_set_for_exercise(session, user_id, exercise_key, exclude_session_id=session_id)

    text = f"💪 <b>{ex_name}</b>\nЦільові повтори: {ex_def['reps']}\n\n"

    if done_sets:
        lines = "\n".join(f"  Підхід {s.set_number}: {s.weight_kg:g}кг × {s.reps}" for s in done_sets)
        text += f"Вже зроблено:\n{lines}\n\n"

    if next_set_number > ex_def["sets"]:
        text += "✅ Усі підходи по цій вправі виконано!"
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Додати ще підхід", callback_data=f"gym_manual_{session_id}_{exercise_key}")
        builder.button(text="🔙 До списку вправ", callback_data=f"gym_open_{session_id}")
    else:
        text += f"▶️ Підхід {next_set_number}/{ex_def['sets']} — скільки і з якою вагою?"
        builder = InlineKeyboardBuilder()
        if last_set:
            builder.button(
                text=f"🔁 Як минулого разу ({last_set.weight_kg:g}кг × {last_set.reps})",
                callback_data=f"gym_repeat_{session_id}_{exercise_key}",
            )
        builder.button(text="✏️ Ввести вручну", callback_data=f"gym_manual_{session_id}_{exercise_key}")
        builder.button(text="🔙 До списку вправ", callback_data=f"gym_open_{session_id}")

    builder.adjust(1)

    if edit:
        await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("gym_repeat_"), HasPermission("gym"))
async def gym_repeat_last(callback: types.CallbackQuery, bot: Bot):
    _, _, session_id_str, exercise_key = callback.data.split("_", 3)
    session_id = int(session_id_str)
    uid = callback.from_user.id

    async with AsyncSessionLocal() as session:
        last_set = await _get_last_set_for_exercise(session, uid, exercise_key, exclude_session_id=session_id)
        if not last_set:
            return await callback.answer("Немає попереднього результату.", show_alert=True)

        done_sets = await _get_sets_done(session, session_id, exercise_key)
        set_number = len(done_sets) + 1

        session.add(WorkoutSet(
            session_id=session_id, exercise_key=exercise_key,
            set_number=set_number, weight_kg=last_set.weight_kg, reps=last_set.reps,
        ))
        await session.commit()

    asyncio.create_task(sheets_sync.sync_set_logged(
        session_id, exercise_key, get_exercise_name(exercise_key), set_number, last_set.weight_kg, last_set.reps,
    ))

    text, markup, is_pr = await _build_set_logged_view(uid, session_id, exercise_key, last_set.weight_kg, last_set.reps)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer("Рекорд! 🔥" if is_pr else "Записано 💪")


@router.callback_query(F.data.startswith("gym_rest_wait_"))
async def gym_rest_timer(callback: types.CallbackQuery, bot: Bot):
    asyncio.create_task(_rest_timer(callback.message.chat.id, bot, 90))
    await callback.answer("⏱ Таймер на 90с запущено, напишу коли час!", show_alert=False)


@router.callback_query(F.data.startswith("gym_manual_"), HasPermission("gym"))
async def gym_manual_entry(callback: types.CallbackQuery, state: FSMContext):
    _, _, session_id_str, exercise_key = callback.data.split("_", 3)
    await state.set_state(GymState.waiting_for_set_input)
    await state.update_data(session_id=int(session_id_str), exercise_key=exercise_key, msg_id=callback.message.message_id)

    await callback.message.edit_text(
        f"✏️ Напиши вагу і повтори, наприклад: <code>60 8</code> або <code>60x8</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(GymState.waiting_for_set_input, HasPermission("gym"))
async def gym_process_manual_set(message: types.Message, state: FSMContext, bot: Bot):
    parsed = _parse_weight_reps(message.text)
    if not parsed:
        return await message.answer("Не зрозумів формат. Напиши так: <code>60 8</code> (вага пробіл повтори)", parse_mode="HTML")

    weight, reps = parsed
    data = await state.get_data()
    session_id, exercise_key = data["session_id"], data["exercise_key"]

    async with AsyncSessionLocal() as session:
        done_sets = await _get_sets_done(session, session_id, exercise_key)
        set_number = len(done_sets) + 1
        session.add(WorkoutSet(
            session_id=session_id, exercise_key=exercise_key,
            set_number=set_number, weight_kg=weight, reps=reps,
        ))
        await session.commit()

    asyncio.create_task(sheets_sync.sync_set_logged(
        session_id, exercise_key, get_exercise_name(exercise_key), set_number, weight, reps,
    ))

    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass

    text, markup, is_pr = await _build_set_logged_view(message.from_user.id, session_id, exercise_key, weight, reps)
    sent = await message.answer(text, reply_markup=markup, parse_mode="HTML")


async def _build_set_logged_view(user_id: int, session_id: int, exercise_key: str, weight: float, reps: int):
    """Чисто формує (текст, клавіатура, чи це рекорд) — без прив'язки до
    callback чи message, щоб використовувати і після кнопки, і після ручного вводу."""
    async with AsyncSessionLocal() as session:
        is_pr = await _is_personal_record(session, user_id, exercise_key, weight, reps)

    pr_text = "\n\n🔥 <b>Новий особистий рекорд!</b>" if is_pr else ""
    ex_name = get_exercise_name(exercise_key)

    builder = InlineKeyboardBuilder()
    builder.button(text="⏱ 90с відпочинку", callback_data=f"gym_rest_wait_{session_id}")
    builder.button(text="➡️ Наступний підхід", callback_data=f"gym_ex_{session_id}_{exercise_key}")
    builder.button(text="🔙 До списку вправ", callback_data=f"gym_open_{session_id}")
    builder.adjust(1)

    text = f"✅ Записано: <b>{ex_name}</b> — {weight:g}кг × {reps}{pr_text}"
    return text, builder.as_markup(), is_pr


# ==========================================
# ЗАВЕРШЕННЯ ТРЕНУВАННЯ
# ==========================================
@router.callback_query(F.data.startswith("gym_finish_"), HasPermission("gym"))
async def gym_finish(callback: types.CallbackQuery):
    session_id = int(callback.data.replace("gym_finish_", ""))

    async with AsyncSessionLocal() as session:
        ws = await session.get(WorkoutSession, session_id)
        ws.finished_at = datetime.utcnow()
        total_sets = (await session.execute(
            select(func.count(WorkoutSet.id)).where(WorkoutSet.session_id == session_id)
        )).scalar_one()
        day_title = WORKOUT_PROGRAM[ws.day_key]["title"]
        await session.commit()

    asyncio.create_task(sheets_sync.sync_session(
        session_id, ws.user_id, ws.day_key, day_title, ws.started_at, ws.finished_at,
    ))

    duration_min = int((ws.finished_at - ws.started_at).total_seconds() // 60)
    await callback.message.edit_text(
        f"🏆 <b>Тренування «{day_title}» завершено!</b>\n"
        f"Тривалість: {duration_min} хв\nЗаписано підходів: {total_sets}\n\n"
        f"Гарного відновлення 💪",
        parse_mode="HTML",
    )
    await callback.answer()


# ==========================================
# ІСТОРІЯ ТРЕНУВАНЬ
# ==========================================
@router.callback_query(F.data == "gym_history", HasPermission("gym"))
async def gym_history(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(WorkoutSession).where(
            WorkoutSession.user_id == callback.from_user.id,
            WorkoutSession.finished_at.isnot(None),
        ).order_by(WorkoutSession.started_at.desc()).limit(10)
        sessions_list = (await session.execute(stmt)).scalars().all()

    if not sessions_list:
        await callback.answer("Ще немає завершених тренувань.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for ws in sessions_list:
        title = WORKOUT_PROGRAM[ws.day_key]["title"]
        date_str = ws.started_at.strftime("%d.%m.%Y")
        builder.button(text=f"{date_str} — {title}", callback_data=f"gym_hist_view_{ws.id}")
    builder.adjust(1)

    await callback.message.edit_text("📊 <b>Останні тренування:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("gym_hist_view_"), HasPermission("gym"))
async def gym_history_view(callback: types.CallbackQuery):
    session_id = int(callback.data.replace("gym_hist_view_", ""))

    async with AsyncSessionLocal() as session:
        ws = await session.get(WorkoutSession, session_id)
        stmt = select(WorkoutSet).where(WorkoutSet.session_id == session_id).order_by(WorkoutSet.exercise_key, WorkoutSet.set_number)
        all_sets = (await session.execute(stmt)).scalars().all()

    by_exercise: dict[str, list[WorkoutSet]] = {}
    for s in all_sets:
        by_exercise.setdefault(s.exercise_key, []).append(s)

    title = WORKOUT_PROGRAM[ws.day_key]["title"]
    date_str = ws.started_at.strftime("%d.%m.%Y")
    text = f"📅 <b>{title} — {date_str}</b>\n\n"

    for ex_key, sets_list in by_exercise.items():
        name = get_exercise_name(ex_key)
        sets_str = ", ".join(f"{s.weight_kg:g}×{s.reps}" for s in sets_list)
        text += f"• <b>{name}</b>: {sets_str}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 До історії", callback_data="gym_history")
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==========================================
# ВІДНОВЛЕННЯ БАЗИ З GOOGLE SHEETS (тільки адмін)
# ==========================================
@router.message(Command("gym_restore"))
async def cmd_gym_restore(message: types.Message):
    if message.from_user.id != ALLOWED_USER_ID:
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Так, перезаписати", callback_data="gym_restore_confirm")
    builder.button(text="❌ Скасувати", callback_data="gym_restore_cancel")
    builder.adjust(1)

    await message.answer(
        "⚠️ <b>Увага!</b>\nЦе видалить усю локальну історію тренувань і завантажить "
        "її заново з Google Sheets. Робити це варто, лише якщо локальна база "
        "справді загублена (наприклад, після переустановки сервера).\n\nПродовжити?",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "gym_restore_cancel")
async def gym_restore_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("Скасовано, локальна база не змінена.")
    await callback.answer()


@router.callback_query(F.data == "gym_restore_confirm")
async def gym_restore_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID:
        return await callback.answer()

    await callback.message.edit_text("⏳ Завантажую дані з Google Sheets...")

    result = await sheets_sync.restore_from_sheets()
    if result is None:
        return await callback.message.edit_text(
            "❌ Google Sheets синхронізація не налаштована або недоступна.\n"
            "Перевір GOOGLE_SHEETS_ID / GOOGLE_SHEETS_CREDS_PATH в .env."
        )

    sessions_rows, sets_rows = result
    if not sessions_rows:
        return await callback.message.edit_text("⚠️ У таблиці ще немає жодного запису — нічого відновлювати.")

    async with AsyncSessionLocal() as session:
        # Повністю очищаємо локальні таблиці перед відновленням
        await session.execute(delete(WorkoutSet))
        await session.execute(delete(WorkoutSession))

        for row in sessions_rows:
            finished_raw = row.get("finished_at") or ""
            session.add(WorkoutSession(
                id=int(row["session_id"]),
                user_id=int(row["user_id"]),
                day_key=row["day_key"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=datetime.fromisoformat(finished_raw) if finished_raw else None,
            ))

        for row in sets_rows:
            session.add(WorkoutSet(
                session_id=int(row["session_id"]),
                exercise_key=row["exercise_key"],
                set_number=int(row["set_number"]),
                weight_kg=float(row["weight_kg"]),
                reps=int(row["reps"]),
                created_at=datetime.fromisoformat(row["logged_at"]) if row.get("logged_at") else datetime.utcnow(),
            ))

        await session.commit()

    await callback.message.edit_text(
        f"✅ <b>Відновлено!</b>\nТренувань: {len(sessions_rows)}\nПідходів: {len(sets_rows)}\n\n"
        f"<i>Примітка: лічильник автоматичної ротації днів (next_workout_index) не зберігався "
        f"в Sheets — за потреби обери день вручну через '🔀 Обрати інший день'.</i>",
        parse_mode="HTML",
    )
    await callback.answer("Готово!")