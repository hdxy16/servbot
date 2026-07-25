import logging
import datetime
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from bot.filters.role_filter import IsClient
from database.models import User, FoodProduct, FoodDay, FoodEntry, NutritionPlan
from bot.keyboards.food import (
    ClientFoodCB, 
    client_food_main_kb, 
    FOOD_CATEGORIES, 
    search_cancel_kb, 
    products_list_kb
)
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

async def render_food_dashboard(message: Message, session: AsyncSession, client_id: int, edit: bool = False):
    try:
        today = datetime.date.today()
        plan = await nutrition_service.get_active_plan(session, client_id)
        progress = await food_service.calculate_progress(session, client_id, today)
        
        if not plan:
            text = "🍎 <b>Мій раціон</b>\n\nТренер ще не призначив вам план харчування."
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
    except Exception as e:
        logger.error(f"Error rendering food dashboard: {e}")
        if edit:
            await message.edit_text("❌ Помилка завантаження даних.")
        else:
            await message.answer("❌ Помилка завантаження даних.")

@client_food_router.message(F.text == "🍎 Мій раціон")
async def cmd_my_food(message: Message, session: AsyncSession, user_db: User):
    await render_food_dashboard(message, session, user_db.id)

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "main"))
async def cb_food_main(callback: CallbackQuery, session: AsyncSession, user_db: User, state: FSMContext):
    await state.clear()
    await render_food_dashboard(callback.message, session, user_db.id, edit=True)
    await callback.answer()

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "cat"))
async def cb_add_food_category(callback: CallbackQuery, callback_data: ClientFoodCB, state: FSMContext, session: AsyncSession, user_db: User):
    cat = callback_data.category
    cat_name = FOOD_CATEGORIES.get(cat, cat)
    
    if cat == "anything":
        await state.set_state(ClientFoodFSM.waiting_for_anything_portions)
        await callback.message.edit_text(
            "🍩 <b>Будь-що (додаткові калорії/солодощі):</b>\nВведіть кількість порцій (наприклад: 1 або 0.5):",
            reply_markup=search_cancel_kb()
        )
        return await callback.answer()
        
    if cat == "vegetable":
        await state.set_state(ClientFoodFSM.waiting_for_anything_portions)
        await state.update_data(category=cat)
        await callback.message.edit_text(
            "🥗 <b>Овочі:</b>\nВведіть з'їдену кількість у грамах (наприклад, 200):",
            reply_markup=search_cancel_kb()
        )
        return await callback.answer()

    # Спочатку показуємо нещодавно використані продукти (історію)
    recent_products = await food_service.get_recent_products(session, user_db.id, cat, limit=6)
    
    if not recent_products:
        # Якщо історії немає, показуємо загальну базу
        products = await food_service.get_all_products_by_category(session, cat)
        if not products:
            await callback.message.edit_text(f"У категорії {cat_name} немає продуктів.", reply_markup=search_cancel_kb())
            return await callback.answer()
        await callback.message.edit_text(
            f"👇 Оберіть продукт з категорії <b>{cat_name}</b>:",
            reply_markup=products_list_kb(products, cat, show_search=True)
        )
    else:
        # Якщо історія є, показуємо її
        await callback.message.edit_text(
            f"🕒 <b>Останні додані продукти ({cat_name}):</b>\nОберіть зі списку або натисніть 'Пошук'.",
            reply_markup=products_list_kb(recent_products, cat, show_search=True)
        )
    await callback.answer()

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "search"))
async def cb_search_manual(callback: CallbackQuery, callback_data: ClientFoodCB, state: FSMContext, session: AsyncSession):
    cat = callback_data.category
    # Показати всю базу як запасний варіант
    products = await food_service.get_all_products_by_category(session, cat)
    await callback.message.edit_text(
        f"👇 Оберіть продукт зі списку або введіть назву в чат для пошуку:",
        reply_markup=products_list_kb(products, cat, show_search=False)
    )
    await state.set_state(ClientFoodFSM.waiting_for_search)
    await state.update_data(category=cat)
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_search)
async def process_food_search(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    category = data["category"]
    query = message.text.strip()
    
    products = await food_service.search_products(session, category, query)
    
    if not products:
        await message.answer("❌ Продукт не знайдено. Спробуйте іншу назву:", reply_markup=search_cancel_kb())
        return
        
    await message.answer("👇 Оберіть продукт зі списку знайденого:", reply_markup=products_list_kb(products, category, show_search=False))

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "pick_prod"))
async def cb_pick_product(callback: CallbackQuery, callback_data: ClientFoodCB, state: FSMContext, session: AsyncSession):
    product_id = callback_data.product_id
    product = await session.get(FoodProduct, product_id)
    
    if not product:
        return await callback.answer("Продукт не знайдено", show_alert=True)
    
    await state.set_state(ClientFoodFSM.waiting_for_amount)
    await state.update_data(
        product_id=product.id,
        portion_size=product.portion_size,
        name=product.name,
        category=product.category,
        unit=product.unit
    )
    
    await callback.message.edit_text(
        f"Ви обрали: <b>{product.name}</b>\n⚖️ Введіть вагу в <b>{product.unit}</b>:",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_amount)
async def process_food_amount(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("Введіть коректне число.")
    
    data = await state.get_data()
    portions = amount / data["portion_size"]
    
    try:
        await food_service.add_food_entry(
            session, user_db.id, datetime.date.today(), 
            data["product_id"], data["category"], data["name"], amount, portions
        )
        
        await message.answer(f"✅ Записано: {data['name']} ({amount:g}{data.get('unit', 'г')}) = {portions:.1f} порц.")
        await state.clear()
        await render_food_dashboard(message, session, user_db.id)
    except Exception as e:
        logger.error(f"Error adding food entry: {e}")
        await message.answer("❌ Помилка збереження.")

@client_food_router.message(ClientFoodFSM.waiting_for_anything_portions)
async def process_anything_veg_amount(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    try:
        val = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("Введіть коректне число.")
    
    data = await state.get_data()
    category = data.get("category", "anything")
    
    try:
        if category == "anything":
            name = "Будь-що (доп. калорії)"
            amount = 1.0
            portions = val
        else:
            name = "Овочі"
            amount = val
            portions = 0.0
        
        await food_service.add_food_entry(
            session, user_db.id, datetime.date.today(), 
            None, category, name, amount, portions
        )
        
        await message.answer("✅ Записано.")
        await state.clear()
        await render_food_dashboard(message, session, user_db.id)
    except Exception as e:
        logger.error(f"Error adding entry: {e}")
        await message.answer("❌ Помилка збереження.")

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "diary"))
async def cb_diary(callback: CallbackQuery, session: AsyncSession, user_db: User):
    today = datetime.date.today()
    entries = await food_service.get_day_entries(session, user_db.id, today)
    
    if not entries:
        await callback.message.edit_text(
            f"📖 <b>Щоденник за {today.strftime('%d.%m.%Y')}</b>\n\nВи ще нічого не записали.",
            reply_markup=client_food_main_kb()
        )
        await callback.answer()
        return
    
    text = f"📖 <b>Щоденник за {today.strftime('%d.%m.%Y')}</b>\n\n"
    for e in entries:
        time_str = e.created_at.strftime("%H:%M")
        if e.category == "vegetable":
            text += f"▫️ {time_str} | {e.product_name} ({e.amount:g} г)\n"
        elif e.category == "anything":
            text += f"▫️ {time_str} | {e.product_name} ({e.portions:g} порц.)\n"
        else:
            text += f"▫️ {time_str} | {e.product_name} ({e.amount:g} г = {e.portions:.1f} порц.)\n"
    
    await callback.message.edit_text(text, reply_markup=client_food_main_kb())
    await callback.answer()

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "close_day"))
async def cb_close_day(callback: CallbackQuery, session: AsyncSession, user_db: User):
    today = datetime.date.today()
    food_day = await food_service.get_or_create_food_day(session, user_db.id, today)
    
    food_day.is_closed = True
    await session.commit()
    await callback.message.edit_text(
        f"🔒 День {today.strftime('%d.%m.%Y')} закрито. Ваш тренер отримає фінальний звіт.",
        reply_markup=client_food_main_kb()
    )
    await callback.answer()

@client_food_router.callback_query(ClientFoodCB.filter(F.action == "photo"))
async def cb_photo_food(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClientFoodFSM.waiting_for_photo_desc)
    await callback.message.edit_text(
        "📷 Надішліть фото вашого прийому їжі (можна додати текст в опис):",
        reply_markup=search_cancel_kb()
    )
    await callback.answer()

@client_food_router.message(ClientFoodFSM.waiting_for_photo_desc, F.photo)
async def process_food_photo(message: Message, state: FSMContext, session: AsyncSession, user_db: User):
    file_id = message.photo[-1].file_id
    comment = message.caption or "Без опису"
    
    try:
        await food_service.add_food_photo(session, user_db.id, datetime.date.today(), file_id, comment)
        await message.answer("📸 Фото успішно збережено в щоденник!")
        await state.clear()
        await render_food_dashboard(message, session, user_db.id)
    except Exception as e:
        logger.error(f"Error saving food photo: {e}")
        await message.answer("❌ Помилка збереження фото.")