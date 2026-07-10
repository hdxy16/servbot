from bot.bus_data import SCHEDULE_TO_CENTER, SCHEDULE_TO_HOME
from datetime import datetime

def get_next_buses(schedule, limit=3):
    now = datetime.now().strftime("%H:%M")
    upcoming = [t for t in schedule if t > now]
    if not upcoming:
        return "На сьогодні автобусів більше немає."
    return ", ".join(upcoming[:limit])

def get_bus_info(direction):
    if direction == "home":
        return f"🚌 Додому (з Postplatz):\n🕒 Наступні: {get_next_buses(SCHEDULE_TO_HOME)}"
    else:
        return f"🚌 В центр (з Agricolastr.):\n🕒 Наступні: {get_next_buses(SCHEDULE_TO_CENTER)}"