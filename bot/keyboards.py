from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def _toggle_style(enabled: bool) -> ButtonStyle:
    return ButtonStyle.SUCCESS if enabled else ButtonStyle.DANGER


def _ha_toggle_style(state: str) -> ButtonStyle:
    if state == "on":
        return ButtonStyle.SUCCESS
    if state == "off":
        return ButtonStyle.DANGER
    return ButtonStyle.PRIMARY


def budget_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=f"📂 {group}", callback_data=f"bgroup_{group}", style=ButtonStyle.PRIMARY)
    builder.button(text="🔄 Оновити", callback_data="budget_refresh", style=ButtonStyle.SUCCESS)
    builder.adjust(1)
    return builder.as_markup()

def budget_back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад до списку груп", callback_data="budget_refresh", style=ButtonStyle.PRIMARY)
    return builder.as_markup()

def expense_categories_keyboard() -> InlineKeyboardMarkup:
    cats = ["Різне", "Товари для дому", "Фаст-фуд", "Тютюн", "Вейпшоп", "Супермаркети"]
    builder = InlineKeyboardBuilder()
    for cat in cats:
        builder.button(text=f"📁 {cat}", callback_data=f"expcat_{cat}", style=ButtonStyle.PRIMARY)
    builder.adjust(2)
    return builder.as_markup()

def expense_draft_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Отримувач", callback_data="exp_set_payee", style=ButtonStyle.PRIMARY)
    builder.button(text="📝 Примітка", callback_data="exp_set_notes", style=ButtonStyle.PRIMARY)
    builder.button(text="✅ Відправити", callback_data="exp_submit", style=ButtonStyle.SUCCESS)
    builder.button(text="❌ Скасувати", callback_data="exp_cancel", style=ButtonStyle.DANGER)
    builder.adjust(2, 2)
    return builder.as_markup()

def payees_keyboard(payees: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in payees:
        builder.button(text=p, callback_data=f"setpayee_{p}", style=ButtonStyle.PRIMARY)
    builder.button(text="🔙 Назад до чернетки", callback_data="exp_back_to_draft", style=ButtonStyle.DANGER)
    builder.adjust(1)
    return builder.as_markup()

def settings_keyboard(notify_finance: bool, notify_calendar: bool, notify_climate: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fin_text = "🟢 Фінанси увімк." if notify_finance else "🔴 Фінанси вимк."
    cal_text = "🟢 Календар увімк." if notify_calendar else "🔴 Календар вимк."
    clim_text = "🟢 Клімат увімк." if notify_climate else "🔴 Клімат вимк."
    
    builder.button(text=fin_text, callback_data="toggle_notify_finance", style=_toggle_style(notify_finance))
    builder.button(text=cal_text, callback_data="toggle_notify_calendar", style=_toggle_style(notify_calendar))
    builder.button(text=clim_text, callback_data="toggle_notify_climate", style=_toggle_style(notify_climate))
    builder.button(text="🔙 Назад до Адмін", callback_data="admin_back", style=ButtonStyle.PRIMARY) # Перенаправлення
    builder.adjust(1)
    return builder.as_markup()

def ha_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌡 Датчики клімату", callback_data="ha_sensors", style=ButtonStyle.PRIMARY)
    builder.button(text="💡 Керування світлом", callback_data="ha_lights", style=ButtonStyle.PRIMARY)
    builder.button(text="⏰ Розумний будильник", callback_data="ha_alarm", style=ButtonStyle.PRIMARY)
    builder.adjust(1)
    return builder.as_markup()

# FILE: ./bot/keyboards.py

def ha_lights_keyboard(states: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # 1. ПАРНА СІТКА КЕРУВАННЯ (Кнопка стану + Кнопка тонкого регулювання)
    rooms = [
        ("Ванна", "light.bathroom_light_ceiling"),
        ("Коридор", "light.hallway_lights"),
        ("Спальня", "light.bedroom_light_floor"),
        ("Вітальня", "light.livingroom_light_floor")
    ]
    
    for name, entity_id in rooms:
        state = states.get(entity_id, "off")
        emoji = "💡 🟢" if state == "on" else "⚫"
        # Ліва кнопка — швидкий тумблер ON/OFF
        builder.button(text=f"{emoji} {name}", callback_data=f"ha_toggle_{entity_id}", style=_ha_toggle_style(state))
        # Права кнопка — перехід до налаштувань яскравості/кольору
        builder.button(text="⚙️ Налаштувати", callback_data=f"ha_opts_{entity_id}", style=ButtonStyle.PRIMARY)

    # 2. НОВІ АТМОСФЕРНІ СЦЕНІ
    builder.button(text="🔞 SEX MODE (Спальня приглушене пурпурне 20%)", callback_data="ha_scene_sex", style=ButtonStyle.PRIMARY)
    builder.button(text="🎬 Режим кіно (Спальня комфортне тепле 15%)", callback_data="ha_scene_cinema_bed", style=ButtonStyle.PRIMARY)
    
    # ПОКРАЩЕННЯ: Автоматичний таймер сну для всієї квартири
    builder.button(text="⏳ Запустити таймер сну (Вимкнути все через 15 хв)", callback_data="ha_light_timer_15", style=ButtonStyle.PRIMARY)
    
    # 3. СИСТЕМНІ КНОПКИ
    builder.button(text="🛑 ВИМКНУТИ ВСЕ СВІТЛО", callback_data="ha_scene_off_all", style=ButtonStyle.DANGER)
    builder.button(text="🔄 Оновити статуси", callback_data="ha_lights", style=ButtonStyle.PRIMARY)
    builder.button(text="🔙 Назад до меню", callback_data="ha_main_menu", style=ButtonStyle.PRIMARY)
    
    # Структура сітки: 4 рядки по 2 кнопки кімнат, сцени по одній, системні внизу
    builder.adjust(2, 2, 2, 2, 1, 1, 1, 1, 2)
    return builder.as_markup()

def ha_light_options_keyboard(entity_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔅 25%", callback_data=f"ha_set_{entity_id}_bri_25", style=ButtonStyle.PRIMARY)
    builder.button(text="🔆 50%", callback_data=f"ha_set_{entity_id}_bri_50", style=ButtonStyle.PRIMARY)
    builder.button(text="☀️ 100%", callback_data=f"ha_set_{entity_id}_bri_100", style=ButtonStyle.SUCCESS)
    
    if entity_id != "light.livingroom_light_floor":
        builder.button(text="🟠 Тепле", callback_data=f"ha_set_{entity_id}_temp_2700", style=ButtonStyle.PRIMARY)
        builder.button(text="⚪ Нейтр", callback_data=f"ha_set_{entity_id}_temp_4000", style=ButtonStyle.PRIMARY)
        builder.button(text="🔵 Холод", callback_data=f"ha_set_{entity_id}_temp_6000", style=ButtonStyle.PRIMARY)
        
        builder.button(text="🟥", callback_data=f"ha_set_{entity_id}_color_red", style=ButtonStyle.DANGER)
        builder.button(text="🟩", callback_data=f"ha_set_{entity_id}_color_green", style=ButtonStyle.SUCCESS)
        builder.button(text="🟦", callback_data=f"ha_set_{entity_id}_color_blue", style=ButtonStyle.PRIMARY)
        builder.button(text="🟨", callback_data=f"ha_set_{entity_id}_color_yellow", style=ButtonStyle.PRIMARY)
        builder.button(text="🟪", callback_data=f"ha_set_{entity_id}_color_purple", style=ButtonStyle.PRIMARY)

    builder.button(text="🔙 Назад", callback_data="ha_lights", style=ButtonStyle.DANGER)
    
    if entity_id != "light.livingroom_light_floor":
        builder.adjust(3, 3, 5, 1)
    else:
        builder.adjust(3, 1)
        
    return builder.as_markup()

def ha_alarm_keyboard(is_enabled: bool, current_time: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    status_emoji = "🟢 Увімкнено" if is_enabled else "🔴 Вимкнено"
    action = "turn_off" if is_enabled else "turn_on"
    
    builder.button(
        text=f"Статус: {status_emoji}",
        callback_data=f"alarm_toggle_{action}",
        style=_toggle_style(is_enabled),
    )
    builder.button(text="🌅 06:00", callback_data="alarm_set_06:00:00", style=ButtonStyle.SUCCESS)
    builder.button(text="🌅 07:00", callback_data="alarm_set_07:00:00", style=ButtonStyle.SUCCESS)
    builder.button(text="🌅 08:00", callback_data="alarm_set_08:00:00", style=ButtonStyle.SUCCESS)
    builder.button(text="✏️ Свій час", callback_data="alarm_custom", style=ButtonStyle.PRIMARY)
    builder.button(text="🚨 Тест дзвінка", callback_data="alarm_test", style=ButtonStyle.PRIMARY)
    builder.button(text="🔙 Назад", callback_data="ha_main_menu", style=ButtonStyle.DANGER)
    builder.adjust(1, 3, 2, 1)
    return builder.as_markup()

def alarm_ringing_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛑 Вимкнути повністю", callback_data="ringing_turn_off", style=ButtonStyle.DANGER)
    builder.button(text="💤 +5 хв", callback_data="ringing_snooze_5", style=ButtonStyle.SUCCESS)
    builder.button(text="💤 +10 хв", callback_data="ringing_snooze_10", style=ButtonStyle.SUCCESS)
    builder.adjust(1, 2)
    return builder.as_markup()
def wifi_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛜 QR для гостей (Main Wi-Fi)", callback_data="wifi_qr", style=ButtonStyle.PRIMARY)
    builder.button(text="📊 Fritz: Статистика", callback_data="wifi_stats", style=ButtonStyle.PRIMARY)
    builder.button(text="📱 Fritz: Пристрої", callback_data="wifi_devices", style=ButtonStyle.PRIMARY)
    builder.button(text="🔄 Ребут Fritz!Box", callback_data="wifi_reboot", style=ButtonStyle.DANGER)
    builder.button(text="🔙 Назад до Адмін", callback_data="admin_back", style=ButtonStyle.PRIMARY) # Перенаправлення
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()
def admin_inline_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Мережа (Fritz!Box)", callback_data="wifi_main_menu")
    builder.button(text="🛡️ Захист AdGuard Home", callback_data="admin_adguard") # Нова кнопка
    builder.button(text="⚙️ Сповіщення", callback_data="admin_settings")
    builder.button(text="🖥️ Телеметрія PVE (Сервер)", callback_data="sys_refresh")
    builder.button(text="👥 Права користувачів", callback_data="admin_users")
    builder.adjust(2, 1, 2) # Рівне, красиве розташування кнопок
    return builder.as_markup()
def admin_adguard_keyboard(filtering_state: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    status_emoji = "🟢 Активний" if filtering_state == "on" else "🔴 Вимкнений"
    action = "turn_off" if filtering_state == "on" else "turn_on"
    
    # Головний тумблер ON/OFF
    builder.button(text=f"Захист: {status_emoji}", callback_data=f"agh_toggle_{action}", style=_ha_toggle_style(filtering_state))
    
    # Кнопка швидкої паузи (показується тільки якщо захист зараз увімкнено)
    if filtering_state == "on":
        builder.button(text="⏸️ Призупинити захист на 15 хв", callback_data="agh_pause_15", style=ButtonStyle.PRIMARY)
        
    builder.button(text="🔄 Оновити статус", callback_data="admin_adguard", style=ButtonStyle.SUCCESS)
    builder.button(text="🔙 Назад до Адмін", callback_data="admin_back", style=ButtonStyle.DANGER)
    builder.adjust(1)
    return builder.as_markup()
# У файлі bot/keyboards.py змінити функцію:
def main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📊 Фінанси"), KeyboardButton(text="🎛 Розумний дім")],
        [KeyboardButton(text="🚌 Автобус"), KeyboardButton(text="📅 Календар")],
        [KeyboardButton(text="🏋️ Спортзал"), KeyboardButton(text="🍏 Трекер їжі")],
    ]
    if is_admin:
        # Всі інші адмінські кнопки прибрані звідси і сховані під цю кнопку
        kb.append([KeyboardButton(text="🛠️ Адмін")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)

def event_confirm_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Кнопки для вечірнього підтвердження 'я пам'ятаю про завтрашню подію'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Так, пам'ятаю", callback_data=f"event_confirm_{event_id}")
    builder.button(text="🔁 Нагадати ще раз", callback_data=f"event_snooze_{event_id}")
    builder.adjust(1)
    return builder.as_markup()


def calendar_menu_keyboard() -> InlineKeyboardMarkup:
    """Підменю кнопки '📅 Календар' в головному меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати подію", callback_data="cal_add")
    builder.button(text="📋 Мої події", callback_data="cal_list")
    builder.adjust(1)
    return builder.as_markup()

def pve_main_keyboard(resources: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in resources:
        vmid = item.get("vmid")
        name = item.get("name", "Unknown")
        status = item.get("status", "stopped")
        gtype = item.get("type", "lxc").upper()
        mark = "🟢" if status == "running" else "🔴"
        builder.button(
            text=f"{mark} [{gtype}] {name} (ID: {vmid})",
            callback_data=f"sys_view_{item.get('type')}_{vmid}"
        )
    builder.adjust(1)
    builder.button(text="🔄 Оновити дані", callback_data="sys_refresh", style=ButtonStyle.SUCCESS)
    builder.button(text="🔙 Назад до Адмін", callback_data="admin_back", style=ButtonStyle.DANGER) # Змінено з ha_main_menu
    builder.adjust(1)
    return builder.as_markup()

def pve_guest_control_keyboard(vmid: int, gtype: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Запустити (Start)", callback_data=f"sys_act_{gtype}_{vmid}_start", style=ButtonStyle.SUCCESS)
    builder.button(text="🔄 Перезавантажити", callback_data=f"sys_act_{gtype}_{vmid}_reboot", style=ButtonStyle.PRIMARY)
    builder.button(text="🛑 Зупинити (Shutdown)", callback_data=f"sys_act_{gtype}_{vmid}_shutdown", style=ButtonStyle.DANGER)
    builder.button(text="⚡ Вбити процес (Stop)", callback_data=f"sys_act_{gtype}_{vmid}_stop", style=ButtonStyle.DANGER)
    builder.button(text="🔙 До списку вузлів", callback_data="sys_refresh", style=ButtonStyle.PRIMARY)
    builder.adjust(2, 2, 1)
    return builder.as_markup()    