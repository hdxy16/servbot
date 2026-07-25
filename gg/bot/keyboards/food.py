from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

class TrainerNutrCB(CallbackData, prefix="tr_nutr"):
    action: str
    client_id: int = 0
    field: str = ""

class TrainerProdCB(CallbackData, prefix="tr_prod"):
    action: str
    category: str = ""

class ClientFoodCB(CallbackData, prefix="cl_food"):
    action: str
    category: str = ""
    product_id: int = 0

FOOD_CATEGORIES = {
    "protein": "🥩 Білок",
    "carbs": "🍚 Вуглеводи",
    "fats": "🥜 Жири",
    "fruits": "🍎 Фрукти",
    "anything": "🍩 Будь-що",
    "vegetable": "🥗 Овочі"
}

def trainer_global_food_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 База продуктів", callback_data=TrainerProdCB(action="menu").pack())
    # Можна додати шаблони в майбутньому
    return builder.as_markup()

def trainer_product_cats_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat_key, cat_name in FOOD_CATEGORIES.items():
        if cat_key in ["anything", "vegetable"]:
            continue # Для цих категорій тренер не додає продукти
        builder.button(text=cat_name, callback_data=TrainerProdCB(action="add_to", category=cat_key).pack())
    builder.adjust(2)
    builder.row(InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="cancel_fsm").buttons[0])
    return builder.as_markup()

def trainer_nutrition_kb(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Змінити порції", callback_data=TrainerNutrCB(action="edit_menu", client_id=client_id).pack())
    builder.button(text="📂 Завантажити шаблон", callback_data=TrainerNutrCB(action="templates", client_id=client_id).pack())
    builder.button(text="📖 Щоденник клієнта", callback_data=TrainerNutrCB(action="diary", client_id=client_id).pack())
    builder.button(text="📊 Статистика", callback_data=TrainerNutrCB(action="stats", client_id=client_id).pack())
    builder.button(text="🔙 Назад до клієнта", callback_data=f"tr_cl:card:{client_id}:1:") 
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup()

def edit_nutrition_kb(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = [
        ("protein", "🥩 Білок"), ("carbs", "🍚 Вуглеводи"),
        ("fats", "🥜 Жири"), ("fruits", "🍎 Фрукти"),
        ("anything", "🍩 Будь-що"), ("vegetables_g", "🥗 Овочі (г)")
    ]
    for f_key, f_name in fields:
        builder.button(text=f_name, callback_data=TrainerNutrCB(action="edit_val", client_id=client_id, field=f_key).pack())
        
    builder.button(text="💾 Зберегти план", callback_data=TrainerNutrCB(action="save_plan", client_id=client_id).pack())
    builder.button(text="❌ Скасувати", callback_data=TrainerNutrCB(action="cancel", client_id=client_id).pack())
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()

def client_food_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🥩 Додати білок", callback_data=ClientFoodCB(action="cat", category="protein").pack())
    builder.button(text="🍚 Додати вуглеводи", callback_data=ClientFoodCB(action="cat", category="carbs").pack())
    builder.button(text="🥜 Додати жири", callback_data=ClientFoodCB(action="cat", category="fats").pack())
    builder.button(text="🍎 Додати фрукти", callback_data=ClientFoodCB(action="cat", category="fruits").pack())
    builder.button(text="🍩 Додати 'Будь-що'", callback_data=ClientFoodCB(action="cat", category="anything").pack())
    builder.button(text="🥗 Додати овочі", callback_data=ClientFoodCB(action="cat", category="vegetable").pack())
    
    builder.button(text="📷 Фото їжі", callback_data=ClientFoodCB(action="photo").pack())
    builder.button(text="📖 Щоденник", callback_data=ClientFoodCB(action="diary").pack())
    builder.button(text="🔒 Закрити день", callback_data=ClientFoodCB(action="close_day").pack())
    
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()

def search_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Скасувати", callback_data=ClientFoodCB(action="main").pack())
    return builder.as_markup()

def products_list_kb(products: list, category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for prod in products:
        unit_text = f"({prod.portion_size} {prod.unit})"
        builder.button(
            text=f"{prod.name} {unit_text}", 
            callback_data=ClientFoodCB(action="pick_prod", category=category, product_id=prod.id).pack()
        )
    # Кнопка для ручного пошуку, якщо список завеликий і юзер не знайшов своє
    builder.button(text="🔍 Ввести назву вручну", callback_data=ClientFoodCB(action="search", category=category).pack())
    builder.button(text="🔙 Скасувати", callback_data=ClientFoodCB(action="main").pack())
    builder.adjust(1)
    return builder.as_markup()