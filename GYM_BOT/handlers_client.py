import re
import logging
import html
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, text, delete, func, distinct, desc

from config import ADMIN_IDS, CATEGORY_TITLES
from database import (
    AsyncSessionLocal, User, ClientTarget, FoodEntry, InviteToken,
    FoodProduct, FoodDay, BotSettings, ClientMeal, WeightEntry
)
from keyboards import (
    client_main_keyboard, trainer_main_keyboard, client_categories_keyboard,
    client_subcategories_keyboard, client_products_keyboard_paginated,
    client_products_keyboard_paginated_for_subcat, close_day_scale_keyboard,
    close_day_yes_no_keyboard, close_day_skip_keyboard, client_close_day_confirm_keyboard,
    trainer_report_reply_keyboard, history_navigation_keyboard, weight_main_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()

TARGET_FIELD = {
    "protein": "protein_target", "carbs": "carbs_target", "fats": "fats_target",
    "fruits": "fruits_target", "veggies": "veggies_target", "other": "other_target",
}

MENU_BUTTON_TEXTS = [
    "🍏 Мій раціон", "🧪 Тест клієнта", "🧠 В адмінку",
    "⚙️ Керувати меню", "👥 Мої клієнти", "➕ Створити інвайт",
    "📖 Інструкція", "⚙️ Редагувати інструкцію",
    "📅 Історія", "⚖️ Моя вага", "🏋️ Спортзал"
]

class ClientLogFSM(StatesGroup):
    waiting_for_grams = State()

class AnythingFSM(StatesGroup):
    waiting_for_text = State()

class CloseDayFSM(StatesGroup):
    waiting_for_steps = State()
    waiting_for_workout = State()
    waiting_for_wellbeing = State()
    waiting_for_comment = State()

class MealBuilderFSM(StatesGroup):
    waiting_for_name = State()
    building = State()
    waiting_for_grams = State()

class WeightFSM(StatesGroup):
    waiting_for_weight = State()

def is_trainer(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def generate_visual_bar(current: float, target: float) -> str:
    if target <= 0: return "<code>[〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️]</code>"
    ratio = min(current / target, 1.0)
    filled = int(ratio * 10)
    return f"<code>{'🟩' * filled}{'⬜' * (10 - filled)}</code>"

def _parse_float(raw: str) -> float | None:
    try: return float(raw.strip().replace(",", "."))
    except ValueError: return None

async def get_client_dashboard(user_id: int, date_str: str = None) -> str:
    today = date_str or datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        target = await session.get(ClientTarget, user_id)
        if not target:
            target = ClientTarget(user_id=user_id)
            session.add(target)
            await session.commit()
            target = await session.get(ClientTarget, user_id)

        rows = (await session.execute(
            text("SELECT category, SUM(portions), SUM(amount) FROM food_entries WHERE user_id = :uid AND date = :dt GROUP BY category"),
            {"uid": user_id, "dt": today},
        )).all()

        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user_id, FoodDay.date == today))).scalars().first()

    is_closed = food_day.is_closed if food_day else False
    status_text = "🔒 День закрито (Звіт надіслано)" if is_closed else "🔓 День відкритий"
    day_number = (datetime.strptime(today, "%Y-%m-%d") - user.created_at).days + 1

    totals = {cat: 0.0 for cat in CATEGORY_TITLES}
    amounts = {cat: 0.0 for cat in CATEGORY_TITLES}
    for cat, total_portions, total_amount in rows:
        if cat in totals:
            totals[cat] = float(total_portions or 0)
            amounts[cat] = float(total_amount or 0)

    def check_mark(curr, target_val):
        if target_val <= 0: return "⚪"
        ratio = curr / target_val
        if 0.7 <= ratio <= 1.2: return "✅"
        if ratio > 1.2: return "⚠️"
        return "⏳"

    lines = [
        f"🍏 <b>Щоденник харчування</b> | {status_text}",
        f"📅 День {day_number} ({today})",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for cat_key, title in CATEGORY_TITLES.items():
        curr = totals[cat_key]
        base_tgt = getattr(target, TARGET_FIELD[cat_key])
        swap_val = getattr(food_day, f"swap_{cat_key}", 0.0) if food_day else 0.0
        tgt = base_tgt + swap_val

        if cat_key == "veggies": curr = amounts[cat_key]
        elif cat_key == "other": curr = amounts[cat_key]

        if cat_key == "other":
            lines.append(f"{title}: {curr:g} / {tgt:g} шт. {check_mark(curr, tgt)}")
            lines.append(generate_visual_bar(curr, tgt))
        elif cat_key == "veggies":
            lines.append(f"{title}: {curr:.1f} / {tgt:.1f} г {check_mark(curr, tgt)}")
            lines.append(generate_visual_bar(curr, tgt))
        else:
            lines.append(f"{title}: {curr:.1f} / {tgt:.1f} порц. {check_mark(curr, tgt)}")
            lines.append(generate_visual_bar(curr, tgt))
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    if food_day and food_day.is_closed:
        lines.append(f"🏃 Кроки: {food_day.steps}")
        lines.append(f"🏋️ Тренування: {'✅' if food_day.workout_done else '❌'}")
        lines.append(f"😊 Самопочуття: {food_day.wellbeing}/5")
        if food_day.comment:
            lines.append(f"💬 Коментар: {html.escape(food_day.comment)}")
    if not is_closed:
        lines.append("<i>💡 Можна швидко внести їжу текстом: 'Гречка 120'.</i>")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()

        if user:
            kb = trainer_main_keyboard() if is_trainer(uid) else client_main_keyboard()
            return await message.answer(f"👋 З поверненням, {user.full_name}!", reply_markup=kb)

        if is_trainer(uid):
            new_trainer = User(telegram_id=uid, username=message.from_user.username, full_name=message.from_user.full_name or "Тренер", role="trainer")
            session.add(new_trainer)
            await session.commit()
            return await message.answer(
                "👋 Вітаю, тренере! Систему ініціалізовано.\nНатисни '➕ Створити інвайт', щоб запросити першого клієнта.",
                reply_markup=trainer_main_keyboard(),
            )

        if not payload:
            return await message.answer("🔒 Цей бот доступний лише за персональним запрошенням від тренера.")

        token = await session.get(InviteToken, payload)
        if not token or token.is_used:
            return await message.answer("❌ Це запрошення недійсне або вже використане. Зверніться до тренера за новим посиланням.")

        token.is_used = True
        new_client = User(telegram_id=uid, username=message.from_user.username, full_name=message.from_user.full_name or f"Клієнт {uid}", role="client")
        session.add(new_client)
        await session.commit()
        await session.refresh(new_client)
        session.add(ClientTarget(user_id=new_client.id))
        await session.commit()
        client_name = new_client.full_name

    await message.answer(f"🎉 Ласкаво просимо, {client_name}! Реєстрацію завершено.", reply_markup=client_main_keyboard())


@router.message(F.text == "📖 Інструкція")
async def cmd_instruction(message: types.Message):
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return
        target = await session.get(ClientTarget, user.id)
        settings = (await session.execute(select(BotSettings).limit(1))).scalars().first()
        raw_text = target.custom_instruction if (target and target.custom_instruction) else (settings.instruction_text if settings else "Інструкція відсутня.")

    if target:
        try:
            text_inst = raw_text.format(
                protein=target.protein_target, carbs=target.carbs_target,
                fats=target.fats_target, fruits=target.fruits_target,
                other=int(target.other_target), veggies=target.veggies_target
            )
        except Exception: text_inst = raw_text
    else:
        text_inst = raw_text

    for i in range(0, len(text_inst), 4000):
        await message.answer(text_inst[i:i+4000], parse_mode="HTML")


@router.message(F.text == "🍏 Мій раціон")
async def cl_diet_menu(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Ваш профіль не знайдено.")
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        is_closed = food_day.is_closed if food_day else False

    await message.answer(await get_client_dashboard(user.id), reply_markup=client_categories_keyboard(is_closed), parse_mode="HTML")


@router.callback_query(F.data == "client_food_home")
async def cal_client_food_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        is_closed = food_day.is_closed if food_day else False

    await callback.message.edit_text(await get_client_dashboard(user.id), reply_markup=client_categories_keyboard(is_closed), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "client_view_logs")
async def cal_client_view_logs(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        entries = (await session.execute(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.date == today))).scalars().all()
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        is_closed = food_day.is_closed if food_day else False

    if not entries:
        return await callback.answer("📭 Сьогодні ви ще не вносили продуктів.", show_alert=True)

    builder = InlineKeyboardBuilder()
    text_data = "📝 <b>Зважені продукти за сьогодні:</b>\n\n"
    for e in entries:
        if e.category == "other":
            val_str = f"{e.amount:g} г ({e.portions:.2f} порц.)" if e.amount != 1.0 else "1 шт."
        elif e.category == "veggies":
            val_str = f"{e.amount:g} г"
        else:
            val_str = f"{e.amount:g} г ({e.portions:.2f} порц.)"

        text_data += f"• {e.time_added} | <b>{e.product_name}</b>: {val_str}\n"
        if not is_closed:
            builder.button(text=f"❌ {e.product_name[:14]}", callback_data=f"cl_dellog_{e.id}")

    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(1)
    await callback.message.edit_text(text=text_data, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cl_dellog_"))
async def cal_client_delete_log_entry(callback: types.CallbackQuery):
    entry_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        await session.execute(delete(FoodEntry).where(FoodEntry.id == entry_id))
        await session.commit()
    await callback.answer("🗑️ Запис видалено!")
    await cal_client_view_logs(callback)


# ============================================================
# ОБРОБНИКИ КАТЕГОРІЙ ТА ПІДКАТЕГОРІЙ
# ============================================================
@router.callback_query(F.data.startswith("client_cat_"))
async def cal_client_cat(callback: types.CallbackQuery, state: FSMContext):
    cat_key = callback.data.replace("client_cat_", "")

    # ОВОЧІ
    if cat_key == "veggies":
        await state.set_state(ClientLogFSM.waiting_for_grams)
        await state.update_data(cat=cat_key, name="Овочі", size=1, unit="г", msg_id=callback.message.message_id)
        kb = InlineKeyboardBuilder().button(text="🔙 Скасувати", callback_data="client_food_home").as_markup()
        await callback.message.edit_text("🥗 <b>Овочі:</b>\nВведіть з'їдену кількість у грамах (наприклад, 200):", reply_markup=kb, parse_mode="HTML")
        return await callback.answer()

    # БУДЬ-ЩО
    if cat_key == "other":
        today = datetime.now().strftime("%Y-%m-%d")
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
            target = await session.get(ClientTarget, user.id)
            food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()

            base_other_tgt = target.other_target if target else 2.0
            swap_val = food_day.swap_other if food_day else 0.0
            other_limit = base_other_tgt + swap_val

            other_count = (await session.execute(
                select(func.sum(FoodEntry.portions)).where(FoodEntry.user_id == user.id, FoodEntry.date == today, FoodEntry.category == "other")
            )).scalar() or 0.0

            if other_count >= other_limit:
                return await callback.answer(f"❌ Ви вже використали ліміт ({other_limit:g} порц.) для категорії 'Будь-що'!", show_alert=True)

            products = (await session.execute(select(FoodProduct).where(FoodProduct.category == "other").order_by(FoodProduct.name))).scalars().all()

        kb = InlineKeyboardBuilder()
        if products:
            for p in products:
                try: size_str = f"{float(p.size):g}"
                except: size_str = str(p.size)
                kb.button(text=f"🍩 {p.name} ({size_str}{p.unit})", callback_data=f"cl_dbprod_{p.id}")

        kb.button(text="✍️ Ввести свою назву вручну", callback_data="cl_other_manual")
        kb.button(text="🔙 Назад", callback_data="client_food_home")
        kb.adjust(1)
        
        await callback.message.edit_text(
            f"🍩 <b>Будь-що</b>\n"
            f"Використано за сьогодні: {other_count:g}/{other_limit:g}\n\n"
            "Оберіть продукт зі списку або введіть свій варіант:",
            parse_mode="HTML", reply_markup=kb.as_markup()
        )
        return await callback.answer()

    # ІНШІ КАТЕГОРІЇ (БІЛКИ, ВУГЛЕВОДИ, ЖИРИ, ФРУКТИ)
    async with AsyncSessionLocal() as session:
        subcats = (await session.execute(
            select(distinct(FoodProduct.subcategory))
            .where(FoodProduct.category == cat_key, FoodProduct.subcategory.isnot(None))
            .order_by(FoodProduct.subcategory)
        )).scalars().all()

        if not subcats:
            products = (await session.execute(
                select(FoodProduct).where(FoodProduct.category == cat_key).order_by(FoodProduct.name)
            )).scalars().all()
            if not products:
                return await callback.answer("У цій категорії поки немає продуктів.", show_alert=True)

            title = CATEGORY_TITLES.get(cat_key, cat_key)
            kb = client_products_keyboard_paginated(products, cat_key, page=0)
            await callback.message.edit_text(f"Оберіть продукт з категорії <b>{title}</b> (стор. 1):", reply_markup=kb, parse_mode="HTML")
            return await callback.answer()

        title = CATEGORY_TITLES.get(cat_key, cat_key)
        kb = client_subcategories_keyboard(cat_key, subcats)
        await callback.message.edit_text(f"Оберіть групу продуктів у категорії <b>{title}</b>:", reply_markup=kb, parse_mode="HTML")
        await callback.answer()


@router.callback_query(F.data == "cl_other_manual")
async def cal_cl_other_manual(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AnythingFSM.waiting_for_text)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="client_cat_other").as_markup()
    await callback.message.edit_text(
        "🍩 <b>Будь-що (Вільне введення)</b>\n\n"
        "Напишіть текстом, що ви з'їли або випили та приблизну грамівку (наприклад: <code>Снікерс 50г</code> або <code>Шматок піци</code>).",
        parse_mode="HTML", reply_markup=kb
    )
    await callback.answer()


@router.message(StateFilter(AnythingFSM.waiting_for_text))
async def process_anything_text(message: types.Message, state: FSMContext):
    text_input = message.text.strip()
    today = datetime.now().strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        target = await session.get(ClientTarget, user.id)
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()

        base_other_tgt = target.other_target if target else 2.0
        swap_val = food_day.swap_other if food_day else 0.0
        other_limit = base_other_tgt + swap_val

        other_count = (await session.execute(
            select(func.sum(FoodEntry.portions)).where(FoodEntry.user_id == user.id, FoodEntry.date == today, FoodEntry.category == "other")
        )).scalar() or 0.0

        if other_count + 1.0 > other_limit:
            await state.clear()
            return await message.answer(f"❌ Перевищено ліміт! Залишилось: {max(0, other_limit - other_count):g} порцій 'Будь-що'.")

        session.add(FoodEntry(user_id=user.id, date=today, category="other", product_name=text_input, amount=1, portions=1))
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Внесено 'Будь-що': <b>{html.escape(text_input)}</b>", parse_mode="HTML")
    await cl_diet_menu(message, state)


# ============================================================
# ПАГІНАЦІЯ ТА ВИБІР (БЕЗПЕЧНИЙ ПАРСИНГ)
# ============================================================
@router.callback_query(F.data.startswith("cl_sc_"))
async def cal_client_subcategory(callback: types.CallbackQuery, state: FSMContext):
    rest = callback.data[6:] # cut 'cl_sc_'
    category, subcategory_name = rest.split("_", 1)

    async with AsyncSessionLocal() as session:
        products = (await session.execute(
            select(FoodProduct).where(FoodProduct.category == category, FoodProduct.subcategory == subcategory_name).order_by(FoodProduct.name)
        )).scalars().all()

    if not products:
        return await callback.answer("У цій групі поки немає продуктів.", show_alert=True)

    kb = client_products_keyboard_paginated_for_subcat(products, category, subcategory_name, page=0)
    await callback.message.edit_text(f"Оберіть продукт з групи <b>{subcategory_name}</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("cl_pp_"))
async def cal_client_prod_page(callback: types.CallbackQuery, state: FSMContext):
    base_data, page_str = callback.data.rsplit("_", 1)
    page = int(page_str)
    category = base_data[6:]

    async with AsyncSessionLocal() as session:
        products = (await session.execute(select(FoodProduct).where(FoodProduct.category == category).order_by(FoodProduct.name))).scalars().all()

    if not products: return await callback.answer("Немає продуктів.", show_alert=True)
    title = CATEGORY_TITLES.get(category, category)
    kb = client_products_keyboard_paginated(products, category, page)
    await callback.message.edit_text(f"Оберіть продукт з категорії <b>{title}</b> (стор. {page+1}):", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("cl_ps_"))
async def cal_client_prod_page_sub(callback: types.CallbackQuery, state: FSMContext):
    base_data, page_str = callback.data.rsplit("_", 1)
    page = int(page_str)
    rest = base_data[6:]
    category, subcategory_name = rest.split("_", 1)

    async with AsyncSessionLocal() as session:
        products = (await session.execute(
            select(FoodProduct).where(FoodProduct.category == category, FoodProduct.subcategory == subcategory_name).order_by(FoodProduct.name)
        )).scalars().all()

    if not products: return await callback.answer("Немає продуктів.", show_alert=True)
    kb = client_products_keyboard_paginated_for_subcat(products, category, subcategory_name, page)
    await callback.message.edit_text(f"Оберіть продукт з групи <b>{subcategory_name}</b> (стор. {page+1}):", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ============================================================
# ВВЕДЕННЯ ВАГИ ДЛЯ ПРОДУКТУ (ФІНАЛ)
# ============================================================
@router.callback_query(F.data.startswith("cl_dbprod_"))
async def cal_client_select_product(callback: types.CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, product_id)
    if not product: return await callback.answer("Продукт не знайдено.", show_alert=True)

    await state.set_state(ClientLogFSM.waiting_for_grams)
    await state.update_data(product_id=product.id, product_name=product.name, product_category=product.category, product_size=product.size, product_unit=product.unit)
    
    try: size_str = f"{float(product.size):g}"
    except: size_str = str(product.size)
    
    await callback.message.edit_text(f"Введіть кількість (в {product.unit}) для <b>{product.name}</b>\n<i>(1 порція = {size_str} {product.unit}):</i>", parse_mode="HTML")
    await callback.answer()

@router.message(StateFilter(ClientLogFSM.waiting_for_grams))
async def process_client_grams(message: types.Message, state: FSMContext):
    val = _parse_float(message.text)
    if val is None:
        return await message.answer("❌ Введіть число!")

    data = await state.get_data()
    cat = data.get("cat") or data.get("product_category")
    product_name = data.get("name") or data.get("product_name")
    product_id = data.get("product_id")
    size = data.get("size") or data.get("product_size")

    if not cat or not product_name:
        await state.clear()
        return await message.answer("❌ Сталася помилка, спробуйте знову.")

    uid = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено.")
        
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if food_day and food_day.is_closed:
            await state.clear()
            return await message.answer("🔒 Ваш день вже закрито. Ви не можете додавати продукти.")

        if cat == "veggies":
            portions = 0
        else:
            if not product_id:
                await state.clear()
                return await message.answer("❌ Сталася помилка, почніть спочатку.")
            portions = val / size

        if cat == "other":
            target = await session.get(ClientTarget, user.id)
            base_other_tgt = target.other_target if target else 2.0
            swap_val = food_day.swap_other if food_day else 0.0
            other_limit = base_other_tgt + swap_val

            other_count_raw = (await session.execute(
                select(func.sum(FoodEntry.portions)).where(FoodEntry.user_id == user.id, FoodEntry.date == today, FoodEntry.category == "other")
            )).scalar() or 0.0

            if other_count_raw + portions > other_limit:
                await state.clear()
                return await message.answer(f"❌ Перевищено ліміт! Залишилось: {max(0, other_limit - other_count_raw):g} порцій 'Будь-що'.")

        entry = FoodEntry(user_id=user.id, date=today, category=cat, product_name=product_name, amount=val, portions=portions)
        session.add(entry)
        await session.commit()

    await state.clear()
    unit = data.get("unit") or data.get("product_unit")
    await message.answer(f"✅ Додано: {html.escape(product_name)} ({val:g} {unit})", parse_mode="HTML")
    await cl_diet_menu(message, state)


# ============================================================
# ДИНАМІЧНІ ЗАМІНИ (SWAPS)
# ============================================================
@router.callback_query(F.data == "cl_swap_home")
async def cl_swap_home(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="1 'Будь-що' ➡️ 1 'Вуглеводи'", callback_data="cl_do_swap_carbs")
    kb.button(text="1 'Будь-що' ➡️ 2 'Фрукти'", callback_data="cl_do_swap_fruits")
    kb.button(text="🔙 Назад", callback_data="client_food_home")
    kb.adjust(1)
    await callback.message.edit_text("🔄 <b>Динамічні заміни</b>\n\nОберіть, на що обміняти 1 порцію 'Будь-що' на сьогодні:", reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("cl_do_swap_"))
async def cl_do_swap(callback: types.CallbackQuery, state: FSMContext):
    target_cat = callback.data.replace("cl_do_swap_", "")
    today = datetime.now().strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        target = await session.get(ClientTarget, user.id)

        if not food_day:
            food_day = FoodDay(user_id=user.id, date=today, swap_other=0.0, swap_carbs=0.0, swap_fruits=0.0)
            session.add(food_day)

        current_other_target = target.other_target + (food_day.swap_other or 0.0)
        if current_other_target < 1.0:
            return await callback.answer("❌ У вас недостатньо ліміту 'Будь-що' для заміни!", show_alert=True)

        food_day.swap_other -= 1.0
        if target_cat == "carbs": food_day.swap_carbs += 1.0
        elif target_cat == "fruits": food_day.swap_fruits += 2.0

        await session.commit()

    await callback.answer("✅ Заміну успішно виконано!")
    await cal_client_food_home(callback, state)


# ============================================================
# КОНСТРУКТОР СТРАВ (MEAL BUILDER)
# ============================================================
@router.callback_query(F.data == "cl_meals_home")
async def cl_meals_home(callback: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        meals = (await session.execute(select(ClientMeal).where(ClientMeal.user_id == user.id))).scalars().all()

    kb = InlineKeyboardBuilder()
    for m in meals:
        kb.row(
            types.InlineKeyboardButton(text=f"🍽 {m.name}", callback_data=f"cl_meal_use_{m.id}"),
            types.InlineKeyboardButton(text="❌", callback_data=f"cl_meal_del_{m.id}")
        )
    kb.row(types.InlineKeyboardButton(text="➕ Створити нову страву", callback_data="cl_meal_create"))
    kb.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="client_food_home"))

    await callback.message.edit_text("📦 <b>Мої страви (Шаблони)</b>\nТут зберігаються ваші готові комбінації продуктів.", reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "cl_meal_create")
async def cl_meal_create(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(MealBuilderFSM.waiting_for_name)
    kb = InlineKeyboardBuilder().button(text="Скасувати", callback_data="cl_meals_home")
    await callback.message.edit_text("📝 Введіть назву для нової страви (наприклад: 'Вівсянка з горіхами'):", reply_markup=kb.as_markup())

@router.message(StateFilter(MealBuilderFSM.waiting_for_name))
async def cl_meal_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip(), components=[], msg_id=message.message_id)
    await state.set_state(MealBuilderFSM.building)
    await render_meal_builder(message, state)

async def render_meal_builder(message, state):
    data = await state.get_data()
    text = f"📦 Створюємо страву: <b>{html.escape(data['name'])}</b>\n\n"
    if data['components']:
        text += "Інгредієнти:\n"
        for c in data['components']:
            text += f"▫️ {html.escape(c['name'])} ({c['amount']}{c['unit']})\n"
    else:
        text += "Поки що порожньо.\n"

    text += "\nОберіть категорію, щоб додати продукт:"

    kb = InlineKeyboardBuilder()
    for cat_key, title in CATEGORY_TITLES.items():
        kb.button(text=title, callback_data=f"cl_mb_cat_{cat_key}")
    if data['components']:
        kb.button(text="💾 Зберегти страву", callback_data="cl_mb_save")
    kb.button(text="❌ Скасувати", callback_data="cl_meals_home")
    kb.adjust(2)

    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("cl_mb_cat_"))
async def cl_mb_cat(callback: types.CallbackQuery):
    cat = callback.data.replace("cl_mb_cat_", "")
    async with AsyncSessionLocal() as session:
        products_list = (await session.execute(select(FoodProduct).where(FoodProduct.category == cat).order_by(FoodProduct.name))).scalars().all()

    kb = InlineKeyboardBuilder()
    for p in products_list:
        kb.button(text=f"{p.name} ({int(p.size)}{p.unit})", callback_data=f"cl_mb_prod_{p.id}")
    kb.button(text="🔙 Назад", callback_data="cl_mb_back")
    kb.adjust(2)
    await callback.message.edit_text("Оберіть продукт для додавання:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "cl_mb_back")
async def cl_mb_back(callback: types.CallbackQuery, state: FSMContext):
    await render_meal_builder(callback.message, state)

@router.callback_query(F.data.startswith("cl_mb_prod_"))
async def cl_mb_prod(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
    await state.update_data(cur_cat=product.category, cur_name=product.name, cur_size=product.size, cur_unit=product.unit)
    await state.set_state(MealBuilderFSM.waiting_for_grams)
    await callback.message.edit_text(f"Введіть вагу для <b>{product.name}</b> ({product.unit}):", parse_mode="HTML")

@router.message(StateFilter(MealBuilderFSM.waiting_for_grams))
async def cl_mb_grams(message: types.Message, state: FSMContext):
    val = _parse_float(message.text)
    if val is None:
        return await message.answer("❌ Введіть число!")

    data = await state.get_data()
    portions = val / data["cur_size"] if data["cur_cat"] != "veggies" else 0

    data["components"].append({
        "cat": data["cur_cat"],
        "name": data["cur_name"],
        "amount": val,
        "portions": portions,
        "unit": data["cur_unit"]
    })

    await state.update_data(components=data["components"])
    await state.set_state(MealBuilderFSM.building)

    try: await message.delete()
    except: pass
    await render_meal_builder(message, state)

@router.callback_query(F.data == "cl_mb_save")
async def cl_mb_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        meal = ClientMeal(user_id=user.id, name=data["name"], components=data["components"])
        session.add(meal)
        await session.commit()
    await state.clear()
    await callback.answer("✅ Страву збережено!")
    await cl_meals_home(callback)

@router.callback_query(F.data.startswith("cl_meal_del_"))
async def cl_meal_del(callback: types.CallbackQuery):
    mid = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ClientMeal).where(ClientMeal.id == mid))
        await session.commit()
    await callback.answer("🗑 Страву видалено")
    await cl_meals_home(callback)

@router.callback_query(F.data.startswith("cl_meal_use_"))
async def cl_meal_use(callback: types.CallbackQuery, state: FSMContext):
    mid = int(callback.data.split("_")[3])
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if food_day and food_day.is_closed:
            return await callback.answer("🔒 День закрито", show_alert=True)

        meal = await session.get(ClientMeal, mid)
        for c in meal.components:
            entry = FoodEntry(user_id=user.id, date=today, category=c["cat"], product_name=f"📦 {meal.name} [{c['name']}]", amount=c["amount"], portions=c["portions"])
            session.add(entry)
        await session.commit()

    await callback.answer(f"✅ Страву {meal.name} додано!")
    await cal_client_food_home(callback, state)


# ============================================================
# ЕКСПРЕС ВВЕДЕННЯ
# ============================================================
EXPRESS_ENTRY_RE = re.compile(r"^\s*(.+?)\s+(\d+([.,]\d+)?)\s*$")

@router.message(StateFilter(None), F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_BUTTON_TEXTS))
async def text_parsing_express_entry(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    match = EXPRESS_ENTRY_RE.match(message.text.strip())
    if not match:
        return await message.answer(
            "🛑 <b>Невідомий формат тексту.</b>\nВнось дані через кнопки або пиши у вигляді: "
            "<code>Назва вага</code> (наприклад: <code>Гречка 120</code>).", parse_mode="HTML",
        )

    query_name = match.group(1).strip()
    grams = float(match.group(2).replace(",", "."))
    today = datetime.now().strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено. Натисніть /start")
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if food_day and food_day.is_closed: return await message.answer("🔒 Ваш день вже закрито. Ви не можете додавати продукти.")
        
        # Додаткова зручність: якщо клієнт пише просто "Овочі 200"
        if query_name.lower() in ["овочі", "овоч"]:
            session.add(FoodEntry(user_id=user.id, date=today, category="veggies", product_name="Овочі", amount=grams, portions=0))
            await session.commit()
            await message.answer(
                f"🚀 <b>Експрес-запис:</b> внесено {grams:g} г — <b>Овочі</b>.\n\n" + await get_client_dashboard(user.id),
                reply_markup=client_categories_keyboard(), parse_mode="HTML",
            )
            return

        matched_products = (await session.execute(select(FoodProduct).where(FoodProduct.name.like(f"%{query_name}%")))).scalars().all()

    if not matched_products:
        return await message.answer(f"❌ Продукту з назвою <b>«{html.escape(query_name)}»</b> не знайдено у меню тренера.", parse_mode="HTML")

    if len(matched_products) == 1:
        prod = matched_products[0]
        portions = grams / prod.size if prod.category != "veggies" else 0
        async with AsyncSessionLocal() as session:
            session.add(FoodEntry(user_id=user.id, date=today, category=prod.category, product_name=prod.name, amount=grams, portions=portions))
            await session.commit()
        await message.answer(
            f"🚀 <b>Експрес-запис:</b> внесено {grams:g} {prod.unit} — <b>{prod.name}</b>.\n\n" + await get_client_dashboard(user.id),
            reply_markup=client_categories_keyboard(), parse_mode="HTML",
        )
    else:
        builder = InlineKeyboardBuilder()
        for p in matched_products:
            builder.button(text=p.name, callback_data=f"cl_fastlog_{p.id}_{int(grams)}")
        builder.adjust(1)
        await message.answer(f"🔍 Знайдено декілька збігів за назвою <b>«{html.escape(query_name)}»</b>. Оберіть точний варіант:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("cl_fastlog_"))
async def cal_cl_fastlog_confirm(callback: types.CallbackQuery, state: FSMContext):
    _, _, pid_str, grams_str = callback.data.split("_")
    pid, grams = int(pid_str), float(grams_str)

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        prod = await session.get(FoodProduct, pid)
        today = datetime.now().strftime("%Y-%m-%d")
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if food_day and food_day.is_closed: return await callback.answer("🔒 День вже закрито.", show_alert=True)

        portions = grams / prod.size if prod.category != "veggies" else 0
        session.add(FoodEntry(user_id=user.id, date=today, category=prod.category, product_name=prod.name, amount=grams, portions=portions))
        await session.commit()

    await callback.answer(f"Записано: {prod.name}")
    await cal_client_food_home(callback, state)


# ============================================================
# ПРОЦЕС ЗАКРИТТЯ ДНЯ
# ============================================================
@router.callback_query(F.data == "client_open_day")
async def cal_client_open_day(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if food_day:
            food_day.is_closed = False
            await session.commit()

    await callback.message.edit_text(await get_client_dashboard(user.id), reply_markup=client_categories_keyboard(is_closed=False), parse_mode="HTML")
    await callback.answer("🔓 День знову відкрито для редагування!")

@router.callback_query(F.data == "client_close_day")
async def cal_client_close_day_start(callback: types.CallbackQuery, state: FSMContext):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        if not food_day:
            food_day = FoodDay(user_id=user.id, date=today)
            session.add(food_day)
            await session.commit()

        current_steps = food_day.steps
        current_workout = food_day.workout_done
        current_wellbeing = food_day.wellbeing
        current_comment = food_day.comment or ""

    await state.set_state(CloseDayFSM.waiting_for_steps)
    await state.update_data(
        edit_msg_id=callback.message.message_id,
        steps=current_steps, workout=current_workout,
        wellbeing=current_wellbeing, comment=current_comment,
    )
    kb = InlineKeyboardBuilder().button(text="🔙 Скасувати", callback_data="client_food_home").as_markup()
    hint = f"\n<i>(Поточне значення: {current_steps})</i>" if current_steps else ""
    await callback.message.edit_text(
        f"🔒 <b>Закриття дня (Крок 1 з 4)</b>\n\nСкільки кроків ви пройшли за сьогодні?{hint}\n(Введіть число)",
        parse_mode="HTML", reply_markup=kb,
    )
    await callback.answer()

@router.message(StateFilter(CloseDayFSM.waiting_for_steps))
async def process_close_steps(message: types.Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit(): return await message.answer("❌ Введіть ціле число.")
    data = await state.get_data()
    await state.update_data(steps=int(message.text))
    await state.set_state(CloseDayFSM.waiting_for_workout)
    try: await message.delete()
    except: pass
    await bot.edit_message_text(
        "🏋️ <b>Крок 2 з 4</b>\n\nЧи було сьогодні тренування?",
        chat_id=message.chat.id, message_id=data["edit_msg_id"],
        reply_markup=close_day_yes_no_keyboard(), parse_mode="HTML",
    )

@router.callback_query(F.data.startswith("cd_workout_"))
async def process_close_workout(callback: types.CallbackQuery, state: FSMContext):
    is_done = (callback.data == "cd_workout_yes")
    await state.update_data(workout=is_done)
    await state.set_state(CloseDayFSM.waiting_for_wellbeing)
    await callback.message.edit_text(
        "😊 <b>Крок 3 з 4</b>\n\nОцініть ваше загальне самопочуття за день (від 1 до 5):",
        reply_markup=close_day_scale_keyboard("wb"), parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cd_wb_"))
async def process_close_wellbeing(callback: types.CallbackQuery, state: FSMContext):
    val = int(callback.data.split("_")[2])
    await state.update_data(wellbeing=val)
    await state.set_state(CloseDayFSM.waiting_for_comment)
    await callback.message.edit_text(
        "💬 <b>Крок 4 з 4</b>\n\nНапишіть короткий коментар тренеру за день (або натисніть 'Пропустити'):",
        reply_markup=close_day_skip_keyboard(), parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "cd_skip_comment")
async def process_close_skip_comment(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        await state.update_data(comment="")
        await render_final_report_preview(callback.message.chat.id, callback.message.message_id, user.id, state, callback.bot)
    await callback.answer()

@router.message(StateFilter(CloseDayFSM.waiting_for_comment))
async def process_close_comment(message: types.Message, state: FSMContext, bot: Bot):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено.")
        await state.update_data(comment=message.text.strip())
        data = await state.get_data()
        edit_msg_id = data.get("edit_msg_id", message.message_id)
        await render_final_report_preview(message.chat.id, edit_msg_id, user.id, state, bot)

async def render_final_report_preview(chat_id: int, message_id: int, uid: int, state: FSMContext, bot: Bot):
    today = datetime.now().strftime("%Y-%m-%d")
    data = await state.get_data()

    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()

        if food_day and data.get("steps") is not None:
            food_day.steps = data["steps"]
            food_day.workout_done = data["workout"]
            food_day.wellbeing = data["wellbeing"]
            food_day.comment = data["comment"]
            await session.commit()

    await state.clear()
    summary = await get_client_dashboard(user.id, today)

    async with AsyncSessionLocal() as session:
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        final_text = (
            f"📊 <b>Фінальна перевірка перед відправкою</b>\n\n"
            f"🏃 Кроки: <b>{food_day.steps if food_day else 0}</b>\n"
            f"🏋️ Тренування: <b>{'✅ Було' if (food_day and food_day.workout_done) else '❌ Не було'}</b>\n"
            f"😊 Самопочуття: <b>{food_day.wellbeing if food_day else 0}/5</b>\n"
            f"💬 Коментар: <i>{html.escape(food_day.comment or 'Немає')}</i>\n\n"
            f"{summary}\n\n"
            f"Все вірно? Відправляємо звіт тренеру?"
        )

    try:
        await bot.edit_message_text(final_text, chat_id=chat_id, message_id=message_id, reply_markup=client_close_day_confirm_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не вдалося редагувати повідомлення: {e}")
        await bot.send_message(chat_id, final_text, reply_markup=client_close_day_confirm_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "cl_restart_close_fsm")
async def cal_restart_close_fsm(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CloseDayFSM.waiting_for_steps)
    await state.update_data(edit_msg_id=callback.message.message_id)
    kb = InlineKeyboardBuilder().button(text="🔙 Скасувати", callback_data="client_food_home").as_markup()
    await callback.message.edit_text("🔒 <b>Оновлення даних (Крок 1 з 4)</b>\n\nСкільки кроків ви пройшли за сьогодні?\n(Введіть число)", parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "cl_confirm_close_day")
async def cal_confirm_close_day(callback: types.CallbackQuery, bot: Bot):
    uid = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == user.id, FoodDay.date == today))).scalars().first()
        target = await session.get(ClientTarget, user.id)

        if food_day:
            food_day.is_closed = True
            await session.commit()

        entries = (await session.execute(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.date == today).order_by(FoodEntry.time_added))).scalars().all()
        rows = (await session.execute(text("SELECT category, SUM(portions), SUM(amount) FROM food_entries WHERE user_id = :uid AND date = :dt GROUP BY category"), {"uid": user.id, "dt": today})).all()

    totals = {cat: 0.0 for cat in CATEGORY_TITLES}
    amounts = {cat: 0.0 for cat in CATEGORY_TITLES}
    for cat, total_portions, total_amount in rows:
        if cat in totals:
            totals[cat] = float(total_portions or 0)
            amounts[cat] = float(total_amount or 0)

    warning_flag = ""
    report_macro = ""
    for cat_key, title in CATEGORY_TITLES.items():
        curr = totals[cat_key]
        base_tgt = getattr(target, TARGET_FIELD[cat_key])
        swap_val = getattr(food_day, f"swap_{cat_key}", 0.0) if food_day else 0.0
        tgt = base_tgt + swap_val

        if cat_key == "veggies":
            report_macro += f"  {title}: {amounts[cat_key]:g} г\n"
        elif cat_key == "other":
            report_macro += f"  {title}: {amounts[cat_key]:g}/{tgt:g} шт.\n"
        else:
            ratio = (curr / tgt) if tgt > 0 else 0
            if ratio < 0.7 or ratio > 1.2:
                warning_flag = "⚠️ <b>Потребує уваги (Макроси порушено)</b>\n"
            report_macro += f"  {title}: {curr:g}/{tgt:g} порц.\n"

    diary_lines = ""
    for e in entries:
        if e.category == "veggies": val_str = f"{e.amount:g} г"
        elif e.category == "other":
            if e.amount == 1 and e.portions == 1: val_str = "1 шт."
            else: val_str = f"{e.amount:g} г"
        else: val_str = f"{e.amount:g} г ({e.portions:.1f} порц.)"
        diary_lines += f"▫️ {e.time_added} | {html.escape(e.product_name)} ({val_str})\n"

    day_number = (datetime.strptime(today, "%Y-%m-%d") - user.created_at).days + 1
    trainer_notes = target.trainer_notes if target and target.trainer_notes else None
    notes_block = f"\n📝 <b>Нотатки тренера:</b>\n{html.escape(trainer_notes)}\n" if trainer_notes else ""

    trainer_report = (
        f"📋 <b>ЗВІТ КЛІЄНТА: {html.escape(user.full_name)}</b> | День {day_number} ({today})\n"
        f"{warning_flag}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃 Кроки: <b>{food_day.steps if food_day else 0}</b>\n"
        f"🏋️ Тренування: <b>{'✅ Було' if (food_day and food_day.workout_done) else '❌ Не було'}</b>\n"
        f"📊 Самопочуття: <b>{food_day.wellbeing if food_day else 0}/5</b>\n"
        f"💬 Коментар: <i>{html.escape(food_day.comment if food_day and food_day.comment else 'Немає')}</i>\n"
        f"{notes_block}"
        f"\n🎯 <b>Виконання порцій:</b>\n"
        f"{report_macro}\n"
        f"📝 <b>Щоденник їжі:</b>\n"
        f"{diary_lines if diary_lines else '<i>Порожньо</i>'}"
    )

    max_len = 4000
    parts = [trainer_report[i:i+max_len] for i in range(0, len(trainer_report), max_len)]

    for admin_id in ADMIN_IDS:
        try:
            for idx, part in enumerate(parts):
                reply_markup = trainer_report_reply_keyboard(user.id, today) if idx == 0 else None
                await bot.send_message(admin_id, part, parse_mode="HTML", reply_markup=reply_markup)
        except Exception: pass

    await callback.message.edit_text("✅ <b>День успішно закрито!</b>\nВаш звіт відправлено тренеру.", parse_mode="HTML")
    await callback.answer()


# ============================================================
# НОВІ ФУНКЦІЇ: ІСТОРІЯ ТА ВАГА
# ============================================================
@router.message(F.text == "📅 Історія")
async def cmd_history(message: types.Message, state: FSMContext):
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    await state.update_data(history_date=today)
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено.")
    await show_history_day(message, user.id, today, state)

async def show_history_day(target, user_id: int, date_str: str, state: FSMContext):
    dash = await get_client_dashboard(user_id, date_str)
    kb = history_navigation_keyboard(date_str)
    if isinstance(target, types.Message):
        await target.answer(dash, reply_markup=kb, parse_mode="HTML")
    else: 
        await target.message.edit_text(dash, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("hist_"))
async def cal_history_nav(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    data = await state.get_data()
    current_date = data.get("history_date", datetime.now().strftime("%Y-%m-%d"))
    dt = datetime.strptime(current_date, "%Y-%m-%d")
    if action == "prev": dt -= timedelta(days=1)
    elif action == "next": dt += timedelta(days=1)
    elif action == "today": dt = datetime.now()
    new_date = dt.strftime("%Y-%m-%d")
    await state.update_data(history_date=new_date)
    uid = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
    await show_history_day(callback, user.id, new_date, state)
    await callback.answer()


@router.message(F.text == "⚖️ Моя вага")
async def cmd_weight(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await message.answer("❌ Профіль не знайдено.")
        weights = (await session.execute(select(WeightEntry).where(WeightEntry.user_id == user.id).order_by(desc(WeightEntry.date)).limit(10))).scalars().all()
    
    text = "⚖️ <b>Трекінг ваги</b>\n\n"
    if weights:
        text += "Останні записи:\n"
        for w in weights:
            text += f"  {w.date}: <b>{w.weight:.1f} кг</b>"
            if w.note: text += f" ({html.escape(w.note)})"
            text += "\n"
        last = weights[0]
        text += f"\nОстання зафіксована вага: <b>{last.weight:.1f} кг</b> ({last.date})"
    else:
        text += "Немає записів ваги. Додайте перший!"
    
    kb = weight_main_keyboard()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "weight_add")
async def cal_weight_add(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(WeightFSM.waiting_for_weight)
    await callback.message.edit_text(
        "⚖️ Введіть вагу в кілограмах (наприклад, 75.5):",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Скасувати", callback_data="weight_cancel").as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "weight_cancel")
async def cal_weight_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_weight(callback.message, state)
    await callback.answer()

@router.message(StateFilter(WeightFSM.waiting_for_weight))
async def process_weight_input(message: types.Message, state: FSMContext):
    val = _parse_float(message.text)
    if val is None or val <= 0: return await message.answer("❌ Введіть додатне число!")
    today = datetime.now().strftime("%Y-%m-%d")
    uid = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user:
            await state.clear()
            return await message.answer("❌ Профіль не знайдено.")
        existing = (await session.execute(select(WeightEntry).where(WeightEntry.user_id == user.id, WeightEntry.date == today))).scalars().first()
        if existing:
            existing.weight = val
            existing.note = None
        else:
            session.add(WeightEntry(user_id=user.id, date=today, weight=val))
        await session.commit()
        
    await state.clear()
    await message.answer(f"✅ Записано вагу: <b>{val:.1f} кг</b>", parse_mode="HTML")
    await cmd_weight(message, state)

@router.callback_query(F.data == "weight_graph")
async def cal_weight_graph(callback: types.CallbackQuery):
    await callback.answer("📊 Графік ваги тимчасово недоступний.", show_alert=True)

@router.callback_query(F.data == "weight_list")
async def cal_weight_list(callback: types.CallbackQuery):
    uid = callback.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        weights = (await session.execute(select(WeightEntry).where(WeightEntry.user_id == user.id).order_by(desc(WeightEntry.date)))).scalars().all()
        
    if not weights: return await callback.answer("Немає записів.", show_alert=True)
    text = "📋 <b>Всі записи ваги:</b>\n\n"
    for w in weights:
        text += f"  {w.date}: <b>{w.weight:.1f} кг</b>"
        if w.note: text += f" ({html.escape(w.note)})"
        text += "\n"
        
    await callback.message.edit_text(text, reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="weight_back").as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "weight_back")
async def cal_weight_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_weight(callback.message, state)
    await callback.answer()