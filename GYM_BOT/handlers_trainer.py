import uuid
import datetime
import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, text, distinct
import html

from config import ADMIN_IDS, CATEGORY_TITLES
from database import (
    AsyncSessionLocal, User, ClientTarget, InviteToken, FoodProduct,
    BotSettings, FoodDay, FoodEntry, WorkoutSession, WorkoutPlan, WorkoutSet,
    Exercise, PlanExercise
)
from keyboards import (
    trainer_main_keyboard, trainer_clients_keyboard, trainer_client_manage_keyboard,
    client_main_keyboard, client_categories_keyboard, trainer_catalog_categories_keyboard,
    trainer_products_management_keyboard, trainer_product_actions_keyboard,
    confirm_delete_client_keyboard,
    trainer_reports_clients_keyboard, trainer_reports_dates_keyboard, trainer_report_detail_keyboard,
)
from handlers_client import get_client_dashboard, TARGET_FIELD

logger = logging.getLogger(__name__)
router = Router()

TARGET_FIELD = {
    "protein": "protein_target", "carbs": "carbs_target", "fats": "fats_target",
    "fruits": "fruits_target", "veggies": "veggies_target", "other": "other_target",
}
CATEGORY_ORDER = list(CATEGORY_TITLES.keys())

class EditTargetFSM(StatesGroup):
    editing = State()

class CatalogManageFSM(StatesGroup):
    waiting_for_name = State()
    waiting_for_size = State()
    waiting_for_unit = State()
    waiting_for_subcategory = State()
    waiting_for_new_portion = State()

class EditInstructionFSM(StatesGroup):
    waiting_for_global_inst = State()
    waiting_for_custom_inst = State()

class TrainerReplyFSM(StatesGroup):
    waiting_for_reply = State()

class TrainerNotesFSM(StatesGroup):
    waiting_for_notes = State()

class MaintenanceUpdateFSM(StatesGroup):
    waiting_for_update_text = State()

class TrainerReportsFSM(StatesGroup):
    selecting_client = State()
    selecting_date = State()
    viewing_report = State()

def is_trainer(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def _parse_float(raw: str) -> float | None:
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        return None

# ==========================================
# ТРЕНДИ ЗА ТИЖДЕНЬ
# ==========================================
@router.callback_query(F.data.startswith("tr_trends_"))
async def cal_tr_trends(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    
    today_date = datetime.datetime.now()
    week_ago_date = today_date - datetime.timedelta(days=7)
    today_str = today_date.strftime("%Y-%m-%d")
    week_ago_str = week_ago_date.strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        target = await session.get(ClientTarget, client_id)
        days = (await session.execute(
            select(FoodDay).where(FoodDay.user_id == client_id, FoodDay.date > week_ago_str, FoodDay.date <= today_str)
        )).scalars().all()
        entries = (await session.execute(
            select(FoodEntry).where(FoodEntry.user_id == client_id, FoodEntry.date > week_ago_str, FoodEntry.date <= today_str)
        )).scalars().all()

    if not days and not entries:
        return await callback.answer("Немає даних за останні 7 днів.", show_alert=True)

    days_closed = [d for d in days if d.is_closed]
    total_steps = sum(d.steps for d in days_closed)
    avg_steps = total_steps // len(days_closed) if days_closed else 0
    avg_wb = sum(d.wellbeing for d in days_closed) / len(days_closed) if days_closed else 0

    compliance_sums = {k: 0.0 for k in CATEGORY_TITLES}
    for e in entries:
        compliance_sums[e.category] += e.portions

    report = f"📊 <b>Тренди за 7 днів: {client.full_name}</b>\n\n"
    report += f"🏃 Сер. кроки: <b>{avg_steps}</b>\n"
    report += f"😊 Сер. самопочуття: <b>{avg_wb:.1f}/5</b>\n"
    report += f"🔒 Закритих днів: <b>{len(days_closed)}/7</b>\n\n"
    report += f"🎯 <b>Відсоток виконання порцій:</b>\n"

    for cat_key, title in CATEGORY_TITLES.items():
        if cat_key == "veggies" or cat_key == "other":
            continue
        
        base_target = getattr(target, TARGET_FIELD[cat_key]) if target else 0.0
        actual_target_sum = base_target * len(days) 
        for d in days:
            actual_target_sum += getattr(d, f"swap_{cat_key}", 0.0)

        if actual_target_sum > 0:
            percent = (compliance_sums[cat_key] / actual_target_sum) * 100
            report += f"{title}: <b>{percent:.1f}%</b>\n"

    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"tr_view_{client_id}")
    await callback.message.edit_text(report, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

# ==========================================
# ВІДПОВІДЬ НА ЗВІТ КЛІЄНТА
# ==========================================
@router.callback_query(F.data.startswith("tr_reply_"))
async def cal_tr_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    parts = callback.data.split("_")
    client_id = int(parts[2])
    date_str = parts[3]
    
    await state.set_state(TrainerReplyFSM.waiting_for_reply)
    await state.update_data(client_id=client_id, date_str=date_str)
    
    await callback.message.answer(f"✏️ Напишіть коментар або відгук клієнту за звіт {date_str}:")
    await callback.answer()

@router.message(StateFilter(TrainerReplyFSM.waiting_for_reply))
async def process_tr_reply(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    client_id = data.get("client_id")
    date_str = data.get("date_str")
    
    if not client_id:
        await state.clear()
        return await message.answer("❌ Сталася помилка (втрачено контекст). Спробуйте ще раз.")
        
    if message.text:
        reply_body = message.html_text
    elif message.caption:
        reply_body = message.html_text
    else:
        reply_body = "[Медіафайл від тренера]"
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        
    if client:
        reply_text = f"💬 <b>Повідомлення від тренера щодо звіту за {date_str}:</b>\n\n{reply_body}"
        try:
            await bot.send_message(client.telegram_id, reply_text, parse_mode="HTML")
            await message.answer("✅ Коментар успішно відправлено клієнту.")
        except Exception as e:
            logger.error(f"Не вдалося відправити коментар клієнту {client_id}: {e}")
            await message.answer("❌ Не вдалося відправити повідомлення. Клієнт заблокував бота або видалив чат.")
    else:
        await message.answer("❌ Клієнта не знайдено в базі.")
        
    await state.clear()

# ==========================================
# ІНСТРУКЦІЯ
# ==========================================
@router.message(F.text == "⚙️ Редагувати інструкцію")
async def cmd_edit_global_instruction(message: types.Message, state: FSMContext):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    await state.set_state(EditInstructionFSM.waiting_for_global_inst)
    kb = InlineKeyboardBuilder().button(text="Скасувати", callback_data="tr_inst_cancel")
    await message.answer("📝 Надішліть новий текст <b>ГЛОБАЛЬНОЇ</b> інструкції, який бачитимуть всі клієнти за замовчуванням:", reply_markup=kb.as_markup(), parse_mode="HTML")

@router.message(StateFilter(EditInstructionFSM.waiting_for_global_inst))
async def process_global_instruction(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        settings = (await session.execute(select(BotSettings).limit(1))).scalars().first()
        if not settings:
            settings = BotSettings()
            session.add(settings)
        settings.instruction_text = message.html_text
        await session.commit()
    await state.clear()
    await message.answer("✅ Загальну інструкцію успішно оновлено!")

@router.callback_query(F.data.startswith("tr_inst_"))
async def cal_tr_inst_start(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    if callback.data == "tr_inst_cancel":
        await state.clear()
        return await callback.message.edit_text("Дію скасовано.")
        
    parts = callback.data.split("_")
    if parts[2] == "reset":
        client_id = int(parts[3])
        async with AsyncSessionLocal() as session:
            target = await session.get(ClientTarget, client_id)
            if target:
                target.custom_instruction = None
                await session.commit()
        await state.clear()
        await callback.answer("✅ Інструкцію скинуто до загальної!", show_alert=True)
        return await _render_client_profile(bot, callback.message.chat.id, callback.message.message_id, client_id)

    client_id = int(parts[2])
    await state.set_state(EditInstructionFSM.waiting_for_custom_inst)
    await state.update_data(client_id=client_id, msg_id=callback.message.message_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Скинути до загальної", callback_data=f"tr_inst_reset_{client_id}")
    kb.button(text="Скасувати", callback_data=f"tr_view_{client_id}")
    
    await callback.message.edit_text(
        "📝 <b>Індивідуальна інструкція клієнта</b>\n\n"
        "Надішліть новий текст інструкції для цього клієнта. "
        "Можете використовувати теги <code>{protein}</code>, <code>{carbs}</code> і т.д. для авто-підстановки норм.\n\n"
        "Або натисніть кнопку, щоб скинути її до загальної:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@router.message(StateFilter(EditInstructionFSM.waiting_for_custom_inst))
async def process_tr_custom_inst(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    client_id = data["client_id"]
    
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, client_id)
        if target:
            target.custom_instruction = message.html_text 
            await session.commit()
    
    await state.clear()
    try:
        await message.delete()
        await bot.delete_message(message.chat.id, data["msg_id"])
    except:
        pass
    
    kb = InlineKeyboardBuilder().button(text="🔙 До профілю", callback_data=f"tr_view_{client_id}")
    await message.answer("✅ Індивідуальну інструкцію збережено!", reply_markup=kb.as_markup())

# ==========================================
# НОТАТКИ ТРЕНЕРА
# ==========================================
@router.callback_query(F.data.startswith("tr_notes_"))
async def cal_tr_notes_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, client_id)
        notes = target.trainer_notes if target else ""
    
    await state.set_state(TrainerNotesFSM.waiting_for_notes)
    await state.update_data(client_id=client_id, msg_id=callback.message.message_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Скасувати", callback_data=f"tr_view_{client_id}")
    current = f"\n\n<b>Поточні нотатки:</b>\n{html.escape(notes) if notes else '<i>немає</i>'}"
    await callback.message.edit_text(
        f"📝 <b>Внутрішні нотатки про клієнта</b>\n"
        f"Напишіть текст нотаток (алергії, травми, особливості).\n"
        f"Вони будуть відображатися у звіті для вас.{current}",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await callback.answer()

@router.message(StateFilter(TrainerNotesFSM.waiting_for_notes))
async def process_tr_notes(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    client_id = data["client_id"]
    notes = message.text.strip()
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, client_id)
        if target:
            target.trainer_notes = notes
            await session.commit()
    await state.clear()
    try:
        await message.delete()
        await bot.delete_message(message.chat.id, data["msg_id"])
    except:
        pass
    kb = InlineKeyboardBuilder().button(text="🔙 До профілю", callback_data=f"tr_view_{client_id}")
    await message.answer("✅ Нотатки збережено!", reply_markup=kb.as_markup())

# ==========================================
# СПИСОК КЛІЄНТІВ ТА УПРАВЛІННЯ
# ==========================================
@router.message(F.text == "👥 Мої клієнти")
async def cmd_my_clients(message: types.Message):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client").order_by(User.full_name))).scalars().all()
    if not clients:
        await message.answer("👥 У вас поки немає зареєстрованих клієнтів.")
        return
    await message.answer("📋 <b>Список ваших клієнтів:</b>", reply_markup=trainer_clients_keyboard(clients), parse_mode="HTML")

@router.callback_query(F.data == "tr_list_back")
async def cal_tr_list_back(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client").order_by(User.full_name))).scalars().all()
    await callback.message.edit_text("📋 <b>Список ваших клієнтів:</b>", reply_markup=trainer_clients_keyboard(clients), parse_mode="HTML")
    await callback.answer()

async def _render_client_profile(bot: Bot, chat_id: int, message_id: int, client_id: int):
    try:
        async with AsyncSessionLocal() as session:
            client = await session.get(User, client_id)
            target = await session.get(ClientTarget, client_id)

        if not client:
            await bot.edit_message_text("❌ Клієнта не знайдено (можливо, вже видалений).", chat_id=chat_id, message_id=message_id)
            return

        lines = [
            f"👤 <b>Клієнт: {client.full_name}</b>",
            f"Username: @{client.username or 'немає'}",
            "",
            "🎯 <b>Поточні норми (порцій/день):</b>",
        ]
        for cat_key, title in CATEGORY_TITLES.items():
            val = getattr(target, TARGET_FIELD[cat_key]) if target else 0.0
            if cat_key == "other":
                lines.append(f"  {title}: <b>{int(val)} шт.</b>")
            else:
                lines.append(f"  {title}: <b>{val:.2f}</b>")

        await bot.edit_message_text(
            "\n".join(lines),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=trainer_client_manage_keyboard(client_id),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка при редагуванні повідомлення профілю: {e}")
        await bot.send_message(
            chat_id,
            "❌ Не вдалося оновити профіль. Спробуйте ще раз через кнопку 'Мої клієнти'.",
            reply_markup=trainer_main_keyboard()
        )

@router.callback_query(F.data.startswith("tr_view_"))
async def cal_tr_view(callback: types.CallbackQuery, bot: Bot):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    await _render_client_profile(bot, callback.message.chat.id, callback.message.message_id, client_id)
    await callback.answer()

@router.callback_query(F.data.startswith("tr_stats_"))
async def cal_tr_stats(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        if not client:
            return await callback.answer("❌ Клієнта не знайдено.", show_alert=True)

    dash = await get_client_dashboard(client_id)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"tr_view_{client_id}")
    await callback.message.edit_text(f"📊 <b>{client.full_name}</b>\n\n{dash}", reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_del_confirm_"))
async def cal_tr_del_confirm(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[3])
    await callback.message.edit_text(
        "⚠️ <b>Ти справді хочеш видалити цього клієнта?</b>\nВся історія харчування буде стерта назавжди.",
        reply_markup=confirm_delete_client_keyboard(client_id), parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tr_del_"))
async def cal_tr_del(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        if client:
            await session.delete(client)
            await session.commit()
    await callback.answer("Клієнта видалено.", show_alert=True)
    await cal_tr_list_back(callback)

@router.callback_query(F.data.startswith("tr_edit_"))
async def cal_tr_edit_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[2])
    await state.set_state(EditTargetFSM.editing)
    await state.update_data(client_id=client_id, step=0, values={}, msg_id=callback.message.message_id)
    first_title = CATEGORY_TITLES[CATEGORY_ORDER[0]]
    await callback.message.edit_text(f"✏️ Введіть нову норму: <b>{first_title}</b> (порцій, наприклад <code>3.5</code>):", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(EditTargetFSM.editing))
async def process_edit_target_step(message: types.Message, state: FSMContext, bot: Bot):
    val = _parse_float(message.text)
    if val is None:
        return await message.answer("❌ Введіть число!")

    data = await state.get_data()
    step = data["step"]
    values = data["values"]
    values[CATEGORY_ORDER[step]] = val
    step += 1

    try:
        await message.delete()
    except:
        pass

    if step < len(CATEGORY_ORDER):
        await state.update_data(step=step, values=values)
        next_title = CATEGORY_TITLES[CATEGORY_ORDER[step]]
        await bot.edit_message_text(
            text=f"✏️ Введіть нову норму: <b>{next_title}</b>:", chat_id=message.chat.id,
            message_id=data["msg_id"], parse_mode="HTML",
        )
        return

    await state.clear()
    client_id = data["client_id"]
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, client_id)
        if target:
            for cat_key, val in values.items():
                setattr(target, TARGET_FIELD[cat_key], val)
            await session.commit()

    kb = InlineKeyboardBuilder().button(text="🔙 До профілю", callback_data=f"tr_view_{client_id}")
    await bot.edit_message_text(
        text="✅ <b>Норми раціону успішно оновлено!</b>", chat_id=message.chat.id,
        message_id=data["msg_id"], reply_markup=kb.as_markup(), parse_mode="HTML",
    )

@router.message(F.text == "➕ Створити інвайт")
async def cmd_create_invite(message: types.Message, bot: Bot):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    unique_token = str(uuid.uuid4())[:8]
    async with AsyncSessionLocal() as session:
        session.add(InviteToken(token=unique_token))
        await session.commit()
    bot_info = await bot.get_me()
    await message.answer(f"🎟️ <b>Нове посилання для клієнта:</b>\n<code>https://t.me/{bot_info.username}?start={unique_token}</code>", parse_mode="HTML")

@router.message(F.text == "🧪 Тест клієнта")
async def cmd_test_client_mode(message: types.Message):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        target = await session.get(ClientTarget, user.id) if user else None
        if not target and user:
            session.add(ClientTarget(user_id=user.id))
            await session.commit()
    await message.answer("🔄 <b>Активовано тестовий режим клієнта.</b>", reply_markup=client_main_keyboard(is_admin=True), parse_mode="HTML")
    await message.answer(await get_client_dashboard(user.id), reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.message(F.text == "🧠 В адмінку")
async def cmd_back_to_trainer_mode(message: types.Message):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    await message.answer("🧠 <b>Повернено в режим Тренера.</b>", reply_markup=trainer_main_keyboard(), parse_mode="HTML")

# ==========================================
# КЕРУВАННЯ МЕНЮ ПРОДУКТІВ
# ==========================================
@router.message(F.text == "⚙️ Керувати меню")
async def cmd_manage_catalog(message: types.Message):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    await message.answer("🗄️ <b>Управління меню продуктів</b>\n\nОберіть категорію:", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "tr_catmanage_back")
async def cal_tr_cat_back(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    await callback.message.edit_text("🗄️ <b>Управління меню продуктів</b>\n\nОберіть категорію:", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_catmanage_"))
async def cal_tr_show_category_products(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    cat = callback.data.replace("tr_catmanage_", "")
    async with AsyncSessionLocal() as session:
        products = (await session.execute(select(FoodProduct).where(FoodProduct.category == cat).order_by(FoodProduct.name))).scalars().all()
    await callback.message.edit_text(
        text=f"🛒 Продукти в <b>{CATEGORY_TITLES.get(cat, cat)}</b>:",
        reply_markup=trainer_products_management_keyboard(products, cat), parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data == "tr_paction_cancel")
async def cal_paction_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🗄️ <b>Управління меню продуктів</b>", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_propt_"))
async def cal_tr_product_options(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    pid = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
    if not product:
        return await callback.answer("Продукт не знайдено.", show_alert=True)
    await callback.message.edit_text(
        text=f"⚙️ <b>Керування: {product.name}</b>\n\nВага порції: <b>{int(product.size)} {product.unit}</b>",
        reply_markup=trainer_product_actions_keyboard(pid), parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data.startswith("tr_paction_del_"))
async def cal_tr_delete_product(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    pid = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
        if product:
            await session.delete(product)
            await session.commit()
    await callback.answer("🗑️ Продукт видалено з меню!", show_alert=True)
    await cal_tr_cat_back(callback)

@router.callback_query(F.data.startswith("tr_paction_edit_"))
async def cal_tr_edit_portion_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    pid = int(callback.data.split("_")[3])
    await state.set_state(CatalogManageFSM.waiting_for_new_portion)
    await state.update_data(pid=pid, msg_id=callback.message.message_id)
    await callback.message.edit_text("⚖️ Введіть нову вагу однієї порції:")
    await callback.answer()

@router.message(StateFilter(CatalogManageFSM.waiting_for_new_portion))
async def process_tr_saving_portion(message: types.Message, state: FSMContext, bot: Bot):
    new_size = _parse_float(message.text)
    if new_size is None or new_size <= 0:
        return await message.answer("❌ Введіть додатне число!")

    data = await state.get_data()
    await state.clear()
    try:
        await message.delete()
    except:
        pass

    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, data["pid"])
        if not product:
            return await bot.send_message(message.chat.id, "❌ Продукт вже не існує.")
        product.size = new_size
        unit = product.unit
        await session.commit()

    kb = InlineKeyboardBuilder().button(text="🔙 До категорій", callback_data="tr_catmanage_back")
    await bot.edit_message_text(text=f"✅ Оновлено до <b>{int(new_size)} {unit}</b>!", chat_id=message.chat.id, message_id=data["msg_id"], reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_addprod_"))
async def cal_tr_add_product_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    cat = callback.data.replace("tr_addprod_", "")
    await state.set_state(CatalogManageFSM.waiting_for_name)
    await state.update_data(cat=cat, msg_id=callback.message.message_id)
    await callback.message.edit_text(text=f"📝 Введіть назву продукту для {CATEGORY_TITLES.get(cat, cat)}:")
    await callback.answer()

@router.message(StateFilter(CatalogManageFSM.waiting_for_name))
async def process_tr_add_name(message: types.Message, state: FSMContext, bot: Bot):
    p_name = message.text.strip()
    if not p_name:
        return await message.answer("❌ Назва не може бути порожньою.")

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(FoodProduct).where(FoodProduct.name == p_name))).scalars().first()
    if existing:
        return await message.answer(f"❌ Продукт з назвою <b>«{p_name}»</b> вже є в меню. Введіть іншу назву:", parse_mode="HTML")

    data = await state.get_data()
    try:
        await message.delete()
    except:
        pass
    await state.update_data(name=p_name)
    await state.set_state(CatalogManageFSM.waiting_for_size)
    await bot.edit_message_text(text=f"⚖️ Продукт: <b>{p_name}</b>\n\nВведіть вагу базової порції:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(StateFilter(CatalogManageFSM.waiting_for_size))
async def process_tr_add_size(message: types.Message, state: FSMContext, bot: Bot):
    p_size = _parse_float(message.text)
    if p_size is None or p_size <= 0:
        return await message.answer("❌ Введіть додатне число!")

    data = await state.get_data()
    try:
        await message.delete()
    except:
        pass
    await state.update_data(size=p_size)
    await state.set_state(CatalogManageFSM.waiting_for_unit)
    await bot.edit_message_text(text=f"📦 Продукт: <b>{data['name']}</b>\n\nВведіть одиницю виміру (г/шт/мл):", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(StateFilter(CatalogManageFSM.waiting_for_unit))
async def process_tr_add_unit(message: types.Message, state: FSMContext, bot: Bot):
    p_unit = message.text.strip()
    if not p_unit:
        return await message.answer("❌ Одиниця виміру не може бути порожньою.")

    data = await state.get_data()
    await state.update_data(unit=p_unit)
    
    if data["cat"] == "other":
        await save_new_product(message, state)
        return
        
    await state.set_state(CatalogManageFSM.waiting_for_subcategory)
    async with AsyncSessionLocal() as session:
        subcats = (await session.execute(select(distinct(FoodProduct.subcategory)).where(FoodProduct.category == data["cat"], FoodProduct.subcategory.isnot(None)))).scalars().all()

    kb = InlineKeyboardBuilder()
    if subcats:
        for sc in subcats:
            kb.button(text=sc, callback_data=f"tr_add_sub_existing_{sc}")
    kb.button(text="➕ Створити нову", callback_data="tr_add_sub_new")
    kb.button(text="🔙 Скасувати", callback_data="tr_catmanage_back")
    kb.adjust(1)

    try:
        await message.delete()
    except:
        pass
    await bot.edit_message_text(
        text=f"📦 Продукт: <b>{data['name']}</b>\n\nОберіть підкатегорію або створіть нову:",
        chat_id=message.chat.id, message_id=data["msg_id"], reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("tr_add_sub_existing_"))
async def tr_add_sub_existing(callback: types.CallbackQuery, state: FSMContext):
    subcategory = callback.data.replace("tr_add_sub_existing_", "")
    await state.update_data(subcategory=subcategory)
    await save_new_product(callback, state)

@router.callback_query(F.data == "tr_add_sub_new")
async def tr_add_sub_new(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CatalogManageFSM.waiting_for_subcategory)
    await callback.message.edit_text("Введіть назву нової підкатегорії (з емодзі, наприклад '🐔 Птиця'):")

@router.message(StateFilter(CatalogManageFSM.waiting_for_subcategory))
async def tr_add_sub_new_text(message: types.Message, state: FSMContext):
    subcategory = message.text.strip()
    if not subcategory:
        return await message.answer("❌ Назва не може бути порожньою.")
    await state.update_data(subcategory=subcategory)
    await save_new_product(message, state)

async def save_new_product(update, state):
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(FoodProduct).where(FoodProduct.name == data["name"]))).scalars().first()
        if existing:
            kb = InlineKeyboardBuilder().button(text="🔙 До категорій", callback_data="tr_catmanage_back")
            if isinstance(update, types.Message):
                await update.answer(f"❌ Продукт <b>«{data['name']}»</b> вже існує.", reply_markup=kb.as_markup(), parse_mode="HTML")
            else:
                await update.message.edit_text(f"❌ Продукт <b>«{data['name']}»</b> вже існує.", reply_markup=kb.as_markup(), parse_mode="HTML")
            return
        session.add(FoodProduct(category=data["cat"], subcategory=data.get("subcategory"), name=data["name"], size=data["size"], unit=data["unit"]))
        await session.commit()

    kb = InlineKeyboardBuilder().button(text="🔙 До категорій", callback_data="tr_catmanage_back")
    subcat_text = f" (підкатегорія: {data.get('subcategory')})" if data.get("subcategory") else ""
    success_text = f"🚀 Продукт <b>{data['name']}</b>{subcat_text} успішно додано!"
    
    if isinstance(update, types.Message):
        await update.answer(success_text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await update.message.edit_text(success_text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ==========================================
# РЕЖИМ ТЕХНІЧНИХ РОБІТ
# ==========================================

@router.message(F.text == "🛠 Технічні роботи")
async def cmd_maintenance_on_confirm(message: types.Message):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="⚠️ Так, надіслати всім", callback_data="tr_bcast_maint_on")
    kb.button(text="❌ Скасувати", callback_data="tr_bcast_cancel")
    kb.adjust(1)
    await message.answer(
        "🛠 <b>Ти зараз надішлеш усім клієнтам повідомлення:</b>\n"
        "«Бот тимчасово не працює, очікуйте на сповіщення».\n\nПродовжити?",
        reply_markup=kb.as_markup(), parse_mode="HTML",
    )


@router.message(F.text == "✅ Бот відновлено")
async def cmd_maintenance_off_confirm(message: types.Message, state: FSMContext):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    await state.set_state(MaintenanceUpdateFSM.waiting_for_update_text)
    kb = InlineKeyboardBuilder()
    kb.button(text="⏩ Пропустити (без оновлень)", callback_data="tr_updates_skip")
    kb.button(text="❌ Скасувати", callback_data="tr_bcast_cancel")
    kb.adjust(1)
    await message.answer(
        "✅ <b>Відновлення роботи бота</b>\n\n"
        "Введіть текст зі списком оновлень, який отримають клієнти.\n"
        "(Наприклад: «Додано історію раціону та трекінг ваги»).\n\n"
        "Або натисніть кнопку, щоб надіслати стандартне повідомлення без оновлень:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data == "tr_updates_skip")
async def cal_updates_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так, надіслати всім", callback_data="tr_bcast_maint_off")
    kb.button(text="❌ Скасувати", callback_data="tr_bcast_cancel")
    kb.adjust(1)
    await callback.message.edit_text(
        "✅ <b>Ти зараз надішлеш усім клієнтам повідомлення:</b>\n"
        "«Бот знову працює!» (без списку оновлень).\n\nПродовжити?",
        reply_markup=kb.as_markup(), parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(MaintenanceUpdateFSM.waiting_for_update_text))
async def process_updates_text(message: types.Message, state: FSMContext):
    updates_text = message.text.strip()
    if not updates_text:
        await message.answer("❌ Текст не може бути порожнім. Введіть текст або натисніть 'Пропустити'.")
        return
    
    await state.update_data(updates=updates_text)
    
    preview = (
        "✅ <b>Бот знову працює!</b>\n"
        "Можете продовжувати вносити раціон.\n\n"
        "🆕 <b>Список оновлень:</b>\n"
        f"{html.escape(updates_text)}"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Надіслати всім", callback_data="tr_bcast_maint_off")
    kb.button(text="❌ Скасувати", callback_data="tr_bcast_cancel")
    kb.adjust(1)
    await message.answer(
        "📨 <b>Попередній перегляд повідомлення для клієнтів:</b>\n\n"
        f"{preview}\n\n"
        "Надіслати?",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data == "tr_bcast_cancel")
async def cal_bcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Скасовано.")
    await callback.answer()


@router.callback_query(F.data == "tr_bcast_maint_on")
async def cal_bcast_maintenance_on(callback: types.CallbackQuery, bot: Bot):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return

    text_to_send = "🛠 <b>Бот тимчасово не працює, очікуйте на сповіщення.</b>\nВибачте за незручності!"

    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client"))).scalars().all()
        settings = (await session.execute(select(BotSettings).limit(1))).scalars().first()
        if settings:
            settings.maintenance_mode = True
            await session.commit()

    sent, failed = 0, 0
    for client in clients:
        try:
            await bot.send_message(client.telegram_id, text_to_send, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Не вдалося надіслати розсилку клієнту {client.telegram_id}: {e}")

    await callback.message.edit_text(f"📨 <b>Розсилку завершено.</b>\nНадіслано: {sent}\nНе вдалося: {failed}", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "tr_bcast_maint_off")
async def cal_bcast_maintenance_off(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return

    data = await state.get_data()
    updates = data.get("updates")
    await state.clear()

    if updates:
        text_to_send = (
            "✅ <b>Бот знову працює!</b>\n"
            "Можете продовжувати вносити раціон.\n\n"
            "🆕 <b>Список оновлень:</b>\n"
            f"{html.escape(updates)}"
        )
    else:
        text_to_send = "✅ <b>Бот знову працює!</b>\nМожете продовжувати вносити раціон."

    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client"))).scalars().all()
        settings = (await session.execute(select(BotSettings).limit(1))).scalars().first()
        if settings:
            settings.maintenance_mode = False
            await session.commit()

    sent, failed = 0, 0
    for client in clients:
        try:
            await bot.send_message(client.telegram_id, text_to_send, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Не вдалося надіслати розсилку клієнту {client.telegram_id}: {e}")

    await callback.message.edit_text(f"📨 <b>Розсилку завершено.</b>\nНадіслано: {sent}\nНе вдалося: {failed}", parse_mode="HTML")
    await callback.answer()


# ==========================================
# НОВИЙ РОЗДІЛ: ЗВІТИ (централізований перегляд)
# ==========================================

async def get_client_name(client_id: int) -> str:
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        return client.full_name if client else "Клієнт"

async def get_reports_dates(client_id: int) -> list:
    async with AsyncSessionLocal() as session:
        food_dates = (await session.execute(
            select(FoodDay.date).where(FoodDay.user_id == client_id, FoodDay.is_closed == True).distinct()
        )).scalars().all()
        workout_dates = (await session.execute(
            select(WorkoutSession.date).where(WorkoutSession.client_id == client_id, WorkoutSession.completed == True).distinct()
        )).scalars().all()
    all_dates = set(food_dates) | set(workout_dates)
    dates_list = []
    for d in sorted(all_dates, reverse=True):
        dates_list.append({
            "date": d,
            "has_food": d in food_dates,
            "has_workout": d in workout_dates
        })
    return dates_list

@router.message(F.text == "📊 Звіти")
async def cmd_reports(message: types.Message, state: FSMContext):
    if not is_trainer(message.from_user.id):
        await message.answer("⛔ Доступ заборонено.")
        return
    await state.set_state(TrainerReportsFSM.selecting_client)
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client").order_by(User.full_name))).scalars().all()
    if not clients:
        return await message.answer("👥 Немає зареєстрованих клієнтів.")
    kb = trainer_reports_clients_keyboard(clients)
    await message.answer("📊 <b>Виберіть клієнта для перегляду звітів:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "tr_reports_clients")
async def cal_reports_clients(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    await state.set_state(TrainerReportsFSM.selecting_client)
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client").order_by(User.full_name))).scalars().all()
    if not clients:
        return await callback.message.edit_text("👥 Немає зареєстрованих клієнтів.")
    kb = trainer_reports_clients_keyboard(clients)
    await callback.message.edit_text("📊 <b>Виберіть клієнта для перегляду звітів:</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "tr_reports_back_to_menu")
async def cal_reports_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("📊 Повернення до головного меню.", reply_markup=trainer_main_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("tr_reports_client_"))
async def cal_reports_client(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    client_id = int(callback.data.split("_")[3])
    await state.update_data(client_id=client_id)
    await state.set_state(TrainerReportsFSM.selecting_date)
    
    dates_list = await get_reports_dates(client_id)
    if not dates_list:
        await callback.message.edit_text("📭 У цього клієнта ще немає звітів.")
        await callback.answer()
        return
    
    await state.update_data(dates_list=dates_list, page=0)
    kb = trainer_reports_dates_keyboard(dates_list, client_id, page=0)
    client_name = await get_client_name(client_id)
    await callback.message.edit_text(f"📅 <b>Звіти для {client_name}</b> (стор. 1)", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_reports_date"))
async def cal_reports_dates(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    parts = callback.data.split("_")
    # parts: ['tr', 'reports', 'date' або 'dates', client_id, ...]
    if len(parts) < 4:
        await callback.answer("❌ Невірний формат запиту.", show_alert=True)
        return
    
    # Розрізняємо навігацію сторінками та вибір дати
    if parts[2] == "dates":
        # Навігація по сторінках: tr_reports_dates_{client_id}_{page}
        if len(parts) < 5:
            await callback.answer("❌ Невірний формат запиту.", show_alert=True)
            return
        client_id = int(parts[3])
        page = int(parts[4])
        data = await state.get_data()
        dates_list = data.get("dates_list")
        if not dates_list:
            dates_list = await get_reports_dates(client_id)
            await state.update_data(dates_list=dates_list)
        await state.update_data(page=page)
        kb = trainer_reports_dates_keyboard(dates_list, client_id, page=page)
        client_name = await get_client_name(client_id)
        await callback.message.edit_text(f"📅 <b>Звіти для {client_name}</b> (стор. {page+1})", reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    elif parts[2] == "date":
        # Вибір конкретної дати: tr_reports_date_{client_id}_{date}
        if len(parts) < 5:
            await callback.answer("❌ Невірний формат запиту.", show_alert=True)
            return
        client_id = int(parts[3])
        # дата може бути у вигляді "2026-07-18", тому parts[4] - це вся дата
        date_str = parts[4]
        await callback.answer("📅 Завантаження звіту...")
        await show_report_detail(callback, client_id, date_str, state)
    else:
        await callback.answer("❌ Невідомий тип запиту.", show_alert=True)

async def show_report_detail(callback: types.CallbackQuery, client_id: int, date_str: str, state: FSMContext):
    if not is_trainer(callback.from_user.id):
        await callback.answer("⛔ Доступ заборонено.", show_alert=True)
        return
    await state.set_state(TrainerReportsFSM.viewing_report)
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        # Харчування
        food_day = (await session.execute(
            select(FoodDay).where(FoodDay.user_id == client_id, FoodDay.date == date_str, FoodDay.is_closed == True)
        )).scalars().first()
        food_entries = []
        if food_day:
            food_entries = (await session.execute(
                select(FoodEntry).where(FoodEntry.user_id == client_id, FoodEntry.date == date_str).order_by(FoodEntry.time_added)
            )).scalars().all()
        
        # Тренування
        workout_session = (await session.execute(
            select(WorkoutSession).where(WorkoutSession.client_id == client_id, WorkoutSession.date == date_str, WorkoutSession.completed == True)
        )).scalars().first()
        workout_sets = []
        workout_plan = None
        if workout_session:
            workout_plan = await session.get(WorkoutPlan, workout_session.plan_id)
            workout_sets = (await session.execute(
                select(WorkoutSet).where(WorkoutSet.session_id == workout_session.id).order_by(WorkoutSet.plan_exercise_id, WorkoutSet.set_number)
            )).scalars().all()
        
        target = await session.get(ClientTarget, client_id)
    
    # Формуємо звіт
    lines = [f"📋 <b>ЗВІТ ЗА {date_str}</b>"]
    lines.append(f"👤 Клієнт: {client.full_name}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Харчування
    if food_day:
        macros = {cat: 0.0 for cat in CATEGORY_TITLES}
        amounts = {cat: 0.0 for cat in CATEGORY_TITLES}
        for e in food_entries:
            if e.category in macros:
                macros[e.category] += e.portions
                amounts[e.category] += e.amount
        lines.append("🍽️ <b>Харчування</b>")
        for cat_key, title in CATEGORY_TITLES.items():
            curr = macros[cat_key] if cat_key != "veggies" else amounts[cat_key]
            base = getattr(target, TARGET_FIELD[cat_key]) if target else 0
            swap = getattr(food_day, f"swap_{cat_key}", 0.0)
            tgt = base + swap
            if cat_key in ["veggies", "other"]:
                lines.append(f"  {title}: {curr:g}/{tgt:g} ({(curr/tgt*100) if tgt>0 else 0:.0f}%)")
            else:
                lines.append(f"  {title}: {curr:.1f}/{tgt:.1f} порц. ({(curr/tgt*100) if tgt>0 else 0:.0f}%)")
        if food_entries:
            lines.append("  📝 Продукти:")
            for e in food_entries:
                if e.category == "other":
                    if e.amount == 1 and e.portions == 1:
                        val_str = "1 шт."
                    else:
                        val_str = f"{e.amount:g} г"
                elif e.category == "veggies":
                    val_str = f"{e.amount:g} г"
                else:
                    val_str = f"{e.amount:g} г ({e.portions:.1f} порц.)"
                lines.append(f"    • {e.time_added} {html.escape(e.product_name)} ({val_str})")
        lines.append(f"  💬 Коментар: {html.escape(food_day.comment) if food_day.comment else 'Немає'}")
        lines.append(f"  🏃 Кроки: {food_day.steps}")
        lines.append(f"  😊 Самопочуття: {food_day.wellbeing}/5")
    else:
        lines.append("🍽️ <b>Харчування:</b> звіт відсутній")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Тренування
    if workout_session:
        lines.append("🏋️ <b>Тренування</b>")
        lines.append(f"  📋 План: {html.escape(workout_plan.name) if workout_plan else 'Невідомо'}")
        lines.append(f"  ⏱️ Час: {workout_session.start_time} – {workout_session.end_time}")
        lines.append(f"  🏋️ Загальний обсяг: {workout_session.total_volume:.1f} кг")
        lines.append(f"  ✔️ Підходів: {workout_session.total_sets}")
        if workout_sets:
            exercise_map = {}
            async with AsyncSessionLocal() as db:
                for ws in workout_sets:
                    pe = await db.get(PlanExercise, ws.plan_exercise_id)
                    if pe:
                        ex = await db.get(Exercise, pe.exercise_id)
                        ex_name = ex.name if ex else "Вправа"
                        key = pe.id
                        if key not in exercise_map:
                            exercise_map[key] = {"name": ex_name, "sets": []}
                        exercise_map[key]["sets"].append((ws.set_number, ws.weight, ws.reps))
            if exercise_map:
                lines.append("  📝 Вправи:")
                for pe_id, data in exercise_map.items():
                    lines.append(f"    <b>{data['name']}</b>")
                    for set_num, weight, reps in data["sets"]:
                        lines.append(f"      Підхід {set_num}: {weight} кг × {reps}")
        if workout_session.comment:
            lines.append(f"  💬 Коментар: {html.escape(workout_session.comment)}")
    else:
        lines.append("🏋️ <b>Тренування:</b> звіт відсутній")
    
    report = "\n".join(lines)
    kb = trainer_report_detail_keyboard(client_id, date_str)
    try:
        await callback.message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Помилка редагування звіту: {e}")
        await callback.message.answer(report, reply_markup=kb, parse_mode="HTML")
    await callback.answer()