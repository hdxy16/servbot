from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData


class ClientAction(CallbackData, prefix="client"):
    action: str
    client_id: int


class TrainerMenu(CallbackData, prefix="trainer"):
    action: str


def clients_list_kb(clients: list) -> InlineKeyboardMarkup:
    """Генерує інлайн клавіатуру зі списком клієнтів тренера."""
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.button(
            text=client.full_name,
            callback_data=ClientAction(action="view", client_id=client.id).pack()
        )
    builder.button(text="➕ Додати клієнта", callback_data=TrainerMenu(action="add_client").pack())
    builder.adjust(1)
    return builder.as_markup()


def client_profile_kb(client_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для керування конкретним клієнтом з панелі тренера."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Інфо", callback_data=ClientAction(action="info", client_id=client_id).pack())
    builder.button(text="🍎 Харчування", callback_data=ClientAction(action="food", client_id=client_id).pack())
    builder.button(text="🏋️ Тренування", callback_data=ClientAction(action="gym", client_id=client_id).pack())
    builder.button(text="📈 Прогрес", callback_data=ClientAction(action="progress", client_id=client_id).pack())
    builder.button(text="💬 Чат", callback_data=ClientAction(action="chat", client_id=client_id).pack())
    builder.button(text="📅 Календар", callback_data=ClientAction(action="calendar", client_id=client_id).pack())
    builder.button(text="⚙️ Налаштування", callback_data=ClientAction(action="settings", client_id=client_id).pack())
    
    builder.adjust(2)
    return builder.as_markup()