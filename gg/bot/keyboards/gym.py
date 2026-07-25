from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

class TrainerGymCB(CallbackData, prefix="tr_g"):
    action: str
    client_id: int = 0
    prog_id: int = 0
    day_id: int = 0
    ex_id: int = 0

class ClientGymCB(CallbackData, prefix="cl_g"):
    action: str
    sess_id: int = 0
    day_id: int = 0
    we_id: int = 0

def trainer_program_card_kb(client_id: int, has_program: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_program:
        builder.button(text="👀 Переглянути план", callback_data=TrainerGymCB(action="view_prog", client_id=client_id).pack())
        builder.button(text="🗑 Видалити план", callback_data=TrainerGymCB(action="del_prog", client_id=client_id).pack())
    
    builder.button(text="📂 Вибрати з шаблонів", callback_data=TrainerGymCB(action="templates", client_id=client_id).pack())
    builder.button(text="➕ Створити нову", callback_data=TrainerGymCB(action="new_prog", client_id=client_id).pack())
    builder.button(text="🔙 Назад до клієнта", callback_data=f"tr_cl:card:{client_id}:1:")
    builder.adjust(1)
    return builder.as_markup()

def trainer_templates_kb(client_id: int, templates: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.button(text=t.name, callback_data=TrainerGymCB(action="assign", client_id=client_id, prog_id=t.id).pack())
    builder.button(text="🔙 Назад", callback_data=TrainerGymCB(action="card", client_id=client_id).pack())
    builder.adjust(1)
    return builder.as_markup()

def trainer_days_kb(client_id: int, prog_id: int, days: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for d in days:
        builder.button(text=d.name, callback_data=TrainerGymCB(action="view_day", client_id=client_id, day_id=d.id).pack())
    builder.button(text="🔙 Назад", callback_data=TrainerGymCB(action="card", client_id=client_id).pack())
    builder.adjust(1)
    return builder.as_markup()

def trainer_day_exercises_kb(client_id: int, day_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати вправу", callback_data=TrainerGymCB(action="add_ex", client_id=client_id, day_id=day_id).pack())
    builder.button(text="🔙 Назад до днів", callback_data=TrainerGymCB(action="view_prog", client_id=client_id).pack())
    builder.adjust(1)
    return builder.as_markup()

def search_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="cancel_fsm").as_markup()

def client_gym_main_kb(active_session_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if active_session_id:
        builder.button(text="▶️ Продовжити тренування", callback_data=ClientGymCB(action="resume", sess_id=active_session_id).pack())
    else:
        builder.button(text="🏁 Почати нове тренування", callback_data=ClientGymCB(action="pick_day").pack())
    builder.button(text="📊 Статистика", callback_data=ClientGymCB(action="stats").pack())
    builder.adjust(1)
    return builder.as_markup()

def client_pick_day_kb(days: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for d in days:
        builder.button(text=d.name, callback_data=ClientGymCB(action="start_day", day_id=d.id).pack())
    builder.button(text="❌ Скасувати", callback_data=ClientGymCB(action="main").pack())
    builder.adjust(1)
    return builder.as_markup()

def client_workout_kb(sess_id: int, exercises_status: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for we_id, ex_name, is_done, done_sets, target_sets in exercises_status:
        mark = "✅" if is_done else "▶️"
        builder.button(
            text=f"{mark} {ex_name} ({done_sets}/{target_sets})",
            callback_data=ClientGymCB(action="do_ex", sess_id=sess_id, we_id=we_id).pack()
        )
    builder.button(text="🏆 Завершити тренування", callback_data=ClientGymCB(action="finish", sess_id=sess_id).pack())
    builder.adjust(1)
    return builder.as_markup()

def client_execute_ex_kb(sess_id: int, we_id: int, target_sets: int = 3, done_sets: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if done_sets < target_sets:
        builder.button(text="✍️ Записати підхід", callback_data=ClientGymCB(action="log_set", sess_id=sess_id, we_id=we_id).pack())
    builder.button(text="🔙 До списку вправ", callback_data=ClientGymCB(action="resume", sess_id=sess_id).pack())
    builder.adjust(1)
    return builder.as_markup()

def workout_stats_kb(sess_id: int = 0) -> InlineKeyboardMarkup:
    """Клавіатура для статистики тренувань."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=ClientGymCB(action="main").pack())
    builder.adjust(1)
    return builder.as_markup()