from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import CATEGORY_TITLES

PRODUCT_EMOJI = {
    "куряче": "🐔", "стегно": "🍗", "філе": "🥩", "індичка": "🦃",
    "телятина": "🥩", "свинина": "🥩", "печінка": "🍖", "яловича": "🥩",
    "хек": "🐟", "мінтай": "🐟", "тріска": "🐟", "судак": "🐟", "пікша": "🐟",
    "окунь": "🐟", "щука": "🐟", "тілапія": "🐟", "тунець": "🐟", "лосось": "🐟",
    "форель": "🐟", "скумбрія": "🐟", "оселедець": "🐟", "сардина": "🐟",
    "креветки": "🦐", "мідії": "🦪", "восьминіг": "🐙", "яйця": "🥚",
    "сир": "🧀", "йогурт": "🥛", "кефір": "🥛", "молоко": "🥛",
    "рис": "🍚", "гречка": "🌾", "булгур": "🌾", "кус-кус": "🌾",
    "перловка": "🌾", "ячна": "🌾", "пшоняна": "🌾", "вівсяні": "🌾",
    "кукурудзяна": "🌽", "манка": "🌾", "кіноа": "🌾", "макарони": "🍝",
    "локшина": "🍜", "лаваш": "🥙", "хліб": "🍞", "хлібці": "🍞",
    "картопля": "🥔", "батат": "🍠", "кукурудза": "🌽", "квасоля": "🫘",
    "нут": "🫘", "горох": "🫘", "сочевиця": "🫘",
    "олія": "🫒", "авокадо": "🥑", "маслини": "🫒", "оливки": "🫒",
    "майонез": "🥫", "кетчуп": "🥫", "горіхи": "🥜", "арахісова": "🥜",
    "тахіні": "🥜", "фрукти": "🍎", "банан": "🍌", "манго": "🥭",
    "хурма": "🍅", "виноград": "🍇", "фініки": "🌴", "ягоди": "🫐",
    "овочі": "🥬", "будь-що": "🍩",
}

def get_product_emoji(name: str) -> str:
    name_lower = name.lower()
    for key, emoji in PRODUCT_EMOJI.items():
        if key in name_lower:
            return emoji
    return "🍽️"

def trainer_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Мої клієнти"), KeyboardButton(text="➕ Створити інвайт")],
        [KeyboardButton(text="⚙️ Керувати меню"), KeyboardButton(text="⚙️ Редагувати інструкцію")],
        [KeyboardButton(text="📊 Звіти"), KeyboardButton(text="🛠 Технічні роботи")],
        [KeyboardButton(text="✅ Бот відновлено"), KeyboardButton(text="🧪 Тест клієнта")],
    ], resize_keyboard=True, is_persistent=True)

def client_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🍏 Мій раціон"), KeyboardButton(text="📖 Інструкція")],
        [KeyboardButton(text="📅 Історія"), KeyboardButton(text="⚖️ Моя вага")],
        [KeyboardButton(text="🏋️ Спортзал")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="🧠 В адмінку")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, is_persistent=True)

def client_categories_keyboard(is_closed: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    if not is_closed:
        for cat_key, title in CATEGORY_TITLES.items():
            builder.button(text=title, callback_data=f"client_cat_{cat_key}")
        builder.button(text="📦 Мої страви", callback_data="cl_meals_home")
        builder.button(text="🔄 Заміни", callback_data="cl_swap_home")
            
    builder.button(text="🔍 Журнал за сьогодні", callback_data="client_view_logs")
    
    if not is_closed:
        builder.button(text="🔒 Закрити день (Звіт)", callback_data="client_close_day")
        builder.adjust(2, 2, 2, 2, 1, 1)
    else:
        builder.button(text="🔓 Відкрити день", callback_data="client_open_day")
        builder.adjust(1)
        
    return builder.as_markup()

def client_subcategories_keyboard(category: str, subcategories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subcategories:
        if sub: 
            # Використовуємо безпечний хеш-префікс
            builder.button(text=sub, callback_data=f"cl_sc_{category}_{sub}")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(1)
    return builder.as_markup()

def client_products_keyboard_paginated(products_list: list, category: str, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_products = products_list[start:end]
    
    for p in page_products:
        emoji = get_product_emoji(p.name)
        try: size_str = f"{float(p.size):g}"
        except: size_str = str(p.size)
        builder.button(text=f"{emoji} {p.name} ({size_str}{p.unit})", callback_data=f"cl_dbprod_{p.id}")
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cl_pp_{category}_{page-1}"))
    if end < len(products_list):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"cl_pp_{category}_{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)
    
    if category == "other":
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="client_cat_other"))
    else:
        builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"client_cat_{category}"))
        
    builder.adjust(1)
    return builder.as_markup()

def client_products_keyboard_paginated_for_subcat(products_list: list, category: str, subcategory: str, page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_products = products_list[start:end]
    
    for p in page_products:
        emoji = get_product_emoji(p.name)
        try: size_str = f"{float(p.size):g}"
        except: size_str = str(p.size)
        builder.button(text=f"{emoji} {p.name} ({size_str}{p.unit})", callback_data=f"cl_dbprod_{p.id}")
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cl_ps_{category}_{subcategory}_{page-1}"))
    if end < len(products_list):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"cl_ps_{category}_{subcategory}_{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="🔙 До підкатегорій", callback_data=f"client_cat_{category}"))
    builder.adjust(1)
    return builder.as_markup()

def close_day_yes_no_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, було", callback_data="cd_workout_yes")
    builder.button(text="❌ Ні, відпочинок", callback_data="cd_workout_no")
    builder.adjust(2)
    return builder.as_markup()

def close_day_scale_keyboard(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text=str(i), callback_data=f"cd_{prefix}_{i}")
    builder.adjust(5)
    return builder.as_markup()

def close_day_skip_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏩ Пропустити коментар", callback_data="cd_skip_comment")
    return builder.as_markup()

def client_close_day_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Все вірно, надіслати тренеру", callback_data="cl_confirm_close_day")
    builder.button(text="🔄 Оновити кроки/самопочуття", callback_data="cl_restart_close_fsm")
    builder.button(text="❌ Скасувати", callback_data="client_food_home")
    builder.adjust(1)
    return builder.as_markup()

def trainer_report_reply_keyboard(client_id: int, date_str: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Написати коментар клієнту", callback_data=f"tr_reply_{client_id}_{date_str}")
    builder.adjust(1)
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
    builder.button(text="📈 Тренди за тиждень", callback_data=f"tr_trends_{client_id}")
    builder.button(text="⚙️ Редагувати норми", callback_data=f"tr_edit_{client_id}")
    builder.button(text="📖 Інструкція клієнта", callback_data=f"tr_inst_{client_id}")
    builder.button(text="📝 Нотатки", callback_data=f"tr_notes_{client_id}")
    builder.button(text="🏋️ Керування тренуваннями", callback_data=f"tr_gym_manage_{client_id}")
    builder.button(text="❌ Видалити клієнта", callback_data=f"tr_del_confirm_{client_id}")
    builder.button(text="🔙 До списку", callback_data="tr_list_back")
    builder.adjust(1)
    return builder.as_markup()

def confirm_delete_client_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Так, видалити", callback_data=f"tr_del_{client_id}")
    builder.button(text="❌ Скасувати", callback_data=f"tr_view_{client_id}")
    builder.adjust(1)
    return builder.as_markup()

def trainer_catalog_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat_key, title in CATEGORY_TITLES.items():
        if cat_key == "veggies": continue
        builder.button(text=f"✏️ {title}", callback_data=f"tr_catmanage_{cat_key}")
    builder.adjust(2)
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
    builder.button(text="❌ Видалити продукт", callback_data=f"tr_paction_del_{product_id}")
    builder.button(text="🔙 Назад до списку", callback_data="tr_paction_cancel")
    builder.adjust(1)
    return builder.as_markup()

def history_navigation_keyboard(current_date: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Вчора", callback_data="hist_prev")
    builder.button(text="📅 Сьогодні", callback_data="hist_today")
    builder.button(text="Завтра ➡️", callback_data="hist_next")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(3, 1)
    return builder.as_markup()

def weight_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати вагу", callback_data="weight_add")
    builder.button(text="📋 Всі записи", callback_data="weight_list")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(1)
    return builder.as_markup()

def gym_plans_keyboard(plans: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        if plan["done_today"]:
            color = "danger"
            status = "🔴"
        else:
            color = "primary"
            status = "🔵"
        builder.button(text=f"{status} {plan['name']}", callback_data=f"gym_plan_{plan['id']}")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(1)
    return builder.as_markup()

def gym_workout_keyboard(pe_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏋️ Почати підхід 1", callback_data=f"gym_set_{pe_id}_1")
    builder.button(text="⏩ Пропустити вправу", callback_data="gym_skip_exercise")
    builder.button(text="🔚 Завершити тренування", callback_data="gym_finish_workout")
    builder.adjust(1)
    return builder.as_markup()

def gym_set_input_keyboard(suggested_weight: float = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if suggested_weight:
        builder.button(text=f"⚖️ {suggested_weight} кг", callback_data=f"gym_weight_{suggested_weight}")
        builder.button(text=f"+2.5", callback_data=f"gym_weight_{suggested_weight+2.5}")
        builder.button(text=f"-2.5", callback_data=f"gym_weight_{suggested_weight-2.5}")
    else:
        builder.button(text="50 кг", callback_data="gym_weight_50")
        builder.button(text="60 кг", callback_data="gym_weight_60")
        builder.button(text="70 кг", callback_data="gym_weight_70")
    builder.button(text="✏️ Ввести вручну", callback_data="gym_weight_manual")
    builder.adjust(2)
    return builder.as_markup()

def gym_confirm_finish_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, завершити", callback_data="gym_confirm_finish")
    builder.button(text="❌ Продовжити", callback_data="gym_continue")
    builder.adjust(1)
    return builder.as_markup()

def trainer_gym_manage_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список планів", callback_data=f"tr_gym_plans_{client_id}")
    builder.button(text="➕ Створити новий план", callback_data=f"tr_gym_create_plan_{client_id}")
    builder.button(text="🏋️ Каталог вправ", callback_data=f"tr_gym_exercises_{client_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_view_{client_id}")
    builder.adjust(1)
    return builder.as_markup()

def gym_exercise_catalog_keyboard(exercises: list, plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ex in exercises[:20]:
        builder.button(text=f"{ex.emoji or '🏋️'} {ex.name}", callback_data=f"tr_gym_select_exercise_{plan_id}_{ex.id}")
    builder.button(text="➕ Створити нову вправу", callback_data=f"tr_gym_create_exercise_{plan_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_add_exercise_{plan_id}")
    builder.adjust(1)
    return builder.as_markup()

# Додати в кінець файлу

def gym_templates_keyboard(templates: list, client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.button(text=f"📋 {t.name}", callback_data=f"tr_gym_assign_template_{client_id}_{t.id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    builder.adjust(1)
    return builder.as_markup()

def gym_client_selection_keyboard(clients: list, plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in clients:
        builder.button(text=f"👤 {c.full_name}", callback_data=f"tr_gym_copy_to_client_{plan_id}_{c.id}")
    builder.button(text="🔙 Скасувати", callback_data=f"tr_gym_manage_0")
    builder.adjust(1)
    return builder.as_markup()

# Оновлюємо trainer_gym_manage_keyboard (якщо ще немає)
def trainer_gym_manage_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список планів", callback_data=f"tr_gym_plans_{client_id}")
    builder.button(text="➕ Створити новий план", callback_data=f"tr_gym_create_plan_{client_id}")
    builder.button(text="🏋️ Каталог вправ", callback_data=f"tr_gym_exercises_{client_id}")
    builder.button(text="📋 Шаблони", callback_data=f"tr_gym_templates_{client_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_view_{client_id}")
    builder.adjust(1)
    return builder.as_markup()


# ==================== НОВІ КЛАВІАТУРИ ДЛЯ СПОРТЗАЛУ ====================

def gym_exercise_list_keyboard(plan_exercises: list, completed_ids: list) -> InlineKeyboardMarkup:
    """Клавіатура зі списком вправ плану та статусами."""
    builder = InlineKeyboardBuilder()
    for pe in plan_exercises:
        status = "✅" if pe["id"] in completed_ids else "⬜"
        builder.button(
            text=f"{status} {pe['exercise'].name}",
            callback_data=f"gym_exercise_{pe['id']}"
        )
    if len(completed_ids) == len(plan_exercises):
        builder.button(text="🔚 Завершити тренування", callback_data="gym_finish_workout")
    builder.button(text="🔙 Назад", callback_data="client_food_home")
    builder.adjust(1)
    return builder.as_markup()

def gym_exercise_detail_keyboard(pe_id: int, remaining: int, last_weight: float = None) -> InlineKeyboardMarkup:
    """Клавіатура для деталей вправи (додати підхід, завершити)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати підхід", callback_data=f"gym_add_set_{pe_id}")
    if remaining == 0:
        builder.button(text="✅ Завершити вправу", callback_data=f"gym_complete_exercise_{pe_id}")
    builder.button(text="🔙 До списку", callback_data="gym_back_to_list")
    builder.adjust(1)
    return builder.as_markup()

def gym_edit_exercise_keyboard(exercise_id: int, client_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для редагування/видалення вправи в каталозі."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Редагувати назву", callback_data=f"tr_gym_edit_exercise_name_{exercise_id}")
    builder.button(text="🗑️ Видалити", callback_data=f"tr_gym_delete_exercise_{exercise_id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_exercises_{client_id}")
    builder.adjust(1)
    return builder.as_markup()

def gym_templates_keyboard(templates: list, client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.button(text=f"📋 {t.name}", callback_data=f"tr_gym_assign_template_{client_id}_{t.id}")
    builder.button(text="🔙 Назад", callback_data=f"tr_gym_manage_{client_id}")
    builder.adjust(1)
    return builder.as_markup()

def gym_client_selection_keyboard(clients: list, plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in clients:
        builder.button(text=f"👤 {c.full_name}", callback_data=f"tr_gym_copy_to_client_{plan_id}_{c.id}")
    builder.button(text="🔙 Скасувати", callback_data=f"tr_gym_manage_0")
    builder.adjust(1)
    return builder.as_markup()

# Оновлюємо trainer_gym_manage_keyboard (якщо потрібно)
# ==================== КЛАВІАТУРИ ДЛЯ ЗВІТІВ ====================

# ==================== КЛАВІАТУРИ ДЛЯ ЗВІТІВ ====================

def trainer_reports_clients_keyboard(clients: list) -> InlineKeyboardMarkup:
    """Клавіатура зі списком клієнтів для перегляду звітів."""
    builder = InlineKeyboardBuilder()
    for c in clients:
        builder.button(text=f"👤 {c.full_name}", callback_data=f"tr_reports_client_{c.id}")
    builder.button(text="🔙 Назад", callback_data="tr_reports_back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def trainer_reports_dates_keyboard(dates: list, client_id: int, page: int = 0, per_page: int = 7) -> InlineKeyboardMarkup:
    """Клавіатура зі списком дат для вибраного клієнта."""
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_dates = dates[start:end]
    
    for d in page_dates:
        date_str = d["date"]
        icons = []
        if d["has_food"]: icons.append("🍽️")
        if d["has_workout"]: icons.append("🏋️")
        label = f"{date_str} {' '.join(icons)}"
        builder.button(text=label, callback_data=f"tr_reports_date_{client_id}_{date_str}")
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"tr_reports_dates_{client_id}_{page-1}"))
    if end < len(dates):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"tr_reports_dates_{client_id}_{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.button(text="🔙 До клієнтів", callback_data="tr_reports_clients")
    builder.adjust(1)
    return builder.as_markup()

def trainer_report_detail_keyboard(client_id: int, date_str: str) -> InlineKeyboardMarkup:
    """Клавіатура для детального звіту."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 До списку дат", callback_data=f"tr_reports_dates_{client_id}_0")
    builder.button(text="📋 Інші клієнти", callback_data="tr_reports_clients")
    builder.adjust(1)
    return builder.as_markup()