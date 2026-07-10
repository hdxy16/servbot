# FILE: ./bot/alarm_monitor.py
import logging
from datetime import datetime
from aiogram import Bot
from database.engine import AsyncSessionLocal
from database.models import User
from sqlalchemy import select
from bot.home_assistant import ha_client
from bot.keyboards import alarm_ringing_keyboard

logger = logging.getLogger(__name__)
last_alarm_sent_time = None

async def check_alarm_trigger(bot: Bot):
    global last_alarm_sent_time
    
    # Перевіряємо, чи будильник взагалі увімкнений
    enabled_state = await ha_client.get_entity_state("input_boolean.smart_alarm_enabled")
    if enabled_state.get("state") != "on":
        return
        
    time_state = await ha_client.get_entity_state("input_datetime.smart_alarm_time")
    alarm_time_str = time_state.get("state", "00:00:00")[:5]
    
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    
    # Якщо поточний час збігається з часом будильника
    if current_time_str == alarm_time_str:
        if last_alarm_sent_time == current_time_str:
            return  # Захист від дублювання в межах однієї хвилини
        
        last_alarm_sent_time = current_time_str
        
        # Отримуємо користувачів, яким можна слати (admin, trusted)
        async with AsyncSessionLocal() as session:
            stmt = select(User.telegram_id).where(User.role.in_(["admin", "trusted"]))
            recipients = (await session.execute(stmt)).scalars().all()
        
        text = (
            f"⏰ <b>БУДИЛЬНИК ДЗВОНИТЬ!</b>\n\n"
            f"Час: <b>{current_time_str}</b>\n"
            f"Що робимо?"
        )
        
        for uid in recipients:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=text,
                    reply_markup=alarm_ringing_keyboard(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Не вдалося надіслати сповіщення про будильник {uid}: {e}")