from aiogram.fsm.state import StatesGroup, State


class CheckinFSM(StatesGroup):

    sleep = State()
    energy = State()
    hunger = State()
    stress = State()
    feeling = State()