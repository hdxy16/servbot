import logging
import datetime
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import TrainerClientCB
from bot.keyboards.food import (
    TrainerNutrCB, 
    trainer_nutrition_kb, 
    edit_nutrition_kb, 
    trainer_global_food_kb,
    TrainerProdCB,
    trainer_product_cats_kb
)
from bot.services import nutrition_service, food_service, audit_service
from bot.states.food_fsm import TrainerNutritionFSM, TrainerAddProductFSM

logger = logging.getLogger(__name__)
trainer_food_router = Router()
trainer_food_router.message.filter(IsTrainer())
trainer_food_router.callback_query.filter(IsTrainer())

# ==========================================
# ГЛОБАЛЬНА БАЗА ПРОДУКТІВ
# ==========================================
@trainer_food_router.message(F.text == "🍎 Харчування")
async def cmd_global_food(message: types.Message):
    await message.answer(
        "🍎 <b>Система Харчування</b>\nТут ви можете керувати базою продуктів для всіх клієнтів.", 
        reply_markup=trainer_global_food_kb()
    )

@trainer_food_router.callback_query(TrainerProdCB.filter(F.action == "menu"))
async def cb_global_food_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Оберіть категорію, до якої хочете додати новий продукт:", reply_markup=trainer_product_cats_kb())
    await callback.answer()

@trainer_food_router.callback_query(TrainerProdCB.filter(F.action == "add_to"))
async def cb_add_product_to_cat(callback: types.CallbackQuery, callback_data: TrainerProdCB, state: FSMContext):
    await state.set_state(TrainerAddProductFSM.waiting_for_name)
    await state.update_data(category=callback_data.category)
    await callback.message.edit_text("Напишіть назву нового продукту:")
    await callback.answer()

@trainer_food_router.message(TrainerAddProductFSM.waiting_for_name)
async def process_prod_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(TrainerAddProductFSM.waiting_for_size)
    await message.answer("Скільки грамів чи штук міститься в 1 порції?\nНапишіть число:")

@trainer_food_router.message(TrainerAddProductFSM.waiting_for_size)
async def process_prod_size(message: types.Message, state: FSMContext):
    try:
        size = float(message.text.strip().replace(",", "."))
        await state.update_data(size=size)
        await state.set_state(TrainerAddProductFSM.waiting_for_unit)
        await message.answer("Яка одиниця виміру? Напишіть 'г', 'мл' або 'шт':")
    except ValueError:
        await message.answer("❌ Будь ласка, введіть коректне число.")

@trainer_food_router.message(TrainerAddProductFSM.waiting_for_unit)
async def process_prod_unit(message: types.Message, state: FSMContext, session: AsyncSession, user_db: User):
    unit = message.text.strip().lower()
    data = await state.get_data()
    
    product = await food_service.add_custom_product(session, data["category"], data["name"], data["size"], unit)
    await audit_service.log_action(session, user_db.id, None, "added_custom_food_product", {"name": product.name})
    
    await message.answer(f"✅ Продукт <b>{product.name} ({product.portion_size:g} {product.unit})</b> успішно додано в загальну базу!", reply_markup=trainer_global_food_kb())
    await state.clear()

# ==========================================
# ІНДИВІДУАЛЬНЕ ХАРЧУВАННЯ КЛІЄНТА
# ==========================================
@trainer_food_router.callback_query(TrainerClientCB.filter(F.action == "food"))
async def cb_client_food_card(callback: types.CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
    client_id = callback_data.client_id
    plan = await nutrition_service.get_active_plan(session, client_id)
    
    if not plan:
        text = "🍎 <b>Харчування клієнта</b>\n\nПлан харчування ще не налаштовано."
    else:
        text = (
            f"🍎 <b>Поточний план харчування</b>\n\n"
            f"🥩 Білок: <b>{plan.protein_portions:g} порцій</b>\n"
            f"🍚 Вуглеводи: <b>{plan.carbs_portions:g} порцій</b>\n"
            f"🥜 Жири: <b>{plan.fats_portions:g} порцій</b>\n"
            f"🍎 Фрукти: <b>{plan.fruits_portions:g} порцій</b>\n"
            f"🍩 Будь-що: <b>{plan.anything_portions:g} порцій</b>\n"
            f"🥗 Овочі: <b>{plan.vegetables_g} г</b>\n\n"
            f"<i>План діє з {plan.created_at.strftime('%d.%m.%Y')}</i>"
        )
        
    await callback.message.edit_text(text, reply_markup=trainer_nutrition_kb(client_id))
    await callback.answer()

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "edit_menu"))
async def cb_edit_nutr_menu(callback: types.CallbackQuery, callback_data: TrainerNutrCB, state: FSMContext, session: AsyncSession):
    client_id = callback_data.client_id
    plan = await nutrition_service.get_active_plan(session, client_id)
    
    draft = {
        "protein": plan.protein_portions if plan else 0.0,
        "carbs": plan.carbs_portions if plan else 0.0,
        "fats": plan.fats_portions if plan else 0.0,
        "fruits": plan.fruits_portions if plan else 0.0,
        "anything": plan.anything_portions if plan else 0.0,
        "vegetables_g": plan.vegetables_g if plan else 400
    }
    await state.update_data(draft=draft, client_id=client_id)
    
    await render_draft(callback.message, client_id, draft)
    await callback.answer()

async def render_draft(message: types.Message, client_id: int, draft: dict):
    text = (
        f"✏️ <b>Редагування плану харчування:</b>\n\n"
        f"🥩 Білок: {draft['protein']:g}\n"
        f"🍚 Вуглеводи: {draft['carbs']:g}\n"
        f"🥜 Жири: {draft['fats']:g}\n"
        f"🍎 Фрукти: {draft['fruits']:g}\n"
        f"🍩 Будь-що: {draft['anything']:g}\n"
        f"🥗 Овочі: {draft['vegetables_g']} г\n\n"
        f"<i>Оберіть макронутрієнт для зміни, потім натисніть 'Зберегти план'.</i>"
    )
    await message.edit_text(text, reply_markup=edit_nutrition_kb(client_id))

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "edit_val"))
async def cb_edit_nutr_val(callback: types.CallbackQuery, callback_data: TrainerNutrCB, state: FSMContext):
    await state.set_state(TrainerNutritionFSM.waiting_for_value)
    await state.update_data(field=callback_data.field)
    await callback.message.edit_text(
        f"Введіть нове значення для <b>{callback_data.field}</b> (число):",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[])
    )
    await callback.answer()

@trainer_food_router.message(TrainerNutritionFSM.waiting_for_value)
async def process_nutr_val(message: types.Message, state: FSMContext):
    val_str = message.text.strip().replace(",", ".")
    try:
        val = float(val_str) if "." in val_str else int(val_str)
        data = await state.get_data()
        field = data["field"]
        draft = data["draft"]
        draft[field] = val
        
        await state.update_data(draft=draft)
        await state.set_state(None)
        
        await message.answer("Значення оновлено. Повертаємось до чернетки...")
        await render_draft(message, data["client_id"], draft)
    except ValueError:
        await message.answer("❌ Введіть коректне число.")

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "save_plan"))
async def cb_save_nutr_plan(callback: types.CallbackQuery, callback_data: TrainerNutrCB, state: FSMContext, session: AsyncSession, user_db: User):
    data = await state.get_data()
    draft = data.get("draft")
    client_id = callback_data.client_id
    
    if not draft:
        return await callback.answer("Помилка чернетки.", show_alert=True)
        
    new_plan = await nutrition_service.create_plan(
        session, client_id, user_db.id,
        draft["protein"], draft["carbs"], draft["fats"], 
        draft["fruits"], draft["anything"], int(draft["vegetables_g"])
    )
    
    await audit_service.log_action(session, user_db.id, client_id, "updated_nutrition_plan", details=draft)
    await state.clear()
    
    await callback.message.edit_text("✅ Новий план харчування успішно застосовано!", reply_markup=trainer_nutrition_kb(client_id))
    await callback.answer()

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "cancel"))
async def cb_cancel_nutr_edit(callback: types.CallbackQuery, callback_data: TrainerNutrCB, state: FSMContext, session: AsyncSession):
    await state.clear()
    await cb_client_food_card(callback, TrainerClientCB(action="food", client_id=callback_data.client_id), session)

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "diary"))
async def cb_diary(callback: types.CallbackQuery, callback_data: TrainerNutrCB, session: AsyncSession):
    client_id = callback_data.client_id
    today = datetime.date.today()
    entries = await food_service.get_day_entries(session, client_id, today)
    
    if not entries:
        await callback.message.edit_text(
            f"📖 <b>Щоденник клієнта за {today.strftime('%d.%m.%Y')}</b>\n\nКлієнт ще нічого не записав.",
            reply_markup=trainer_nutrition_kb(client_id)
        )
        return
        
    text = f"📖 <b>Щоденник клієнта за {today.strftime('%d.%m.%Y')}</b>\n\n"
    for e in entries:
        time_str = e.created_at.strftime("%H:%M")
        if e.category == "vegetable":
            text += f"▫️ {time_str} | {e.product_name} ({e.amount:g} г)\n"
        elif e.category == "anything":
            text += f"▫️ {time_str} | {e.product_name} ({e.portions:g} порц.)\n"
        else:
            text += f"▫️ {time_str} | {e.product_name} ({e.amount:g} г = {e.portions:.1f} порц.)\n"
            
    await callback.message.edit_text(text, reply_markup=trainer_nutrition_kb(client_id))
    await callback.answer()