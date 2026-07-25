from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def scale_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Створює клавіатуру з оцінками від 1 до 5."""
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text=str(i), callback_data=f"{prefix}:{i}")
    builder.adjust(5)
    return builder.as_markup()


def trainer_checkins_keyboard(clients):
    """Створює клавіатуру зі списком клієнтів для перегляду чекінів."""
    builder = InlineKeyboardBuilder()
    for client in clients:
        builder.button(
            text=f"👤 {client.full_name}",
            callback_data=f"trainer_checkin:{client.id}"
        )
    builder.adjust(1)
    return builder.as_markup()


def checkin_answer_keyboard(checkin_id: int) -> InlineKeyboardMarkup:
    """Створює клавіатуру для відповіді на чекін."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬 Відповісти клієнту",
        callback_data=f"reply_checkin:{checkin_id}"
    )
    builder.button(
        text="⬅️ Назад",
        callback_data="back_checkins"
    )
    builder.adjust(1)
    return builder.as_markup()