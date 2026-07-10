# FILE: ./bot/gym_data.py
"""
Статична програма тренувань. Щоб змінити вправи/схему підходів —
редагуй тільки цей файл, решта коду підхопить зміни автоматично.
"""

WORKOUT_PROGRAM = {
    "upper_a": {
        "title": "Верх А",
        "exercises": [
            {"key": "bench_press", "name": "Жим штанги лежачи", "sets": 3, "reps": "6–10"},
            {"key": "lat_pulldown", "name": "Тяга вертикального блока", "sets": 3, "reps": "8–12"},
            {"key": "db_shoulder_press", "name": "Жим гантелей сидячи", "sets": 2, "reps": "8–12"},
            {"key": "pec_deck", "name": "Розведення у тренажері (Pec Deck)", "sets": 2, "reps": "12–15"},
            {"key": "seated_row", "name": "Горизонтальна тяга блока", "sets": 2, "reps": "10–15"},
            {"key": "db_curl", "name": "Згинання рук з гантелями на біцепс сидячи", "sets": 2, "reps": "10–15"},
            {"key": "triceps_pushdown", "name": "Розгинання рук на блоці (гриф)", "sets": 2, "reps": "10–15"},
        ],
    },
    "lower_a": {
        "title": "Низ А",
        "exercises": [
            {"key": "squat", "name": "Присідання зі штангою", "sets": 3, "reps": "6–10"},
            {"key": "rdl", "name": "Румунська тяга", "sets": 3, "reps": "8–10"},
            {"key": "leg_press", "name": "Жим ногами", "sets": 2, "reps": "10–15"},
            {"key": "leg_curl", "name": "Згинання ніг лежачи", "sets": 2, "reps": "10–15"},
            {"key": "calf_raise_a", "name": "Підйом на носки стоячи/сидячи", "sets": 3, "reps": "10–15"},
            {"key": "crunches", "name": "Скручування", "sets": 3, "reps": "10–20"},
        ],
    },
    "upper_b": {
        "title": "Верх Б",
        "exercises": [
            {"key": "incline_db_press", "name": "Жим гантелей під кутом", "sets": 3, "reps": "8–12"},
            {"key": "bent_row", "name": "Тяга штанги в нахилі / Т-гриф", "sets": 3, "reps": "8–12"},
            {"key": "lateral_raise", "name": "Махи гантелями в сторони", "sets": 3, "reps": "12–15"},
            {"key": "dips", "name": "Віджимання на брусах", "sets": 2, "reps": "10–15"},
            {"key": "pullups", "name": "Підтягування", "sets": 2, "reps": "Max"},
            {"key": "scott_curl", "name": "Згинання рук на лаві Скотта", "sets": 2, "reps": "10–15"},
            {"key": "rope_extension", "name": "Французьке розгинання з канатом", "sets": 2, "reps": "10–15"},
        ],
    },
    "lower_b": {
        "title": "Низ Б",
        "exercises": [
            {"key": "hack_squat", "name": "Гак-присід", "sets": 3, "reps": "8–12"},
            {"key": "db_rdl", "name": "Румунська тяга з гантелями", "sets": 3, "reps": "8–12"},
            {"key": "leg_extension", "name": "Розгинання ніг", "sets": 2, "reps": "12–15"},
            {"key": "leg_curl_b", "name": "Згинання ніг", "sets": 2, "reps": "12–15"},
            {"key": "calf_raise_b", "name": "Підйом на носки сидячи/стоячи", "sets": 3, "reps": "12–20"},
            {"key": "abs_machine", "name": "Скручування прес / тренажер на прес", "sets": 3, "reps": "12–20"},
        ],
    },
}

# Порядок автоматичної ротації
DAY_ORDER = ["upper_a", "lower_a", "upper_b", "lower_b"]


def get_exercise_name(exercise_key: str) -> str:
    for day in WORKOUT_PROGRAM.values():
        for ex in day["exercises"]:
            if ex["key"] == exercise_key:
                return ex["name"]
    return exercise_key