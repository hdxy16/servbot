from aiogram.fsm.state import StatesGroup, State

class TrainerNutritionFSM(StatesGroup):
    waiting_for_value = State()
    waiting_for_reason = State()

class ClientFoodFSM(StatesGroup):
    waiting_for_search = State()
    waiting_for_amount = State()
    waiting_for_anything_portions = State()
    waiting_for_photo_desc = State()