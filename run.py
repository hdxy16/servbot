# FILE: ./run.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from aiohttp import web  # <-- Наш асинхронний сервер вебхуків
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from datetime import datetime, timedelta

from config import BOT_TOKEN, ALLOWED_USER_ID
from database.engine import init_db, UsersSessionLocal, CalendarSessionLocal
from database.models import CalendarEvent, User

from bot.handlers import router as main_router
from bot.handlers_calendar import router as calendar_router
from bot.handlers_network import router as network_router
from bot.handlers_gym import router as gym_router
from bot.handlers_food import router as food_router, upsert_iphone_steps # <-- Додали модуль їжі
from bot.handlers_system import router as system_router
from bot.proxmox_client import pve_client
from bot.climate_monitor import check_climate_thresholds
from bot.actual_api import get_budget_data
from bot.home_assistant import ha_client
from bot.alarm_monitor import check_alarm_trigger
from bot.fritz_api import get_active_devices
from bot.keyboards import event_confirm_keyboard
from bot.icloud_sync import icloud_pull_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
KNOWN_DEVICES_MACS = set()

# ==========================================
# ВЕБХУК ПРИЙМАЧ ДЛЯ IPHONE (HEALTHKIT STEPS)
# ==========================================
async def handle_iphone_steps_webhook(request):
    try:
        data = await request.json()
        steps = int(data.get("steps", 0))
        user_id = int(data.get("user_id", ALLOWED_USER_ID))
        
        today = datetime.now().strftime("%Y-%m-%d")
        # Зберігаємо кроки в базу даних їжі
        await upsert_iphone_steps(user_id, today, steps)
        
        logger.info(f"📲 Отримано Webhook з iPhone: зареєстровано {steps} кроків для користувача {user_id}")
        return web.json_response({"status": "success", "steps_logged": steps})
    except Exception as e:
        logger.error(f"Помилка обробки вебхуку кроків з iPhone: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=400)

async def init_admin():
    async with UsersSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == ALLOWED_USER_ID)
        admin = (await session.execute(stmt)).scalar_one_or_none()
        if not admin:
            new_admin = User(
                telegram_id=ALLOWED_USER_ID,
                role="admin",
                is_approved=True,
                notify_finance=True,
                notify_calendar=True,
                notify_climate=True,
                notify_network=True
            )
            session.add(new_admin)
            await session.commit()
            logger.info("Головного адміністратора (ID: %s) додано в БД.", ALLOWED_USER_ID)

async def scheduled_network_radar():
    global KNOWN_DEVICES_MACS
    devices = await get_active_devices()
    if not devices: return
    current_macs = {d['mac'] for d in devices if d['mac'] != '-'}
    if not KNOWN_DEVICES_MACS:
        KNOWN_DEVICES_MACS = current_macs
        return
    new_macs = current_macs - KNOWN_DEVICES_MACS
    if new_macs:
        KNOWN_DEVICES_MACS.update(new_macs)
        alert_text = "🛡 <b>РАДАР МЕРЕЖІ</b>\n\nНові пристрої підключилися до Wi-Fi:\n"
        for d in devices:
            if d['mac'] in new_macs:
                alert_text += f"• <b>{d['name']}</b> (MAC: <code>{d['mac']}</code>)\n"
        async with UsersSessionLocal() as session:
            stmt = select(User.telegram_id).where(User.notify_network == True, User.role == "admin")
            recipients = (await session.execute(stmt)).scalars().all()
        for uid in recipients:
            try: await bot.send_message(uid, alert_text, parse_mode="HTML")
            except Exception: pass

async def daily_report():
    async with UsersSessionLocal() as session:
        stmt_users = select(User.telegram_id).where(User.notify_finance == True)
        recipients = (await session.execute(stmt_users)).scalars().all()
    if not recipients: return
    data = await get_budget_data()
    if not data: return
    text = (
        f"🕒 <b>Щоденний фінансовий підсумок (23:59)</b>\n"
        f"💰 Загальний вільний залишок: <b>{data['total_balance']:.2f}€</b>\n\n"
        f"<i>Всі транзакції успішно синхронізовано з Actual Budget.</i>\n"
        f"Щоб переглянути деталі, натисніть кнопку '📊 Фінанси' у меню."
    )
    for uid in recipients:
        try: await bot.send_message(uid, text, parse_mode="HTML")
        except Exception: pass

async def daily_agenda_digest():
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    async with CalendarSessionLocal() as session:
        stmt = select(CalendarEvent).where(
            CalendarEvent.event_date >= today_start,
            CalendarEvent.daily_reminder == True,
            CalendarEvent.is_archived == False,
        ).order_by(CalendarEvent.event_date)
        events = (await session.execute(stmt)).scalars().all()
        by_user: dict[int, list[CalendarEvent]] = {}
        for e in events: by_user.setdefault(e.user_id, []).append(e)
        for uid, user_events in by_user.items():
            today_lines, upcoming_lines = [], []
            for e in user_events:
                days_left = (e.event_date.date() - now.date()).days
                if days_left == 0: today_lines.append(f"• {e.event_date.strftime('%H:%M')} — {e.title}")
                else:
                    word = "день" if days_left == 1 else ("дні" if 2 <= days_left <= 4 else "днів")
                    upcoming_lines.append(f"• За <b>{days_left} {word}</b> ({e.event_date.strftime('%d.%m')}) — {e.title}")
            parts = []
            if today_lines: parts.append("🔔 <b>Сьогодні:</b>\n" + "\n".join(today_lines))
            if upcoming_lines: parts.append("📅 <b>Наближається:</b>\n" + "\n".join(upcoming_lines))
            if parts:
                try: await bot.send_message(uid, "\n\n".join(parts), parse_mode="HTML")
                except Exception: pass

async def evening_confirmation_check():
    now = datetime.utcnow()
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow_start + timedelta(days=1)
    async with CalendarSessionLocal() as session:
        stmt = select(CalendarEvent).where(
            CalendarEvent.event_date >= tomorrow_start,
            CalendarEvent.event_date < tomorrow_end,
            CalendarEvent.confirmed == False,
            CalendarEvent.is_archived == False,
        )
        events = (await session.execute(stmt)).scalars().all()
        for e in events:
            if e.last_reminder_at and (now - e.last_reminder_at) < timedelta(hours=1): continue
            if e.reminder_stage == 0:
                text = f"📌 <b>Завтра о {e.event_date.strftime('%H:%M')} — {e.title}</b>\nПідтвердиш, що пам'ятаєш?"
            else:
                text = f"⚠️ <b>Нагадую ще раз:</b> завтра о {e.event_date.strftime('%H:%M')} — {e.title}\nТи ще не підтвердив(-ла) — не забудь!"
            e.last_reminder_at = now
            try: await bot.send_message(e.user_id, text, parse_mode="HTML", reply_markup=event_confirm_keyboard(e.id))
            except Exception: pass
        await session.commit()

async def archive_past_events():
    cutoff = datetime.utcnow() - timedelta(days=1)
    async with CalendarSessionLocal() as session:
        stmt = select(CalendarEvent).where(CalendarEvent.event_date < cutoff, CalendarEvent.is_archived == False)
        events = (await session.execute(stmt)).scalars().all()
        for e in events: e.is_archived = True
        await session.commit()

async def scheduled_climate_check():
    try: await check_climate_thresholds(bot)
    except Exception as e: logger.error("Помилка в check_climate_thresholds: %s", e, exc_info=True)

async def scheduled_alarm_check():
    try: await check_alarm_trigger(bot)
    except Exception as e: logger.error("Помилка в scheduled_alarm_check: %s", e, exc_info=True)

async def main():
    await init_db()
    await init_admin()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_report, "cron", hour=23, minute=59)
    scheduler.add_job(scheduled_climate_check, "interval", minutes=5)
    scheduler.add_job(scheduled_alarm_check, "cron", second=0)
    scheduler.add_job(scheduled_network_radar, "interval", minutes=5)
    scheduler.add_job(daily_agenda_digest, "cron", hour=8, minute=0)
    scheduler.add_job(evening_confirmation_check, "cron", hour=20, minute=0)
    scheduler.add_job(evening_confirmation_check, "cron", hour=22, minute=0)
    scheduler.add_job(archive_past_events, "cron", hour=3, minute=0)
    scheduler.add_job(icloud_pull_sync, "interval", minutes=15)
    scheduler.start()

    # СТАРТ ЛОКАЛЬНОГО HTTP ВЕБ-СЕРВЕРА ДЛЯ ВЕБХУКІВ IPHONE
    webapp = web.Application()
    webapp.router.add_post('/webhook/steps', handle_iphone_steps_webhook)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080) # Порт 8080 всередині контейнера
    await site.start()
    logger.info("📡 HTTP Веб-сервер для кроків iPhone успішно запущено на порту 8080...")

    dp = Dispatcher()
    dp.include_router(calendar_router)
    dp.include_router(network_router)
    dp.include_router(gym_router)
    dp.include_router(food_router)
    dp.include_router(system_router)  # <-- ДОДАНО ТУТ
    dp.include_router(main_router)

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        logger.error("Необроблена помилка під час обробки update: %s", event.exception, exc_info=True)
        try:
            update = event.update
            chat_id = None
            if update.message: chat_id = update.message.chat.id
            elif update.callback_query and update.callback_query.message: chat_id = update.callback_query.message.chat.id
            if chat_id: await bot.send_message(chat_id, "⚠️ Сталася внутрішня помилка. Спробуйте ще раз трохи пізніше.")
        except Exception: pass
        return True

    logger.info("Бот та планувальник успішно запущено...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await ha_client.close()
        await pve_client.close()       # <-- ДОДАНО ТУТ
        await bot.session.close()
        await runner.cleanup()
        scheduler.shutdown(wait=False)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logger.info("Роботу завершено.")