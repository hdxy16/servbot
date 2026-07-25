from aiogram.fsm.state import StatesGroup, State

class FoodFSM(StatesGroup):
    add_product = State()
    choose_category = State()
    enter_amount = State()

class GymFSM(StatesGroup):
    create_workout = State()
    add_exercise = State()
    enter_weight = State()
    enter_reps = State()

class CheckinFSM(StatesGroup):
    sleep = State()
    energy = State()
    hunger = State()
    stress = State()
    comment = State()

class TrainerFSM(StatesGroup):
    create_client = State()
    edit_client = State()
    change_nutrition = State()