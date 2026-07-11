# FILE: ./bot/handlers_calendar.py
from datetime import datetime, timedelta

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete

from database.engine import AsyncSessionLocal
from database.models import CalendarEvent
from bot.security import HasPermission, IsApproved

router = Router()


class EventState(StatesGroup):
    waiting_for_name = State()


@router.message(F.text == "📅 Календар", HasPermission("calendar"))
async def calendar_menu(message: types.Message):
    """
    ВИПРАВЛЕНО: сама кнопка "📅 Календар" в reply-клавіатурі раніше ніде не
    оброблялась — тому натискання не робило нічого (текст просто йшов у
    ignore-список загального catch-all хендлера і на цьому все закінчувалось).
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати подію", callback_data="cal_add_event")
    builder.button(text="📋 Мої події", callback_data="cal_list_events")
    builder.adjust(1)
    await message.answer("📅 <b>Календар</b>", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "cal_add_event", HasPermission("calendar"))
async def cal_add_event_button(callback: types.CallbackQuery):
    await callback.message.edit_text("📅 Обери дату події:", reply_markup=await SimpleCalendar().start_calendar())
    await callback.answer()


@router.message(Command("add_event"), HasPermission("calendar"))
async def cmd_add_event(message: types.Message):
    await message.answer("📅 Обери дату події:", reply_markup=await SimpleCalendar().start_calendar())


@router.callback_query(SimpleCalendarCallback.filter(), HasPermission("calendar"))
async def process_calendar(callback: types.CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    calendar = SimpleCalendar(show_alerts=True)
    selected, date = await calendar.process_selection(callback, callback_data)

    if selected:
        await state.update_data(event_date=date)
        await state.set_state(EventState.waiting_for_name)
        await callback.message.answer(
            f"Дата <b>{date.strftime('%d.%m.%Y')}</b> обрана.\nВведи назву події в чат:",
            parse_mode="HTML",
        )


@router.message(EventState.waiting_for_name, HasPermission("calendar"))
async def process_event_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    event_date = data["event_date"]

    async with AsyncSessionLocal() as session:
        # ВИПРАВЛЕНО: раніше тут не зберігався user_id, а в моделі це поле
        # nullable=False — тому раніше подія просто не могла зберегтися
        # (падіння з IntegrityError при commit).
        new_event = CalendarEvent(
            user_id=message.from_user.id,
            title=message.text,
            event_date=event_date,
            daily_reminder=True,
            confirmed=False,
        )
        session.add(new_event)
        await session.commit()

    await state.clear()

    days_left = (event_date.date() - datetime.now().date()).days
    days_text = f"Це через {days_left} дн. — щодня нагадуватиму, а ввечері напередодні попрошу підтвердити." if days_left > 0 else "Це сьогодні!"

    await message.answer(
        f"✅ Подію <b>«{message.text}»</b> на {event_date.strftime('%d.%m.%Y')} збережено.\n{days_text}",
        parse_mode="HTML",
    )


async def _build_events_list(user_id: int) -> tuple[str, InlineKeyboardBuilder | None]:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(CalendarEvent)
            .where(
                CalendarEvent.event_date >= today,
                CalendarEvent.user_id == user_id,
                CalendarEvent.is_archived == False,
            )
            .order_by(CalendarEvent.event_date)
            .limit(15)
        )
        events = (await session.execute(stmt)).scalars().all()

    if not events:
        return "📅 На найближчий час подій не заплановано.", None

    builder = InlineKeyboardBuilder()
    text = "📅 <b>Твій план:</b>\n\n"

    for e in events:
        days_left = (e.event_date.date() - datetime.now().date()).days
        if days_left == 0:
            when = "сьогодні"
        elif days_left == 1:
            when = "завтра"
        else:
            when = f"через {days_left} дн."

        if days_left <= 1:
            status = "✅ підтверджено" if e.confirmed else "⏳ очікує підтвердження"
            text += f"• <b>{e.event_date.strftime('%d.%m %H:%M')}</b> ({when}) — {e.title}\n  {status}\n"
        else:
            text += f"• <b>{e.event_date.strftime('%d.%m')}</b> ({when}) — {e.title}\n"

        builder.button(text=f"❌ {e.title[:12]}...", callback_data=f"delevent_{e.id}")

    builder.adjust(2)
    return text, builder


@router.message(Command("events"), HasPermission("calendar"))
async def cmd_list_events(message: types.Message):
    text, builder = await _build_events_list(message.from_user.id)
    await message.answer(text, reply_markup=builder.as_markup() if builder else None, parse_mode="HTML")


@router.callback_query(F.data == "cal_list_events", HasPermission("calendar"))
async def cal_list_events_button(callback: types.CallbackQuery):
    text, builder = await _build_events_list(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=builder.as_markup() if builder else None, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("delevent_"), HasPermission("calendar"))
async def process_del_event(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CalendarEvent).where(CalendarEvent.id == event_id))
        await session.commit()

    await callback.message.edit_text(
        callback.message.html_text + "\n\n<i>Оновлено: подію скасовано.</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer("Видалено!")


# ==========================================
# ПІДТВЕРДЖЕННЯ "Я ПАМ'ЯТАЮ" (вечірній нагадувач)
# ==========================================
@router.callback_query(F.data.startswith("event_confirm_"))
async def process_event_confirm(callback: types.CallbackQuery):
    event_id = int(callback.data.replace("event_confirm_", ""))
    async with AsyncSessionLocal() as session:
        event = await session.get(CalendarEvent, event_id)
        if not event:
            return await callback.answer("Подію вже видалено.", show_alert=True)

        event.confirmed = True
        event.reminder_stage = 0
        await session.commit()

        await callback.message.edit_text(
            f"✅ <b>Супер, підтверджено!</b>\n«{event.title}» — {event.event_date.strftime('%d.%m %H:%M')}",
            parse_mode="HTML",
        )
    await callback.answer("Записано, більше не турбуватиму 👍")


@router.callback_query(F.data.startswith("event_snooze_"))
async def process_event_snooze(callback: types.CallbackQuery):
    event_id = int(callback.data.replace("event_snooze_", ""))
    async with AsyncSessionLocal() as session:
        event = await session.get(CalendarEvent, event_id)
        if not event:
            return await callback.answer("Подію вже видалено.", show_alert=True)

        event.reminder_stage += 1
        event.last_reminder_at = datetime.utcnow()
        await session.commit()

    await callback.message.edit_text(
        callback.message.html_text + "\n\n<i>🔁 Гаразд, нагадаю ще раз пізніше.</i>",
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.answer("Нагадаю пізніше")