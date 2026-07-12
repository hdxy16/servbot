# Gym_Bot/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def trainer_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Мої клієнти"), KeyboardButton(text="➕ Створити інвайт")],
        [KeyboardButton(text="⚙️ Керувати каталогом"), KeyboardButton(text="🕒 Налаштувати звіт")],
        [KeyboardButton(text="🧪 Тест клієнта")]
    ], resize_keyboard=True, is_persistent=True)

def client_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [[KeyboardButton(text="🍏 Мій раціон")]]
    if is_admin:
        buttons.append([KeyboardButton(text="🧠 В адмінку")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, is_persistent=True)

def client_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🥩 Білки", callback_data="client_cat_protein")
    builder.button(text="🍚 Вуглеводи", callback_data="client_cat_carbs")
    builder.button(text="🥜 Жири", callback_data="client_cat_fats")
    builder.button(text="🍎 Фрукти", callback_data="client_cat_fruits")
    builder.button(text="🥗 Овочі (внести в г)", callback_data="client_add_veggies")
    builder.button(text="🔍 Щоденник прийомів", callback_data="client_view_logs")
    builder.button(text="⚖️ Внести вагу", callback_data="client_weight_log") # ІДЕЯ 3
    builder.button(text="🔒 Закрити день", callback_data="client_close_day") # ІДЕЯ 4
    builder.button(text="🧹 Очистити весь день", callback_data="client_clear_day")
    builder.adjust(2, 2, 1, 2, 1)
    return builder.as_markup()

def client_products_keyboard(products_list: list, category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products_list:
        builder.button(text=f"{p.name} ({int(p.size)}{p.unit})", callback_data=f"cl_dbprod_{p.id}")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(2)
    return builder.as_markup()

def trainer_clients_keyboard(clients: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in clients:
        name = c.full_name if c.full_name else f"ID: {c.telegram_id}"
        builder.button(text=f"👤 {name}", callback_data=f"tr_view_{c.id}")
    builder.adjust(1)
    return builder.as_markup()

def trainer_client_manage_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика за сьогодні", callback_data=f"tr_stats_{client_id}")
    builder.button(text="⚙️ Редагувати норми БЖВ", callback_data=f"tr_edit_{client_id}")
    builder.button(text="❌ Видалити клієнта", callback_data=f"tr_del_{client_id}")
    builder.button(text="🔙 До списку", callback_data="tr_list_back")
    builder.adjust(1)
    return builder.as_markup()

def trainer_catalog_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🥩 Редагувати Білки", callback_data="tr_catmanage_protein")
    builder.button(text="🍚 Редагувати Вуглеводи", callback_data="tr_catmanage_carbs")
    builder.button(text="🥜 Редагувати Жири", callback_data="tr_catmanage_fats")
    builder.button(text="🍎 Редагувати Фрукти", callback_data="tr_catmanage_fruits")
    builder.adjust(1)
    return builder.as_markup()

def trainer_products_management_keyboard(products_list: list, category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products_list:
        builder.button(text=f"⚙️ {p.name}", callback_data=f"tr_propt_{p.id}")
    builder.button(text="➕ Додати новий продукт", callback_data=f"tr_addprod_{category}")
    builder.button(text="🔙 До категорій", callback_data="tr_catmanage_back")
    builder.adjust(1)
    return builder.as_markup()

def trainer_product_actions_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚖️ Змінити вагу порції", callback_data=f"tr_paction_edit_{product_id}")
    builder.button(text="❌ Видалити продукт з бази", callback_data=f"tr_paction_del_{product_id}")
    builder.button(text="🔙 Назад до списку", callback_data="tr_paction_cancel")
    builder.adjust(1)
    return builder.as_markup()

# КЛАВІАТУРА НАЛАШТУВАННЯ ЧАСУ ЗВІТІВ (ІДЕЯ 2)
def trainer_report_time_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    times = ["19:00", "20:00", "21:00", "22:00", "23:00"]
    for t in times:
        builder.button(text=t, callback_data=f"tr_settime_{t}")
    builder.button(text="✏️ Ввести інший час вручну", callback_data="tr_settime_manual")
    builder.adjust(3, 2, 1)
    return builder.as_markup()