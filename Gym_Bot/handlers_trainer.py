# Gym_Bot/handlers_trainer.py
import re  # <-- ОЦЕЙ ІМПОРТ ОБОВ'ЯЗКОВО ДОДАТИ
import uuid
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete, text

from config import ADMIN_IDS
from database import AsyncSessionLocal, User, ClientTarget, FoodEntry, InviteToken, FoodProduct, WeightLog, DayClosure
from keyboards import (
    trainer_main_keyboard, trainer_clients_keyboard, trainer_client_manage_keyboard, 
    client_main_keyboard, client_categories_keyboard, trainer_catalog_categories_keyboard,
    trainer_products_management_keyboard, trainer_product_actions_keyboard, trainer_report_time_keyboard
)

from handlers_client import get_client_dashboard, get_weight_delta_str

router = Router()

class EditTargetFSM(StatesGroup):
    waiting_for_protein = State()
    waiting_for_carbs = State()
    waiting_for_fats = State()
    waiting_for_fruits = State()
    waiting_for_veggies = State()

class CatalogManageFSM(StatesGroup):
    waiting_for_name = State()
    waiting_for_size = State()
    waiting_for_unit = State()
    waiting_for_new_portion = State()
    waiting_for_report_time = State() # Стан часу звіту

CAT_TITLES = {"protein": "🥩 Білки", "carbs": "🍚 Вуглеводи", "fats": "🥜 Жири", "fruits": "🍎 Фрукти"}

def is_trainer(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# НАЛАШТУВАННЯ ЧАСУ ЗВІТІВ (ІДЕЯ 2)
@router.message(F.text == "🕒 Налаштувати звіт")
async def cmd_setup_report_time(message: types.Message):
    if not is_trainer(message.from_user.id): return
    async with AsyncSessionLocal() as session:
        trainer = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        current_time = trainer.digest_time if trainer else "21:00"
    await message.answer(
        text=f"🕒 <b>Управління часом щоденного рапорту клієнтів</b>\n\nПоточний час пушу: <b>{current_time}</b>\n"
             f"Оберіть швидкий пресет або введіть свій час:",
        reply_markup=trainer_report_time_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("tr_settime_"))
async def cal_tr_set_report_time(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return
    action = callback.data.replace("tr_settime_", "")
    
    if action == "manual":
        await state.set_state(CatalogManageFSM.waiting_for_report_time)
        await state.update_data(msg_id=callback.message.message_id)
        return await callback.message.edit_text("✍️ Введіть час у форматі <b>ГГ:ХХ</b> (наприклад, <code>20:30</code>):", parse_mode="HTML")
        
    async with AsyncSessionLocal() as session:
        trainer = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalars().first()
        if trainer:
            trainer.digest_time = action
            await session.commit()
            
    await callback.answer(f"Час розсилки змінено на {action}")
    await callback.message.edit_text(f"✅ Успішно! Автоматичний щоденний рапорт надходитиме о <b>{action}</b>.", parse_mode="HTML")

@router.message(CatalogManageFSM.waiting_for_report_time)
async def process_manual_report_time(message: types.Message, state: FSMContext, bot: Bot):
    raw_time = message.text.strip()
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", raw_time):
        return await message.answer("❌ Невірний формат. Введіть час як: <code>21:15</code>", parse_mode="HTML")
        
    data = await state.get_data()
    await state.clear()
    await message.delete()
    
    async with AsyncSessionLocal() as session:
        trainer = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalars().first()
        if trainer:
            trainer.digest_time = raw_time
            await session.commit()
            
    await bot.edit_message_text(text=f"✅ Успішно! Автоматичний щоденний рапорт надходитиме о <b>{raw_time}</b>.", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

# ОНОВЛЕНИЙ ПЕРЕГЛЯД КЛІЄНТА (ДЕЛІТА ВАГИ + СТРІКИ)
@router.callback_query(F.data.startswith("tr_view_"))
async def cal_tr_view(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    client_id = int(callback.data.split("_")[2])
    
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        target = await session.get(ClientTarget, client_id)
        weight_text = await get_weight_delta_str(session, client_id)
        
    if not client: return await callback.answer("Клієнта не знайдено.")
    
    text_data = (
        f"👤 <b>Клієнт: {client.full_name}</b>\n"
        f"Username: @{client.username or 'немає'}\n"
        f"🔥 Стрік дисципліни: <b>{client.streak} днів</b>\n"
        f"{weight_text}\n\n"
        f"🎯 <b>Поточні норми плану:</b>\n"
        f"  🥩 Білки: <b>{target.protein_target:.2f} порц.</b>\n"
        f"  🍚 Вуглеводи: <b>{target.carbs_target:.2f} порц.</b>\n"
        f"  🥜 Жири: <b>{target.fats_target:.2f} порц.</b>\n"
        f"  🍎 Фрукти: <b>{target.fruits_target:.2f} порц.</b>\n"
        f"  🥗 Овочі: <b>{int(target.veggies_target)} г</b>"
    )
    await callback.message.edit_text(text_data, reply_markup=trainer_client_manage_keyboard(client_id), parse_mode="HTML")
    await callback.answer()

# КЕРУВАННЯ КАТАЛОГОМ ТА БАЗОВИЙ CRUD
@router.message(F.text == "⚙️ Керувати каталогом")
async def cmd_manage_catalog(message: types.Message):
    if not is_trainer(message.from_user.id): return
    await message.answer("🗄️ <b>Панель управління базою продуктів</b>\n\nОберіть категорію:", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "tr_catmanage_back")
async def cal_tr_cat_back(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    await callback.message.edit_text("🗄️ <b>Панель управління базою продуктів</b>\n\nОберіть категорію:", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_catmanage_"))
async def cal_tr_show_category_products(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    cat = callback.data.replace("tr_catmanage_", "")
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(FoodProduct).where(FoodProduct.category == cat).order_by(FoodProduct.name))
        products = res.scalars().all()
    await callback.message.edit_text(text=f"🛒 Список продуктів у <b>{CAT_TITLES[cat]}</b>:", reply_markup=trainer_products_management_keyboard(products, cat), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "tr_paction_cancel")
async def cal_paction_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🗄️ <b>Панель управління базою продуктів</b>", reply_markup=trainer_catalog_categories_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_propt_"))
async def cal_tr_product_options(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
    await callback.message.edit_text(text=f"⚙️ <b>Керування: {product.name}</b>\n\nВага однієї порції: <b>{int(product.size)} {product.unit}</b>", reply_markup=trainer_product_actions_keyboard(pid), parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_paction_del_"))
async def cal_tr_delete_product(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, pid)
        if product:
            await session.delete(product)
            await session.commit()
    await callback.answer("🗑️ Продукт видалено з бази!", show_alert=True)
    await cal_tr_cat_back(callback)

@router.callback_query(F.data.startswith("tr_paction_edit_"))
async def cal_tr_edit_portion_start(callback: types.CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[3])
    await state.set_state(CatalogManageFSM.waiting_for_new_portion)
    await state.update_data(pid=pid, msg_id=callback.message.message_id)
    await callback.message.edit_text("⚖️ Введіть нову чисту вагу однієї порції:")

@router.message(CatalogManageFSM.waiting_for_new_portion)
async def process_tr_saving_portion(message: types.Message, state: FSMContext, bot: Bot):
    raw = message.text.strip().replace(",", ".")
    new_size = float(raw)
    data = await state.get_data()
    await state.clear()
    await message.delete()
    async with AsyncSessionLocal() as session:
        product = await session.get(FoodProduct, data["pid"])
        if product:
            product.size = new_size
            await session.commit()
    kb = InlineKeyboardBuilder().button(text="🔙 До категорій", callback_data="tr_catmanage_back").as_markup()
    await bot.edit_message_text(text=f"✅ Оновлено до <b>{int(new_size)} {product.unit}</b>!", chat_id=message.chat.id, message_id=data["msg_id"], reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_addprod_"))
async def cal_tr_add_product_start(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.replace("tr_addprod_", "")
    await state.set_state(CatalogManageFSM.waiting_for_name)
    await state.update_data(cat=cat, msg_id=callback.message.message_id)
    await callback.message.edit_text(text=f"📝 Введіть назву продукту для {CAT_TITLES[cat]}:")

@router.message(CatalogManageFSM.waiting_for_name)
async def process_tr_add_name(message: types.Message, state: FSMContext, bot: Bot):
    p_name = message.text.strip()
    data = await state.get_data()
    await message.delete()
    await state.update_data(name=p_name)
    await state.set_state(CatalogManageFSM.waiting_for_size)
    await bot.edit_message_text(text=f"⚖️ Продукт: <b>{p_name}</b>\n\nВведіть вагу базової порції:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(CatalogManageFSM.waiting_for_size)
async def process_tr_add_size(message: types.Message, state: FSMContext, bot: Bot):
    p_size = float(message.text.strip())
    data = await state.get_data()
    await message.delete()
    await state.update_data(size=p_size)
    await state.set_state(CatalogManageFSM.waiting_for_unit)
    await bot.edit_message_text(text=f"📦 Продукт: <b>{data['name']}</b>\n\nВведіть одиницю виміру (г/шт):", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(CatalogManageFSM.waiting_for_unit)
async def process_tr_add_unit(message: types.Message, state: FSMContext, bot: Bot):
    p_unit = message.text.strip()
    data = await state.get_data()
    await state.clear()
    await message.delete()
    async with AsyncSessionLocal() as session:
        session.add(FoodProduct(category=data["cat"], name=data["name"], size=data["size"], unit=p_unit))
        await session.commit()
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="tr_catmanage_back").as_markup()
    await bot.edit_message_text(text=f"🚀 Продукт <b>{data['name']}</b> успішно додано!", chat_id=message.chat.id, message_id=data["msg_id"], reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🧪 Тест клієнта")
async def cmd_test_client_mode(message: types.Message):
    if not is_trainer(message.from_user.id): return
    uid = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == uid))).scalars().first()
        if not user:
            user = User(telegram_id=uid, username=message.from_user.username, full_name="Тренер (Тест)", role="trainer")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        target = await session.get(ClientTarget, user.id)
        if not target:
            await session.execute(delete(ClientTarget).where(ClientTarget.user_id == user.id))
            session.add(ClientTarget(user_id=user.id, protein_target=3.5, carbs_target=3.0, fats_target=3.0, fruits_target=1.0, veggies_target=400.0))
            await session.commit()
    dash = await get_client_dashboard(user.id)
    await message.answer("🔄 <b>Активовано тестовий режим клієнта.</b>", reply_markup=client_main_keyboard(is_admin=True), parse_mode="HTML")
    await message.answer(dash, reply_markup=client_categories_keyboard(), parse_mode="HTML")

@router.message(F.text == "🧠 В адмінку")
async def cmd_back_to_trainer_mode(message: types.Message):
    if not is_trainer(message.from_user.id): return
    await message.answer("🧠 <b>Повернено в режим Тренера.</b>", reply_markup=trainer_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "➕ Створити інвайт")
async def cmd_create_invite(message: types.Message, bot: Bot):
    if not is_trainer(message.from_user.id): return
    unique_token = str(uuid.uuid4())[:8]
    async with AsyncSessionLocal() as session:
        session.add(InviteToken(token=unique_token))
        await session.commit()
    bot_info = await bot.get_me()
    await message.answer(f"🎟️ <b>Нове посилання для клієнта:</b>\n<code>https://t.me/{bot_info.username}?start={unique_token}</code>", parse_mode="HTML")

@router.message(F.text == "👥 Мої клієнти")
async def cmd_my_clients(message: types.Message):
    if not is_trainer(message.from_user.id): return
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.role == "client").order_by(User.full_name))
        clients = res.scalars().all()
    if not clients: return message.answer("👥 У вас поки немає зареєстрованих клієнтів.")
    await message.answer("📋 <b>Список ваших клієнтів:</b>", reply_markup=trainer_clients_keyboard(clients), parse_mode="HTML")

@router.callback_query(F.data == "tr_list_back")
async def cal_tr_list_back(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.role == "client").order_by(User.full_name))
        clients = res.scalars().all()
    await callback.message.edit_text("📋 <b>Список ваших клієнтів:</b>", reply_markup=trainer_clients_keyboard(clients), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("tr_stats_"))
async def cal_tr_stats(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    client_id = int(callback.data.split("_")[2])
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        target = await session.get(ClientTarget, client_id)
        query = text("SELECT category, SUM(amount), SUM(portions) FROM food_entries WHERE user_id = :uid AND date = :dt GROUP BY category")
        rows = (await session.execute(query, {"uid": client_id, "dt": today})).all()
    totals = {"protein": 0.0, "carbs": 0.0, "fats": 0.0, "fruits": 0.0, "veggies": 0.0}
    for r in rows:
        if r[0] == "veggies": totals["veggies"] = float(r[1] or 0)
        else: totals[r[0]] = float(r[2] or 0)
    report = (
        f"📊 <b>Сьогоднішній звіт: {client.full_name}</b>\nДата: {datetime.now().strftime('%d.%m.%Y')}\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🥩 Білки: <b>{totals['protein']:.2f}</b> / {target.protein_target:.1f} порц.\n🍚 Вуглеводи: <b>{totals['carbs']:.2f}</b> / {target.carbs_target:.1f} порц.\n"
        f"🥜 Жири: <b>{totals['fats']:.2f}</b> / {target.fats_target:.1f} порц.\n🍎 Фрукти: <b>{totals['fruits']:.2f}</b> / {target.fruits_target:.1f} порц.\n"
        f"🥗 Овочі: <b>{int(totals['veggies'])}г</b> / {int(target.veggies_target)}г\n"
    )
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data=f"tr_view_{client_id}").as_markup()
    await callback.message.edit_text(report, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_edit_"))
async def cal_tr_edit_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_trainer(callback.from_user.id): return
    client_id = int(callback.data.split("_")[2])
    await state.set_state(EditTargetFSM.waiting_for_protein)
    await state.update_data(client_id=client_id, msg_id=callback.message.message_id)
    await callback.message.edit_text("✏️ Введіть нову норму <b>БІЛКІВ</b> (порцій, наприклад <code>3.5</code>):", parse_mode="HTML")

@router.message(EditTargetFSM.waiting_for_protein)
async def process_edit_p(message: types.Message, state: FSMContext, bot: Bot):
    try: val = float(message.text.replace(",", "."))
    except ValueError: return message.answer("❌ Число!")
    await state.update_data(p=val)
    data = await state.get_data()
    await message.delete()
    await state.set_state(EditTargetFSM.waiting_for_carbs)
    await bot.edit_message_text(text="✏️ Введіть нову норму <b>ВУГЛЕВОДІВ</b>:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(EditTargetFSM.waiting_for_carbs)
async def process_edit_c(message: types.Message, state: FSMContext, bot: Bot):
    try: val = float(message.text.replace(",", "."))
    except ValueError: return message.answer("❌ Число!")
    await state.update_data(c=val)
    data = await state.get_data()
    await message.delete()
    await state.set_state(EditTargetFSM.waiting_for_fats)
    await bot.edit_message_text(text="✏️ Введіть нову норму <b>ЖИРІВ</b>:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(EditTargetFSM.waiting_for_fats)
async def process_edit_f(message: types.Message, state: FSMContext, bot: Bot):
    try: val = float(message.text.replace(",", "."))
    except ValueError: return message.answer("❌ Число!")
    await state.update_data(f=val)
    data = await state.get_data()
    await message.delete()
    await state.set_state(EditTargetFSM.waiting_for_fruits)
    await bot.edit_message_text(text="✏️ Введіть нову норму <b>ФРУКТІВ</b>:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(EditTargetFSM.waiting_for_fruits)
async def process_edit_fr(message: types.Message, state: FSMContext, bot: Bot):
    try: val = float(message.text.replace(",", "."))
    except ValueError: return message.answer("❌ Число!")
    await state.update_data(fr=val)
    data = await state.get_data()
    await message.delete()
    await state.set_state(EditTargetFSM.waiting_for_veggies)
    await bot.edit_message_text(text="✏️ Введіть нову норму <b>ОВОЧІВ</b> у грамах:", chat_id=message.chat.id, message_id=data["msg_id"], parse_mode="HTML")

@router.message(EditTargetFSM.waiting_for_veggies)
async def process_edit_v(message: types.Message, state: FSMContext, bot: Bot):
    try: val = float(message.text.replace(",", "."))
    except ValueError: return message.answer("❌ Число!")
    data = await state.get_data()
    await state.clear()
    await message.delete()
    async with AsyncSessionLocal() as session:
        target = await session.get(ClientTarget, data["client_id"])
        if target:
            target.protein_target, target.carbs_target, target.fats_target, target.fruits_target, target.veggies_target = data["p"], data["c"], data["f"], data["fr"], val
            await session.commit()
    kb = InlineKeyboardBuilder().button(text="🔙 До профілю", callback_data=f"tr_view_{data['client_id']}").as_markup()
    await bot.edit_message_text(text="✅ <b>План раціону успішно оновлено!</b>", chat_id=message.chat.id, message_id=data["msg_id"], reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("tr_del_"))
async def cal_tr_del(callback: types.CallbackQuery):
    if not is_trainer(callback.from_user.id): return
    client_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        client = await session.get(User, client_id)
        if client: await session.delete(client)
        await session.commit()
    await callback.answer("Видалено.", show_alert=True)
    await cal_tr_list_back(callback)