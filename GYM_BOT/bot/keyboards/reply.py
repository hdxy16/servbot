from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database.models import User

def get_main_menu(user_db: User) -> ReplyKeyboardMarkup:
    """Генерує головне меню в залежності від поточної активної ролі користувача."""
    kb = []
    
    if user_db.active_role == "ADMIN":
        kb = [
            [KeyboardButton(text="👥 Клієнти"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📢 Розсилки"), KeyboardButton(text="⚙️ Налаштування")],
            [KeyboardButton(text="📝 Логи")]
        ]
    elif user_db.active_role == "TRAINER":
        kb = [
            [KeyboardButton(text="👥 Клієнти"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🍎 Харчування"), KeyboardButton(text="🏋️ Тренування")],
            [KeyboardButton(text="📢 Розсилка"), KeyboardButton(text="⚙️ Налаштування")],
            [KeyboardButton(text="🧪 Тест клієнта")]
        ]
    else:  # CLIENT
        kb = [
            [KeyboardButton(text="🍎 Мій раціон"), KeyboardButton(text="🏋️ Моє тренування")],
            [KeyboardButton(text="📈 Мій прогрес"), KeyboardButton(text="💬 Написати тренеру")],
            [KeyboardButton(text="📚 FAQ"), KeyboardButton(text="⚙️ Профіль")]
        ]
        
    # Якщо користувач має більше однієї ролі — даємо кнопку переключення
    if len(user_db.roles) > 1:
        kb.append([KeyboardButton(text="🔄 Переключити режим")])
        
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)