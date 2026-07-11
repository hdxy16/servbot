# FILE: ./bot/handlers.py
import re
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ButtonStyle
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, delete

from database.engine import UsersSessionLocal as AsyncSessionLocal
from database.models import User, CalendarEvent
from config import ALLOWED_USER_ID
from bot.security import HasPermission, IsApproved

from bot.keyboards import (
    expense_categories_keyboard,
    expense_draft_keyboard,
    payees_keyboard,
    ha_main_keyboard,
    ha_lights_keyboard,
    ha_alarm_keyboard,
    main_reply_keyboard,
    ha_light_options_keyboard,
    settings_keyboard,
    budget_groups_keyboard,
    budget_back_keyboard,
)
from bot.home_assistant import ha_client
from bot.actual_api import add_expense_to_actual, get_budget_data, get_recent_payees
from bot.bus_logic import get_bus_info


logger = logging.getLogger(__name__)
router = Router()


# ==========================================
# 1. АВТОРИЗАЦІЯ ТА СИСТЕМА ДОСТУПУ
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username or "Невідомий"
    
    if user_id == ALLOWED_USER_ID:
        await message.answer(
            "🛠 <b>Вітаю, Адміністраторе!</b> Система готова до роботи.", 
            parse_mode="HTML", 
            reply_markup=main_reply_keyboard()
        )
        return

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        
        if not user:
            new_user = User(telegram_id=user_id, username=username, is_approved=False)
            session.add(new_user)
            await session.commit()
            
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Схвалити", callback_data=f"auth_approve_{user_id}")
            kb.button(text="❌ Заборонити", callback_data=f"auth_deny_{user_id}")
            
            await bot.send_message(
                ALLOWED_USER_ID, 
                f"🚨 <b>Новий запит доступу!</b>\nКористувач: @{username} (ID: <code>{user_id}</code>)",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            await message.answer("👋 Запит надіслано адміністратору. Очікуйте на підтвердження.")
            return

        if not user.is_approved:
            await message.answer("⏳ Ваш запит ще розглядається адміністратором.")
            return
            
        await message.answer("✅ Ласкаво просимо! У вас є доступ до бота.", reply_markup=main_reply_keyboard())

@router.callback_query(F.data.startswith("auth_approve_"))
async def process_approve(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ALLOWED_USER_ID: return
    
    target_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, target_id)
        if user:
            user.is_approved = True
            await session.commit()
            try:
                await bot.send_message(target_id, "🎉 Адміністратор надав вам доступ! Введіть /start")
            except Exception:
                pass
            await open_permission_panel(callback, target_id, session)

@router.callback_query(F.data.startswith("auth_deny_"))
async def process_deny(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ALLOWED_USER_ID: return
    
    target_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, target_id)
        if user:
            session.delete(user)
            await session.commit()
            try:
                await bot.send_message(target_id, "❌ Адміністратор відхилив ваш запит.")
            except Exception:
                pass
            await callback.message.edit_text(f"❌ Запит від ID <code>{target_id}</code> відхилено.", parse_mode="HTML")

async def open_permission_panel(callback: types.CallbackQuery, target_id: int, session):
    user = await session.get(User, target_id)
    if not user: return
    
    kb = InlineKeyboardBuilder()
    perms = user.permissions
    
    kb.button(
        text=f"{'✅' if perms.get('finance') else '❌'} Фінанси",
        callback_data=f"perm_toggle_{target_id}_finance"
    )
    kb.button(
        text=f"{'✅' if perms.get('calendar') else '❌'} Календар",
        callback_data=f"perm_toggle_{target_id}_calendar"
    )
    kb.button(
        text=f"{'✅' if perms.get('ha_light') else '❌'} Світло",
        callback_data=f"perm_toggle_{target_id}_ha_light"
    )
    kb.button(
        text=f"{'✅' if perms.get('ha_climate') else '❌'} Клімат",
        callback_data=f"perm_toggle_{target_id}_ha_climate"
    )
    kb.button(
        text=f"{'✅' if perms.get('ha_alarm') else '❌'} Будильник",
        callback_data=f"perm_toggle_{target_id}_ha_alarm"
    )
    kb.button(
        text=f"{'✅' if perms.get('bus') else '❌'} Автобуси",
        callback_data=f"perm_toggle_{target_id}_bus"
    )
    kb.button(
        text=f"{'✅' if perms.get('wifi') else '❌'} Мережа",
        callback_data=f"perm_toggle_{target_id}_wifi"
    )
    kb.button(
        text=f"{'✅' if perms.get('gym') else '❌'} Спортзал",
        callback_data=f"perm_toggle_{target_id}_gym"
    )
    kb.adjust(2)
    
    await callback.message.edit_text(
        f"⚙️ <b>Налаштування прав: @{user.username}</b> (ID: <code>{target_id}</code>)\n"
        f"<i>Натискайте кнопки, щоб увімкнути/вимкнути доступ.</i>",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith("perm_toggle_"))
async def process_perm_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID: return
    
    parts = callback.data.split("_")
    target_id = int(parts[2])
    perm_key = "_".join(parts[3:]) 
    
    async with AsyncSessionLocal() as session:
        user = await session.get(User, target_id)
        if user:
            new_perms = dict(user.permissions)
            new_perms[perm_key] = not new_perms.get(perm_key, False)
            user.permissions = new_perms
            await session.commit()
            await open_permission_panel(callback, target_id, session)

@router.message(F.text == "👥 Користувачі", IsApproved())
async def users_menu_button(message: types.Message):
    # ВИПРАВЛЕНО: та сама проблема, що й з "📅 Календар" — кнопка існувала
    # в клавіатурі, але не була підключена до жодного обробника.
    await cmd_users(message)


@router.message(Command("users"), IsApproved())
async def cmd_users(message: types.Message):
    if message.from_user.id != ALLOWED_USER_ID: 
        return
        
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        
        if not users:
            return await message.answer("База користувачів порожня.")
            
        kb = InlineKeyboardBuilder()
        for u in users:
            if u.telegram_id == ALLOWED_USER_ID: 
                continue 
                
            status = "✅" if u.is_approved else "⏳"
            name = u.username or str(u.telegram_id)
            kb.button(text=f"{status} {name}", callback_data=f"edit_user_{u.telegram_id}")
            
        kb.adjust(1)
        await message.answer(
            "👥 <b>Керування користувачами:</b>\n<i>Оберіть гостя для налаштування прав:</i>", 
            reply_markup=kb.as_markup(), 
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("edit_user_"))
async def process_edit_user(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID: 
        return
        
    target_id = int(callback.data.replace("edit_user_", ""))
    async with AsyncSessionLocal() as session:
        await open_permission_panel(callback, target_id, session)

# ==========================================
# 2. НАЛАШТУВАННЯ СПОВІЩЕНЬ
# ==========================================
@router.message(F.text == "⚙️ Налаштування", IsApproved())
async def settings_menu_button(message: types.Message):
    # ВИПРАВЛЕНО: та сама проблема, що й з "📅 Календар"/"👥 Користувачі" —
    # кнопка була в клавіатурі, але ніде не підключена до обробника.
    await cmd_settings(message)


@router.message(Command("settings"), IsApproved())
async def cmd_settings(message: types.Message):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        await message.answer(
            "⚙️ <b>Налаштування сповіщень:</b>",
            reply_markup=settings_keyboard(user.notify_finance, user.notify_calendar, user.notify_climate),
            parse_mode="HTML",
        )

@router.callback_query(F.data.startswith("toggle_notify_"), IsApproved())
async def process_toggle_notify(callback: types.CallbackQuery):
    param = callback.data.replace("toggle_notify_", "")
    
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        if param == "finance":
            user.notify_finance = not user.notify_finance
        elif param == "calendar":
            user.notify_calendar = not user.notify_calendar
        elif param == "climate":
            user.notify_climate = not user.notify_climate

        await session.commit()
        await callback.message.edit_reply_markup(
            reply_markup=settings_keyboard(user.notify_finance, user.notify_calendar, user.notify_climate)
        )
        await callback.answer("Змінено!")

# ==========================================
# 3. ДОДАВАННЯ ВИТРАТ (FSM)
# ==========================================
class ExpenseFSM(StatesGroup):
    waiting_for_category = State()
    draft = State()
    waiting_for_payee = State()
    waiting_for_notes = State()

active_draft_timers = {}

async def render_draft_message(data: dict) -> str:
    return (
        f"📝 <b>Чернетка витрати</b>\n"
        f"💰 Сума: <b>{data.get('amount')}€</b>\n"
        f"📁 Категорія: <b>{data.get('category', '[Очікує вибору]')}</b>\n"
        f"👤 Отримувач: <b>{data.get('payee')}</b>\n"
        f"🏷 Примітка: <b>{data.get('notes')}</b>\n\n"
        f"⏳ <i>Відправиться автоматично через 30 секунд...</i>"
    )

async def execute_submit(chat_id: int, state: FSMContext, bot: Bot, msg_id: int):
    data = await state.get_data()
    if not data or "amount" not in data: return
    await state.clear()
    
    try:
        await bot.edit_message_text("🔄 Синхронізація з Actual Budget...", chat_id=chat_id, message_id=msg_id)
    except TelegramBadRequest:
        pass

    result_text = await add_expense_to_actual(
        amount=data["amount"], category=data["category"], payee=data["payee"], notes=data["notes"]
    )
    try:
        await bot.edit_message_text(result_text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
    except TelegramBadRequest:
        pass

async def auto_submit_task(chat_id: int, state: FSMContext, bot: Bot, msg_id: int):
    try:
        await asyncio.sleep(30)
        current_state = await state.get_state()
        if current_state == ExpenseFSM.draft.state:
            await execute_submit(chat_id, state, bot, msg_id)
    except asyncio.CancelledError:
        pass

def restart_timer(chat_id: int, state: FSMContext, bot: Bot, msg_id: int):
    if chat_id in active_draft_timers:
        active_draft_timers[chat_id].cancel()
    active_draft_timers[chat_id] = asyncio.create_task(auto_submit_task(chat_id, state, bot, msg_id))

@router.message(F.text.regexp(r"^(\d+[.,]?\d*)(?:#(.*))?$"), HasPermission("finance"))
async def new_expense_trigger(message: types.Message, state: FSMContext, bot: Bot):
    match = re.match(r"^(\d+[.,]?\d*)(?:#(.*))?$", message.text)
    amount = float(match.group(1).replace(",", "."))
    initial_notes = (match.group(2) or "").strip() or "[Не вказано]"

    await state.update_data(amount=amount, notes=initial_notes, payee="[Не вказано]", category=None)
    await state.set_state(ExpenseFSM.waiting_for_category)
    msg = await message.answer(f"💰 Сума: {amount}€\n📁 Оберіть категорію:", reply_markup=expense_categories_keyboard())
    await state.update_data(msg_id=msg.message_id)

@router.callback_query(ExpenseFSM.waiting_for_category, F.data.startswith("expcat_"), HasPermission("finance"))
async def process_category_selection(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(category=callback.data.split("_")[1])
    await state.set_state(ExpenseFSM.draft)
    data = await state.get_data()
    text = await render_draft_message(data)
    await callback.message.edit_text(text, reply_markup=expense_draft_keyboard(), parse_mode="HTML")
    restart_timer(callback.message.chat.id, state, bot, callback.message.message_id)
    await callback.answer()

@router.callback_query(ExpenseFSM.draft, F.data == "exp_submit", HasPermission("finance"))
async def manual_submit(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    chat_id = callback.message.chat.id
    if chat_id in active_draft_timers:
        active_draft_timers[chat_id].cancel()
    await execute_submit(chat_id, state, bot, callback.message.message_id)
    await callback.answer()

@router.callback_query(ExpenseFSM.draft, F.data == "exp_cancel", HasPermission("finance"))
async def manual_cancel(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id in active_draft_timers:
        active_draft_timers[chat_id].cancel()
    await state.clear()
    await callback.message.edit_text("❌ Витрату скасовано.")
    await callback.answer()

@router.callback_query(ExpenseFSM.draft, F.data == "exp_set_payee", HasPermission("finance"))
async def trigger_set_payee(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id in active_draft_timers:
        active_draft_timers[chat_id].cancel()
    await state.set_state(ExpenseFSM.waiting_for_payee)
    await callback.message.edit_text("⏳ Завантажую список отримувачів...")
    payees = await get_recent_payees()
    await callback.message.edit_text("👤 Оберіть зі списку або напишіть в чат:", reply_markup=payees_keyboard(payees))
    await callback.answer()

@router.callback_query(ExpenseFSM.waiting_for_payee, F.data.startswith("setpayee_"), HasPermission("finance"))
async def process_inline_payee(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await state.update_data(payee=callback.data.split("_")[1])
    await return_to_draft(callback.message.chat.id, state, bot)
    await callback.answer()

@router.message(ExpenseFSM.waiting_for_payee, HasPermission("finance"))
async def process_text_payee(message: types.Message, state: FSMContext, bot: Bot):
    await state.update_data(payee=message.text.strip())
    await message.delete()
    await return_to_draft(message.chat.id, state, bot)

@router.callback_query(ExpenseFSM.draft, F.data == "exp_set_notes", HasPermission("finance"))
async def trigger_set_notes(callback: types.CallbackQuery, state: FSMContext):
    chat_id = callback.message.chat.id
    if chat_id in active_draft_timers:
        active_draft_timers[chat_id].cancel()
    await state.set_state(ExpenseFSM.waiting_for_notes)
    await callback.message.edit_text("🏷 Напишіть нотатку в чат:", reply_markup=payees_keyboard([]))
    await callback.answer()

@router.message(ExpenseFSM.waiting_for_notes, HasPermission("finance"))
async def process_text_notes(message: types.Message, state: FSMContext, bot: Bot):
    await state.update_data(notes=message.text.strip())
    await message.delete()
    await return_to_draft(message.chat.id, state, bot)

@router.callback_query(F.data == "exp_back_to_draft", HasPermission("finance"))
async def go_back_to_draft(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await return_to_draft(callback.message.chat.id, state, bot)
    await callback.answer()

async def return_to_draft(chat_id: int, state: FSMContext, bot: Bot):
    await state.set_state(ExpenseFSM.draft)
    data = await state.get_data()
    msg_id = data.get("msg_id")
    if msg_id is None: return
    text = await render_draft_message(data)
    await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=expense_draft_keyboard(), parse_mode="HTML")
    restart_timer(chat_id, state, bot, msg_id)

# ==========================================
# 4. ФІНАНСОВА АНАЛІТИКА
# ==========================================
@router.message(F.text == "📊 Фінанси", HasPermission("finance"))
async def process_menu_finance(message: types.Message):
    msg = await message.answer("🔄 Збираю інформацію з Actual Budget...")
    await render_budget_main(msg)

@router.callback_query(F.data == "budget_refresh", HasPermission("finance"))
async def process_budget_refresh(callback: types.CallbackQuery):
    await render_budget_main(callback.message)
    await callback.answer()

async def render_budget_main(msg: types.Message):
    data = await get_budget_data()
    if not data:
        return await msg.edit_text("❌ Помилка завантаження бюджету. Спробуйте пізніше.")
    text = (
        f"📊 <b>Фінансовий звіт | {data['month']}</b>\n\n"
        f"💰 <b>Загальний вільний залишок: {data['total_balance']:.2f}€</b>\n\n"
        f"<i>👇 Оберіть групу категорій:</i>"
    )
    await msg.edit_text(text, reply_markup=budget_groups_keyboard(list(data["groups"].keys())), parse_mode="HTML")

@router.callback_query(F.data.startswith("bgroup_"), HasPermission("finance"))
async def process_budget_group(callback: types.CallbackQuery):
    group_name = callback.data.replace("bgroup_", "")
    data = await get_budget_data()
    if not data or group_name not in data["groups"]:
        return await callback.answer("Дані застаріли, оновіть.", show_alert=True)

    group = data["groups"][group_name]
    text = f"📂 <b>{group_name.upper()}</b>\nВільний залишок: <b>{group['balance']:.2f}€</b>\n"
    
    budgeted = group["budgeted"]
    spent = abs(group["spent"])
    if budgeted > 0: text += f"<i>(Витрачено {spent:.2f}€ з {budgeted:.2f}€)</i>\n\n"
    else: text += f"<i>(Витрачено {spent:.2f}€)</i>\n\n"

    for cat in group["categories"]:
        c_spent = abs(cat["spent"])
        c_budget = cat["budgeted"]
        c_bal = cat["balance"]
        icon = "🟢" if c_bal >= 0 else "🔴"
        text += f"{icon} <b>{cat['name']}</b>: {c_bal:.2f}€\n"
        
        if c_budget > 0:
            ratio = min(c_spent / c_budget, 1.0)
            filled = int(round(ratio * 10))
            bar = "█" * filled + "░" * (10 - filled)
            text += f"<code>[{bar}]</code> <i>{c_spent:.2f} / {c_budget:.2f}</i>\n\n"
        else:
            text += f"<code>[〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️]</code> <i>{c_spent:.2f} (без ліміту)</i>\n\n"

    await callback.message.edit_text(text, reply_markup=budget_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# 5. HOME ASSISTANT
# ==========================================
@router.message(F.text == "🎛 Розумний дім", IsApproved())
async def process_menu_ha(message: types.Message):
    await message.answer("🏠 <b>Home Assistant</b>", reply_markup=ha_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "ha_main_menu", IsApproved())
async def process_ha_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>Home Assistant</b>", reply_markup=ha_main_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "ha_sensors", HasPermission("ha_climate"))
async def process_ha_sensors(callback: types.CallbackQuery):
    k_t = (await ha_client.get_entity_state("sensor.kitchen_sensor_climate_temperature")).get("state", "Н/Д")
    k_h = (await ha_client.get_entity_state("sensor.kitchen_sensor_climate_humidity")).get("state", "Н/Д")
    b_t = (await ha_client.get_entity_state("sensor.bathroom_sensor_climate_temperature")).get("state", "Н/Д")
    b_h = (await ha_client.get_entity_state("sensor.bathroom_sensor_climate_humidity")).get("state", "Н/Д")
    text = f"🍳 <b>Кухня:</b> {k_t}°C | {k_h}%\n🛁 <b>Ванна:</b> {b_t}°C | {b_h}%"
    await callback.message.edit_text(text, reply_markup=ha_main_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "ha_lights", HasPermission("ha_light"))
async def process_ha_lights(callback: types.CallbackQuery):
    lights = [
        "light.bathroom_light_ceiling",
        "light.hallway_lights",
        "light.bedroom_light_floor",
        "light.livingroom_light_floor",
    ]
    states = {e: (await ha_client.get_entity_state(e)).get("state", "unknown") for e in lights}
    await callback.message.edit_text("💡 <b>Управління освітленням:</b>", reply_markup=ha_lights_keyboard(states), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("ha_toggle_"), HasPermission("ha_light"))
async def process_ha_toggle(callback: types.CallbackQuery):
    entity_id = callback.data.replace("ha_toggle_", "")
    ok = await ha_client.toggle_device(entity_id.split(".")[0], "toggle", entity_id)
    if not ok: await callback.answer("⚠️ Не вдалося зв'язатися з Home Assistant.", show_alert=True)
    await asyncio.sleep(0.5)
    await process_ha_lights(callback)

@router.callback_query(F.data.startswith("ha_opts_"), HasPermission("ha_light"))
async def process_ha_light_options(callback: types.CallbackQuery):
    entity_id = callback.data.replace("ha_opts_", "")
    await callback.message.edit_text("🎛 <b>Налаштування світла</b>", reply_markup=ha_light_options_keyboard(entity_id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("ha_set_"), HasPermission("ha_light"))
async def process_ha_light_set(callback: types.CallbackQuery):
    data = callback.data[len("ha_set_"):]
    ok = True
    if "_bri_" in data: ok = await ha_client.set_light_state(data.split("_bri_")[0], brightness_pct=int(data.split("_bri_")[1]))
    elif "_temp_" in data: ok = await ha_client.set_light_state(data.split("_temp_")[0], kelvin=int(data.split("_temp_")[1]))
    elif "_color_" in data: ok = await ha_client.set_light_state(data.split("_color_")[0], color_name=data.split("_color_")[1])
    await callback.answer("Застосовано" if ok else "⚠️ Помилка застосування", show_alert=not ok)

# ==========================================
# 6. РОЗУМНИЙ БУДИЛЬНИК
# ==========================================
class AlarmFSM(StatesGroup):
    waiting_for_time = State()
@router.callback_query(F.data == "ha_alarm", HasPermission("ha_alarm"))
async def process_ha_alarm(callback: types.CallbackQuery):
    enabled_state = await ha_client.get_entity_state("input_boolean.smart_alarm_enabled")
    time_state = await ha_client.get_entity_state("input_datetime.smart_alarm_time")
    is_enabled = enabled_state.get("state") == "on"
    current_time = time_state.get("state", "00:00:00")[:5]
    
    text = (
        f"⏰ <b>Розумний будильник</b>\n\nПоточний час: <b>{current_time}</b>\n"
        f"<i>Параметри: Плавний світанок починається за 20 хвилин до тригера.</i>"
    )
    await callback.message.edit_text(text, reply_markup=ha_alarm_keyboard(is_enabled, current_time), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("alarm_toggle_"), HasPermission("ha_alarm"))
async def process_alarm_toggle(callback: types.CallbackQuery):
    action = callback.data.replace("alarm_toggle_", "")
    await ha_client.toggle_alarm(action)
    await asyncio.sleep(0.5)
    await process_ha_alarm(callback)

@router.callback_query(F.data.startswith("alarm_set_"), HasPermission("ha_alarm"))
async def process_alarm_set(callback: types.CallbackQuery):
    time_str = callback.data.replace("alarm_set_", "")
    await ha_client.set_alarm_time(time_str)
    await ha_client.toggle_alarm("turn_on") 
    await asyncio.sleep(0.5)
    await process_ha_alarm(callback)
    await callback.answer(f"Будильник активовано на {time_str[:5]}")

@router.callback_query(F.data == "alarm_custom", HasPermission("ha_alarm"))
async def process_alarm_custom(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AlarmFSM.waiting_for_time)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    cancel_kb = InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="ha_alarm").as_markup()
    await callback.message.edit_text(
        "⏰ Введи час для будильника у форматі <b>ГГ:ХХ</b> (наприклад, <code>07:15</code>):",
        parse_mode="HTML", reply_markup=cancel_kb
    )
    await callback.answer()

@router.message(AlarmFSM.waiting_for_time, F.text.regexp(r"^([01]?\d|2[0-3]):([0-5]\d)$"), HasPermission("ha_alarm"))
async def process_alarm_custom_time(message: types.Message, state: FSMContext, bot: Bot):
    time_str = f"{message.text}:00"
    await ha_client.set_alarm_time(time_str)
    await ha_client.toggle_alarm("turn_on")
    await state.clear()
    
    await message.answer(f"✅ Будильник встановлено на <b>{message.text}</b>", parse_mode="HTML")
    text = (
        f"⏰ <b>Розумний будильник</b>\n\nПоточний час: <b>{message.text}</b>\n"
        f"<i>Параметри: Плавний світанок починається за 20 хвилин до тригера.</i>"
    )
    await message.answer(text, reply_markup=ha_alarm_keyboard(True, message.text), parse_mode="HTML")

@router.message(AlarmFSM.waiting_for_time, HasPermission("ha_alarm"))
async def process_alarm_custom_invalid(message: types.Message):
    await message.answer("❌ Невірний формат. Напиши час чітко у форматі <b>ГГ:ХХ</b>, наприклад <code>07:30</code>.", parse_mode="HTML")

@router.callback_query(F.data == "alarm_test", HasPermission("ha_alarm"))
async def process_alarm_test(callback: types.CallbackQuery):
    await ha_client.toggle_device("automation", "trigger", "automation.alarm_dzvinok_ta_blimannia")
    await callback.answer("🚨 Тест запущено! Перевіряй телефон та світло.", show_alert=True)

@router.callback_query(F.data == "ringing_turn_off", HasPermission("ha_alarm"))
async def process_ringing_turn_off(callback: types.CallbackQuery):
    await ha_client.toggle_alarm("turn_off")
    await callback.message.edit_text("🛑 <b>Будильник вимкнено.</b> Доброго ранку!", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("ringing_snooze_"), HasPermission("ha_alarm"))
async def process_ringing_snooze(callback: types.CallbackQuery):
    minutes = int(callback.data.replace("ringing_snooze_", ""))
    await ha_client.toggle_alarm("turn_off")
    time_state = await ha_client.get_entity_state("input_datetime.smart_alarm_time")
    current_time_str = time_state.get("state", "00:00:00")
    
    t = datetime.strptime(current_time_str, "%H:%M:%S")
    new_t = t + timedelta(minutes=minutes)
    new_time_str = new_t.strftime("%H:%M:%S")
    
    await ha_client.set_alarm_time(new_time_str)
    await ha_client.toggle_alarm("turn_on")
    
    await callback.message.edit_text(
        f"💤 <b>Відкладено на {minutes} хв.</b>\nНовий час: <b>{new_time_str[:5]}</b>\n<i>Дзвінок тимчасово зупинено.</i>",
        parse_mode="HTML"
    )
    await callback.answer()

# ==========================================
# 7. АВТОБУС
# ==========================================
@router.message(F.text == "🚌 Автобус", HasPermission("bus"))
async def process_bus(message: types.Message):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Додому", callback_data="bus_home")
    b.button(text="🏢 В центр", callback_data="bus_center")
    await message.answer("Обери напрямок:", reply_markup=b.as_markup())

@router.callback_query(F.data.startswith("bus_"), HasPermission("bus"))
async def bus_callback(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(text=get_bus_info(callback.data.split("_")[1]), reply_markup=callback.message.reply_markup)
    except TelegramBadRequest:
        pass
    await callback.answer()


async def _try_process_ha_command(message: types.Message) -> str | None:
    if not message.text:
        return None
    command = await ha_client.interpret_command(message.text)
    action = command.get("action")
    if not action:
        return None

    user_id = message.from_user.id
    if user_id != ALLOWED_USER_ID:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if not user or not user.is_approved:
                return None
            if action.startswith("light_") and not user.permissions.get("ha_light", False): return None
            if action == "sensor_read" and not user.permissions.get("ha_climate", False): return None
            if action.startswith("alarm_") and not user.permissions.get("ha_alarm", False): return None

    return await ha_client.execute_command(command)


# ВИПРАВЛЕНО: раніше цей catch-all відправляв будь-який текст в ollama/AI-пам'ять
# (видалену повністю). Залишено тільки регекс-розпізнавання текстових команд
# для Home Assistant (не є ШІ — просте keyword-парсення в home_assistant.py).
@router.message(F.text, IsApproved())
async def handle_text_ha_command(message: types.Message):
    if message.text.startswith("/"):
        return
    if message.text in ["📊 Фінанси", "🎛 Розумний дім", "🚌 Автобус", "🌐 Мережа", "📅 Календар", "⚙️ Налаштування", "👥 Користувачі", "🏋️ Спортзал"]:
        return

    ha_response = await _try_process_ha_command(message)
    if ha_response:
        await message.answer(ha_response, parse_mode="HTML")