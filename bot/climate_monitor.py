# FILE: ./bot/climate_monitor.py
from datetime import datetime, timedelta
from aiogram import Bot
from config import ALLOWED_USER_ID
from bot.home_assistant import ha_client
from database.engine import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

# Професійне налаштування критичних меж
THRESHOLDS = {
    "sensor.kitchen_sensor_climate_temperature": {
        "max": 28.0, 
        "name": "🍳 Кухня (Температура)", 
        "unit": "°C"
    },
    "sensor.kitchen_sensor_climate_humidity": {
        "max": 70.0, 
        "name": "🍳 Кухня (Вологість)", 
        "unit": "%"
    },
    "sensor.bathroom_sensor_climate_temperature": {
        "max": 30.0, 
        "name": "🛁 Ванна кімната (Температура)", 
        "unit": "°C"
    },
    "sensor.bathroom_sensor_climate_humidity": {
        "max": 82.0, 
        "name": "🛁 Ванна кімната (Вологість)", 
        "unit": "%"
    }
}

# Внутрішній кеш для збереження часу останнього алерта (cooldown - 1 година)
ALERT_COOLDOWN_PERIOD = timedelta(hours=1)
last_sent_alerts = {}

async def check_climate_thresholds(bot: Bot):
    """Фонова задача перевірки лімітів клімату"""
    now = datetime.utcnow()

    for entity_id, rules in THRESHOLDS.items():
        state_data = await ha_client.get_entity_state(entity_id)
        raw_state = state_data.get("state")

        try:
            current_value = float(raw_state)
        except (ValueError, TypeError):
            continue

        # Якщо показник перевищує норму
        if current_value > rules["max"]:
            last_alert_time = last_sent_alerts.get(entity_id)

            if last_alert_time and (now - last_alert_time) < ALERT_COOLDOWN_PERIOD:
                continue

            alert_text = (
                f"⚠️ <b>КЛІМАТИЧНА ТРИВОГА</b>\n\n"
                f"🚨 Об'єкт: <b>{rules['name']}</b>\n"
                f"📈 Поточне значення: <pre>{current_value}{rules['unit']}</pre>\n"
                f"🛑 Встановлений ліміт: <b>{rules['max']}{rules['unit']}</b>\n\n"
                f"<i>Рекомендується перевірити приміщення або увімкнути вентиляцію.</i>"
            )

            # Отримуємо користувачів, у яких увімкнено сповіщення про клімат
            async with AsyncSessionLocal() as session:
                stmt = select(User.telegram_id).where(User.notify_climate == True)
                result = await session.execute(stmt)
                recipients = result.scalars().all()

            for uid in recipients:
                try:
                    await bot.send_message(chat_id=uid, text=alert_text, parse_mode="HTML")
                except Exception as e:
                    print(f"Помилка надсилання алерта користувачу {uid}: {e}")
                    
            # Оновлюємо час останнього алерта, тільки якщо комусь його відправили
            if recipients:
                last_sent_alerts[entity_id] = now