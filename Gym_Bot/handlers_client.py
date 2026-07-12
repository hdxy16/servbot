# Gym_Bot/handlers_client.py
import re
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, text, delete

from config import ADMIN_IDS
from database import AsyncSessionLocal, User, ClientTarget, FoodEntry, InviteToken, FoodProduct, WeightLog, DayClosure
from keyboards import client_main_keyboard, trainer_main_keyboard, client_categories_keyboard, client_products_keyboard

router = Router()

class ClientLogFSM(StatesGroup):
    waiting_for_grams = State()
    waiting_for_pure_veggies = State()
    waiting_for_weight = State()

CAT_EMOJIS = {"protein": "🥩 Білки", "carbs": "🍚 Вуглеводи", "fats": "🥜 Жири", "fruits": "🍎 Фрукти"}

def generate_visual_bar(current: float, target: float) -> str:
    if target <= 0: return "<code>[░░░░░░░░░░]</code>"
    ratio = min(current / target, 1.0)
    filled = int(ratio * 10)
    bar = "🟩" * filled + "⬜" * (10 - filled)
    return f"<code>{bar}</code>"

async def get_weight_delta_str(session, user_id: int) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    res_now = await session.execute(select(WeightLog).where(WeightLog.user_id == user_id).order_by(WeightLog.date.desc()).limit(1))
    latest_log = res_now.scalar_one_or_none()
    if not latest_log: return "Вага: <code>не вносилась</code>"
    
    res_7 = await session.execute(select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.date <= seven_days_ago).order_by(WeightLog.date.desc()).limit(1))
    old_log = res_7.scalar_one_or_none()
    
    delta_str = ""
    if old_log:
        diff = latest_log.weight - old_log.weight
        sign = "+" if diff > 0 else ""
        delta_str = f" ({sign}{diff:.1f} кг за тиждень)"
        
    return f"⚖️ Поточна вага: <b>{latest_log.weight:.1f} кг</b>{delta_str}"

async def get_client_dashboard(user_id: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, user_id)
        # ЗАХИСТ: Якщо плану немає, створюємо дефолтний автоматично прямо тут[cite: 3]
        if not target:
            target = ClientTarget(user_id=user_id, protein_target=3.5, carbs_target=3.0, fats_target=3.0, fruits_target=1.0, veggies_target=400.0)
            session.add(target)
            await session.commit()
            target = await session.get(ClientTarget, user_id)

        user_obj = await session.get(User, user_id)
        streak_val = user_obj.streak if user_obj else 0
        
        query = text("""
            SELECT category, SUM(amount), SUM(portions) 
            FROM food_entries 
            WHERE user_id = :uid AND date = :dt 
            GROUP BY category
        """)
        rows = (await session.execute(query, {"uid": user_id, "dt": today})).all()
        
        closure_check = await session.execute(select(DayClosure).where(DayClosure.user_id == user_id, DayClosure.date == today))
        is_day_closed = closure_check.scalar_one_or_none() is not None
        
        weight_text = await get_weight_delta_str(session, user_id)
        
    totals = {"protein": 0.0, "carbs": 0.0, "fats": 0.0, "fruits": 0.0, "veggies": 0.0}
    for r in rows:
        if r[0] == "veggies": totals["veggies"] = float(r[1] or 0)
        else: totals[r[0]] = float(r[2] or 0)
        
    def check_mark(curr, target_val): return "✅" if curr >= target_val else "⏳"
    
    status_day = "\n🔒 <b>ЦЕЙ ДЕНЬ УСПІШНО ЗАКРИТО ТРЕНЕРУ!</b>" if is_day_closed else ""
    streak_emoji = "🔥" if streak_val > 0 else "🎯"
    
    return (
        f"🍏 <b>Щоденник харчування</b>\n"
        f"Дата: <b>{datetime.now().strftime('%d.%m.%Y')}</b>\n"
        f"{streak_emoji} Дисципліна: <b>{streak_val} днів поспіль</b>\n"
        f"{weight_text}{status_day}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥩 <b>Білки:</b> {totals['protein']:.2f} / {target.protein_target:.1f} порц. {check_mark(totals['protein'], target.protein_target)}\n"
        f"{generate_visual_bar(totals['protein'], target.protein_target)}\n\n"
        f"🍚 <b>Вуглеводи:</b> {totals['carbs']:.2f} / {target.carbs_target:.1f} порц. {check_mark(totals['carbs'], target.carbs_target)}\n"
        f"{generate_visual_bar(totals['carbs'], target.carbs_target)}\n\n"
        f"🥜 <b>Жири:</b> {totals['fats']:.2f} / {target.fats_target:.1f} порц. {check_mark(totals['fats'], target.fats_target)}\n"
        f"{generate_visual_bar(totals['fats'], target.fats_target)}\n\n"
        f"🍎 <b>Фрукти:</b> {totals['fruits']:.2f} / {target.fruits_target:.1f} порц. {check_mark(totals['fruits'], target.fruits_target)}\n"
        f"{generate_visual_bar(totals['fruits'], target.fruits_target)}\n\n"
        f"🥗 <b>Овочі:</b> {int(totals['veggies'])} / {int(target.veggies_target)} г {check_mark(totals['veggies'], target.veggies_target)}\n"
        f"{generate_visual_bar(totals['veggies'], target.veggies_target)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>💡 Порада: Ти можеш просто написати в чат текст виду: 'Гречка 120' для миттєвого внесення ваги!</i>"
    )

# ЗАХИСТ: Додано state="*" для розблокування при будь-яких підвислих станах
@router.message(F.text == "🍏 Мій раціон")
async def cl_diet_menu(message: types.Message, state: FSMContext):
    await state.clear()  # Примусово збиваємо будь-який старий діалог
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
    if not user: 
        return await message.answer("❌ Ваш профіль не знайдено в базі. Натисніть /start")
    
    dash = await get_client_dashboard(user.id)
    await message.answer(dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "client_food_home")
async def cal_client_food_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
    if not user:
        return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
    dash = await get_client_dashboard(user.id)
    await callback.message.edit_text(text=dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "client_view_logs")
async def cal_client_view_logs(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        if not user: return await callback.answer("❌ Профіль не знайдено.", show_alert=True)
        res = await session.execute(select(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.date == today))
        entries = res.scalars().all()
        
    if not entries: return await callback.answer("📭 Сьогодні ви ще не вносили продуктів.", show_alert=True)
        
    builder = InlineKeyboardBuilder()
    text_data = "📝 <b>Зважені продукти за сьогодні:</b>\n\n"
    for e in entries:
        portions_info = f"({e.portions:.2f} порц.)" if e.category != "veggies" else ""
        text_data += f"• <b>{e.product_name}</b>: {e.amount:g} г/шт {portions_info}\n"
        builder.button(text=f"❌ Видалити {e.product_name[:12]}...", callback_data=f"cl_dellog_{e.id}")
        
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
    await callback.answer("🗑️ Запис видалено з журналу!")
    await cal_client_view_logs(callback)

@router.callback_query(F.data.startswith("client_cat_"))
async def cal_client_cat(callback: types.CallbackQuery):
    cat = callback.data.replace("client_cat_", "")
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(FoodProduct).where(FoodProduct.category == cat).order_by(FoodProduct.name))
        products_list = res.scalars().all()
    await callback.message.edit_text(text=f"⬇️ <b>Оберіть продукт з бази даних: {CAT_EMOJIS[cat]}</b>", reply_markup=client_products_keyboard(products_list, cat), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("cl_dbprod_"))
async def cal_client_dbproduct_click(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
    if not product: return await callback.answer("Продукт не знайдено.", show_alert=True)
    await state.set_state(ClientLogFSM.waiting_for_grams)
    await state.update_data(cat=product.category, name=product.name, size=product.size, unit=product.unit, msg_id=callback.message.message_id)
    await callback.message.edit_text(text=f"✍️ Введіть вагу для: <b>{product.name}</b>\n1 порція = <b>{int(product.size)} {product.unit}</b>:", parse_mode="HTML")

@router.message(ClientLogFSM.waiting_for_grams)
async def process_grams_input(message: types.Message, state: FSMContext, bot: Bot):
    raw = message.text.strip().replace(",", ".")
    if not re.match(r"^\d+(?:\.\d+)?$", raw): return await message.answer("❌ Введіть число!")
    grams = float(raw)
    data = await state.get_data()
    await state.clear()
    portions = grams / data["size"]
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        session.add(FoodEntry(user_id=user.id, date=today, category=data["cat"], product_name=data["name"], amount=grams, portions=portions))
        await session.commit()
    try: await bot.delete_message(chat_id=message.chat.id, message_id=data["msg_id"])
    except Exception: pass
    await message.delete()
    dash = await get_client_dashboard(user.id)
    await message.answer(text=f"✅ Внесено {grams:g} {data['unit']} {data['name']}\n\n" + dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "client_add_veggies")
async def cal_v_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientLogFSM.waiting_for_pure_veggies)
    await state.update_data(msg_id=callback.message.message_id)
    await callback.message.edit_text(text="🥗 Введіть вагу овочів у грамах:")
    await callback.answer()

@router.message(ClientLogFSM.waiting_for_pure_veggies)
async def process_v_input(message: types.Message, state: FSMContext, bot: Bot):
    try: grams = float(message.text.replace(",", "."))
    except ValueError: return await message.answer("❌ Число!")
    data = await state.get_data()
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        session.add(FoodEntry(user_id=user.id, date=today, category="veggies", product_name="Овочі", amount=grams, portions=0.0))
        await session.commit()
    try: await bot.delete_message(chat_id=message.chat.id, message_id=data["msg_id"])
    except Exception: pass
    await message.delete()
    dash = await get_client_dashboard(user.id)
    await message.answer(text=dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "client_clear_day")
async def cal_clear_day(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        await session.execute(delete(FoodEntry).where(FoodEntry.user_id == user.id, FoodEntry.date == today))
        await session.execute(delete(DayClosure).where(DayClosure.user_id == user.id, DayClosure.date == today))
        await session.commit()
    dash = await get_client_dashboard(user.id)
    await callback.message.edit_text(text="🧹 Журнал за сьогодні повністю очищено!", reply_markup=client_categories_keyboard(), parse_mode="HTML")
    await callback.answer()

# ЕКСПРЕС-ВВЕДЕННЯ ПРОДУКТІВ З ТЕКСТУ (ІДЕЯ 1)
@router.message(F.text, ~F.text.startswith("/"), ~F.text.in_([
    "🍏 Мій раціон", "🧪 Тест клієнта", "🧠 В адмінку", "⚙️ Керувати каталогом", "🕒 Налаштувати звіт", "👥 Мої клієнти", "➕ Створити інвайт"
]))
async def text_parsing_express_entry(message: types.Message):
    uid = message.from_user.id
    raw_text = message.text.strip()
    
    match = re.match(r"^([A-Za-яА-ЯёЁіІїЇєЄґҐ\s'\-]+?)\s+(\d+(?:[.,]\d+)?)$", raw_text)
    if not match:
        return await message.answer("🛑 <b>Невідомий формат тексту.</b>\nВнось дані через кнопки або пиши у вигляді: <code>Назва вага</code> (наприклад: <code>Гречка 120</code>).", parse_mode="HTML")
        
    query_name = match.group(1).strip()
    grams = float(match.group(2).replace(",", "."))
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return
        
        res = await session.execute(select(FoodProduct).where(FoodProduct.name.like(f"%{query_name}%")))
        matched_products = res.scalars().all()
        
    if not matched_products:
        return await message.answer(f"❌ Продукту з назвою <b>«{query_name}»</b> не знайдено у каталозі тренера.", parse_mode="HTML")
        
    if len(matched_products) == 1:
        prod = matched_products[0]
        portions = grams / prod.size
        today = datetime.now().strftime("%Y-%m-%d")
        
        async with AsyncSessionLocal() as session:
            session.add(FoodEntry(user_id=user.id, date=today, category=prod.category, product_name=prod.name, amount=grams, portions=portions))
            await session.commit()
            
        dash = await get_client_dashboard(user.id)
        await message.answer(f"🚀 <b>Експрес-запис:</b> внесено {grams:g} {prod.unit} продукту <b>{prod.name}</b>.\n\n" + dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")
    else:
        builder = InlineKeyboardBuilder()
        for p in matched_products:
            builder.button(text=f"{p.name}", callback_data=f"cl_fastlog_{p.id}_{int(grams)}")
        builder.adjust(1)
        await message.answer(f"🔍 Знайдено декілька збігів за назвою <b>«{query_name}»</b>. Оберіть точний варіант:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("cl_fastlog_"))
async def cal_cl_fastlog_confirm(callback: types.CallbackQuery):
    _, _, pid_str, grams_str = callback.data.split("_")
    pid = int(pid_str)
    grams = float(grams_str)
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        prod = await session.get(FoodProduct, pid)
        if prod and user:
            portions = grams / prod.size
            today = datetime.now().strftime("%Y-%m-%d")
            session.add(FoodEntry(user_id=user.id, date=today, category=prod.category, product_name=prod.name, amount=grams, portions=portions))
            await session.commit()
            await callback.answer(f"Записано: {prod.name}")
            dash = await get_client_dashboard(user.id)
            await callback.message.edit_text(text=dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "client_weight_log")
async def cal_client_weight_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientLogFSM.waiting_for_weight)
    await state.update_data(msg_id=callback.message.message_id)
    await callback.message.edit_text("⚖️ Введіть вашу **поточну ранкову вагу** в кілограмах (наприклад <code>74.5</code>):", parse_mode="HTML")
    await callback.answer()

@router.message(ClientLogFSM.waiting_for_weight)
async def process_client_weight_input(message: types.Message, state: FSMContext, bot: Bot):
    raw = message.text.strip().replace(",", ".")
    if not re.match(r"^\d+(?:\.\d+)?$", raw): return await message.answer("❌ Введіть число!")
        
    weight = float(raw)
    data = await state.get_data()
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        if user:
            await session.execute(delete(WeightLog).where(WeightLog.user_id == user.id, WeightLog.date == today))
            session.add(WeightLog(user_id=user.id, date=today, weight=weight))
            await session.commit()
            
    try: await bot.delete_message(chat_id=message.chat.id, message_id=data["msg_id"])
    except Exception: pass
    await message.delete()
    
    dash = await get_client_dashboard(user.id)
    await message.answer(text="⚖️ Вагу успішно зафіксовано в системі!\n\n" + dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "client_close_day")
async def cal_client_close_day_trigger(callback: types.CallbackQuery, bot: Bot):
    uid = callback.from_user.id
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user: return
        
        already_closed = await session.execute(select(DayClosure).where(DayClosure.user_id == user.id, DayClosure.date == today_str))
        if already_closed.scalar_one_or_none():
            return await callback.answer("🔒 Цей день уже закритий тренеру!", show_alert=True)
            
        if user.last_closed_date == yesterday_str: user.streak += 1
        elif user.last_closed_date != today_str: user.streak = 1
            
        user.last_closed_date = today_str
        session.add(DayClosure(user_id=user.id, date=today_str))
        
        query = text("SELECT category, SUM(portions) FROM food_entries WHERE user_id = :uid AND date = :dt GROUP BY category")
        rows = (await session.execute(query, {"uid": user.id, "dt": today_str})).all()
        target = await session.get(ClientTarget, user.id)
        await session.commit()
        
    totals = {"protein": 0.0, "carbs": 0.0, "fats": 0.0, "fruits": 0.0}
    for r in rows:
        if r[0] in totals: totals[r[0]] = float(r[1] or 0)
        
    await callback.answer("🔒 День успішно зафіксовано та надіслано тренеру!", show_alert=True)
    dash = await get_client_dashboard(user.id)
    await callback.message.edit_text(text=dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")
    
    trainer_push = (
        f"🔥 <b>Клієнт закрив день дисципліни!</b>\n"
        f"Спортсмен: <b>{user.full_name}</b>\n"
        f"Серія регулярності: <b>{user.streak} днів поспіль</b>\n\n"
        f"📊 <b>Виконання плану:</b>\n"
        f"  🥩 Б: {totals['protein']:.1f}/{target.protein_target:.1f} порц.\n"
        f"  🍚 В: {totals['carbs']:.1f}/{target.carbs_target:.1f} порц.\n"
        f"  🥜 Ж: {totals['fats']:.1f}/{target.fats_target:.1f} порц."
    )
    for trainer_id in ADMIN_IDS:
        try: await bot.send_message(chat_id=trainer_id, text=trainer_push, parse_mode="HTML")
        except Exception: pass