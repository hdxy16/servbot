import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import TrainerClientCB
from bot.keyboards.food import TrainerNutrCB, trainer_nutrition_kb, edit_nutrition_kb
from bot.services import nutrition_service, food_service, audit_service

logger = logging.getLogger(__name__)
trainer_food_router = Router()
trainer_food_router.message.filter(IsTrainer())
trainer_food_router.callback_query.filter(IsTrainer())

from bot.states.food_fsm import TrainerNutritionFSM

@trainer_food_router.callback_query(TrainerClientCB.filter(F.action == "food"))
async def cb_client_food_card(callback: types.CallbackQuery, callback_data: TrainerClientCB, session: AsyncSession):
    client_id = callback_data.client_id
    plan = await nutrition_service.get_active_plan(session, client_id)
    
    if not plan:
        text = "🍎 <b>Харчування клієнта</b>\n\nПлан харчування ще не налаштовано."
    else:
        text = (
            f"🍎 <b>Поточний план харчування</b>\n\n"
            f"🥩 Білок: <b>{plan.protein_portions} порцій</b>\n"
            f"🍚 Вуглеводи: <b>{plan.carbs_portions} порцій</b>\n"
            f"🥜 Жири: <b>{plan.fats_portions} порцій</b>\n"
            f"🍎 Фрукти: <b>{plan.fruits_portions} порцій</b>\n"
            f"🍩 Будь-що: <b>{plan.anything_portions} порцій</b>\n"
            f"🥗 Овочі: <b>{plan.vegetables_g} г</b>\n\n"
            f"<i>План діє з {plan.created_at.strftime('%d.%m.%Y')}</i>"
        )
        
    await callback.message.edit_text(text, reply_markup=trainer_nutrition_kb(client_id))
    await callback.answer()

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "edit_menu"))
async def cb_edit_nutr_menu(callback: types.CallbackQuery, callback_data: TrainerNutrCB, state: FSMContext, session: AsyncSession):
    client_id = callback_data.client_id
    plan = await nutrition_service.get_active_plan(session, client_id)
    
    # Створюємо чернетку в FSM
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
        f"🥩 Білок: {draft['protein']}\n"
        f"🍚 Вуглеводи: {draft['carbs']}\n"
        f"🥜 Жири: {draft['fats']}\n"
        f"🍎 Фрукти: {draft['fruits']}\n"
        f"🍩 Будь-що: {draft['anything']}\n"
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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[])
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
        # У реальному боті краще видаляти повідомлення юзера і редагувати старе, 
        # але для стабільності надішлемо нове.
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

@trainer_food_router.callback_query(TrainerNutrCB.filter(F.action == "diary"))
async def cb_diary(callback: types.CallbackQuery, callback_data: TrainerNutrCB, session: AsyncSession):
    client_id = callback_data.client_id
    today = datetime.date.today()
    entries = await food_service.get_day_entries(session, client_id, today)
    
    if not entries:
        await callback.message.edit_text(
            f"📖 <b>Щоденник за {today.strftime('%d.%m.%Y')}</b>\n\nКлієнт ще нічого не записав.",
            reply_markup=trainer_nutrition_kb(client_id)
        )
        return
        
    text = f"📖 <b>Щоденник за {today.strftime('%d.%m.%Y')}</b>\n\n"
    for e in entries:
        time_str = e.created_at.strftime("%H:%M")
        if e.category == "vegetable":
            text += f"▫️ {time_str} | {e.product_name} ({e.amount} г)\n"
        else:
            text += f"▫️ {time_str} | {e.product_name} ({e.portions:.1f} порц.)\n"
            
    await callback.message.edit_text(text, reply_markup=trainer_nutrition_kb(client_id))
    await callback.answer()