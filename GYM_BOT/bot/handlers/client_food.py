import logging
import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsClient
from database.models import User, FoodProduct
from bot.keyboards.food import ClientFoodCB, client_food_main_kb, FOOD_CATEGORIES, search_cancel_kb, products_list_kb
from bot.services import nutrition_service, food_service
from bot.states.food_fsm import ClientFoodFSM

logger = logging.getLogger(__name__)
client_food_router = Router()
client_food_router.message.filter(IsClient())
client_food_router.callback_query.filter(IsClient())

def build_progress_bar(current: float, target: float, length: int = 5) -> str:
    if target <= 0:
        return "✅" if current > 0 else "〰️"
    ratio = min(current / target, 1.0)
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)

@client_food_router.message(F.text == "🍎 Мій раціон")
async def cmd_my_food(message: types.Message, session: AsyncSession, user_db: User):
    await render_food_dashboard(message, session, user_db.id)

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "main"))
async def cb_food_main(callback: types.CallbackQuery, session: AsyncSession, user_db: User, state: FSMContext):
    await state.clear()
    await render_food_dashboard(callback.message, session, user_db.id, edit=True)
    await callback.answer()

async def render_food_dashboard(message: types.Message, session: AsyncSession, client_id: int, edit: bool = False):
    today = datetime.date.today()
    plan = await nutrition_service.get_active_plan(session, client_id)
    progress = await food_service.calculate_progress(session, client_id, today)
    
    if not plan:
        text = "Тренер ще не призначив вам план харчування."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    text = f"🍎 <b>Мій раціон | {today.strftime('%d.%m.%Y')}</b>\n\n"
    
    categories_map = [
        ("protein", "🥩 Білок", plan.protein_portions),
        ("carbs", "🍚 Вуглеводи", plan.carbs_portions),
        ("fats", "🥜 Жири", plan.fats_portions),
        ("fruits", "🍎 Фрукти", plan.fruits_portions),
        ("anything", "🍩 Будь-що", plan.anything_portions),
    ]
    
    for cat_key, cat_name, target in categories_map:
        current = progress.get(cat_key, 0.0)
        bar = build_progress_bar(current, target)
        text += f"{cat_name}\n<code>{bar}</code> {current:g}/{target:g}\n\n"
        
    veg_current = progress.get("vegetable", 0.0)
    veg_target = plan.vegetables_g
    veg_bar = build_progress_bar(veg_current, veg_target)
    text += f"🥗 Овочі\n<code>{veg_bar}</code> {veg_current:g}/{veg_target} г\n"
    
    markup = client_food_main_kb()
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)

# ==========================================
# ДОДАВАННЯ ЇЖІ (ПОШУК ТА ПОРЦІЇ)
# ==========================================
@client_food_router.callback_query(ClientFoodCB.filter(F.action == "cat"))
async def cb_add_food_category(callback: types.CallbackQuery, callback_data: ClientFoodCB, state: FSMContext):
    cat = callback_data.category
    cat_name = FOOD_CATEGORIES.get(cat, cat)
    
    if cat == "anything":
        await state.set_state(ClientFoodFSM.waiting_for_anything_portions)
        await callback.message.edit_text("🍩 <b>Будь-що:</b>\nВведіть кількість порцій (наприклад: 1 або 0.5):", reply_markup=search_cancel_kb())
        return
        
    if cat == "vegetable":
        await state.set_state(ClientFoodFSM.waiting_for_anything_portions) # Перевикористаємо стейт, але для грамів
        await state.update_data(category=cat)
        await callback.message.edit_text("🥗 <b>Овочі:</b>\nВведіть з'їдену кількість у грамах:", reply_markup=search_cancel_kb())
        return
        
    await state.set_state(ClientFoodFSM.waiting_for_search)
    await state.update_data(category=cat)
    
    await callback.message.edit_text(
        f"{cat_name}\n🔍 Напишіть назву продукту в чат (наприклад, 'курка'):",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_search)
async def process_food_search(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    category = data["category"]
    query = message.text.strip()
    
    products = await food_service.search_products(session, category, query)
    
    if not products:
        await message.answer("❌ Продукт не знайдено. Спробуйте іншу назву:", reply_markup=search_cancel_kb())
        return
        
    await message.answer("👇 Оберіть продукт зі списку:", reply_markup=products_list_kb(products, category))

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "pick_prod"))
async def cb_pick_product(callback: types.CallbackQuery, callback_data: ClientFoodCB, state: FSMContext, session: AsyncSession):
    product_id = callback_data.product_id
    product = await session.get(FoodProduct, product_id)
    
    if not product:
        return await callback.answer("Продукт не знайдено", show_alert=True)
        
    await state.set_state(ClientFoodFSM.waiting_for_amount)
    await state.update_data(product_id=product.id, portion_size=product.portion_size, name=product.name, category=product.category)
    
    await callback.message.edit_text(
        f"Ви обрали: <b>{product.name}</b>\n⚖️ Введіть вагу в грамах (або шт):",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_amount)
async def process_food_amount(message: types.Message, state: FSMContext, session: AsyncSession, user_db: User):
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("Введіть коректне число.")
        
    data = await state.get_data()
    portions = amount / data["portion_size"]
    
    await food_service.add_food_entry(
        session, user_db.id, datetime.date.today(), 
        data["product_id"], data["category"], data["name"], amount, portions
    )
    
    await message.answer(f"✅ Записано: {data['name']} ({amount}г) = {portions:.1f} порц.")
    await state.clear()
    await render_food_dashboard(message, session, user_db.id)

@client_food_router.message(ClientFoodFSM.waiting_for_anything_portions)
async def process_anything_veg_amount(message: types.Message, state: FSMContext, session: AsyncSession, user_db: User):
    try:
        val = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("Введіть коректне число.")
        
    data = await state.get_data()
    category = data.get("category", "anything")
    
    if category == "anything":
        name = "Будь-що (доп. калорії)"
        amount = 1.0 # 1 запис
        portions = val
    else: # vegetable
        name = "Овочі"
        amount = val # грами
        portions = 0.0
        
    await food_service.add_food_entry(
        session, user_db.id, datetime.date.today(), 
        None, category, name, amount, portions
    )
    
    await message.answer("✅ Записано.")
    await state.clear()
    await render_food_dashboard(message, session, user_db.id)

# ==========================================
# ФОТО ЇЖІ
# ==========================================
@client_food_router.callback_query(ClientFoodCB.filter(F.action == "photo"))
async def cb_photo_food(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientFoodFSM.waiting_for_photo_desc)
    await callback.message.edit_text("📷 Надішліть фото вашого прийому їжі (можна додати текст в опис):", reply_markup=search_cancel_kb())
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_photo_desc, F.photo)
async def process_food_photo(message: types.Message, state: FSMContext, session: AsyncSession, user_db: User):
    file_id = message.photo[-1].file_id
    comment = message.caption or "Без опису"
    
    await food_service.add_food_photo(session, user_db.id, datetime.date.today(), file_id, comment)
    await message.answer("📸 Фото успішно збережено в щоденник!")
    await state.clear()
    await render_food_dashboard(message, session, user_db.id)