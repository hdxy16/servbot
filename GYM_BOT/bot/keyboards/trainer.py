from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

class TrainerClientCB(CallbackData, prefix="tr_cl"):
    action: str
    client_id: int = 0
    page: int = 1
    field: str = ""

def trainer_main_keyboard() -> InlineKeyboardMarkup:
    """Може використовуватись для інлайн-меню тренера (дублює Reply-клавіатуру)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Мої клієнти", callback_data=TrainerClientCB(action="list").pack())
    builder.button(text="📊 Статистика", callback_data=TrainerClientCB(action="stats").pack())
    builder.adjust(1)
    return builder.as_markup()

def clients_list_keyboard(clients_data: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for user, profile in clients_data:
        status = "🟢" if profile.is_active else "🔴"
        builder.button(
            text=f"{status} {user.full_name}",
            callback_data=TrainerClientCB(action="card", client_id=user.id).pack()
        )
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardBuilder().button(text="◀️ Назад", callback_data=TrainerClientCB(action="list", page=page-1).pack())
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardBuilder().button(text="▶️ Далі", callback_data=TrainerClientCB(action="list", page=page+1).pack())
        )
        
    builder.adjust(1)
    if nav_buttons:
        builder.row(*(btn.buttons[0] for btn in nav_buttons))
        
    return builder.as_markup()

def client_card_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Інфо", callback_data=TrainerClientCB(action="info", client_id=client_id).pack())
    builder.button(text="🍎 Харчування", callback_data=TrainerClientCB(action="food", client_id=client_id).pack())
    builder.button(text="🏋️ Тренування", callback_data=TrainerClientCB(action="gym", client_id=client_id).pack())
    builder.button(text="📈 Прогрес", callback_data=TrainerClientCB(action="progress", client_id=client_id).pack())
    builder.button(text="💬 Чат", callback_data=TrainerClientCB(action="chat", client_id=client_id).pack())
    builder.button(text="📅 Календар", callback_data=TrainerClientCB(action="calendar", client_id=client_id).pack())
    builder.button(text="⚙️ Налаштування", callback_data=TrainerClientCB(action="settings", client_id=client_id).pack())
    builder.button(text="🗑 Видалити", callback_data=TrainerClientCB(action="delete", client_id=client_id).pack())
    
    builder.adjust(2, 2, 2, 2)
    builder.row(InlineKeyboardBuilder().button(text="🔙 До списку", callback_data=TrainerClientCB(action="list", page=1).pack()).buttons[0])
    return builder.as_markup()

def client_edit_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = [
        ("Ім'я", "name"), ("Вік", "age"), ("Стать", "gender"), 
        ("Ріст", "height"), ("Стартова вага", "start_weight"), 
        ("Поточна вага", "current_weight"), ("Ціль", "goal"), 
        ("Рівень", "level"), ("Наступний чекін", "next_checkin"), 
        ("Нотатки", "notes")
    ]
    
    for label, field in fields:
        builder.button(
            text=f"✏️ {label}", 
            callback_data=TrainerClientCB(action="edit_field", client_id=client_id, field=field).pack()
        )
        
    builder.adjust(2)
    builder.row(InlineKeyboardBuilder().button(text="🔙 Назад до картки", callback_data=TrainerClientCB(action="card", client_id=client_id).pack()).buttons[0])
    return builder.as_markup()

def cancel_edit_keyboard(client_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Скасувати", callback_data=TrainerClientCB(action="card", client_id=client_id).pack())
    return builder.as_markup()