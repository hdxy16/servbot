from aiogram.fsm.state import StatesGroup, State

class WorkoutCreateFSM(StatesGroup):
    program_name = State()
    description = State()
    days_count = State()

class ExerciseCreateFSM(StatesGroup):
    waiting_for_search = State()
    sets = State()
    reps = State()
    note_and_rest = State() # Тренер пише одним текстом: "Не відривай таз. Відпочинок 90с"

class WorkoutExecutionFSM(StatesGroup):
    weight_reps_rpe = State() # Чекає вводу формату "80 8 8" (Вага Повтори RPE)