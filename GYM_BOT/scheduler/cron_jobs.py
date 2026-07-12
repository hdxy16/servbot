import logging
import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import AsyncSessionLocal
from database.models import User, ClientProfile, CheckIn, Notification, TrainerClient

logger = logging.getLogger(__name__)

# Глобальний шедулер
scheduler = AsyncIOScheduler()


async def send_notification(user_id: int, text: str, notif_type: str):
    """Відправляє сповіщення користувачеві (зберігає в БД)."""
    async with AsyncSessionLocal() as session:
        notification = Notification(
            user_id=user_id,
            type=notif_type,
            text=text,
            scheduled_at=datetime.datetime.utcnow(),
            is_sent=False
        )
        session.add(notification)
        await session.commit()


async def check_checkin_reminders():
    """Перевіряє, хто з клієнтів має зробити чекін."""
    try:
        async with AsyncSessionLocal() as session:
            today = datetime.date.today()
            
            # Шукаємо клієнтів, у яких next_checkin <= today
            stmt = (
                select(User, ClientProfile)
                .join(ClientProfile, ClientProfile.user_id == User.id)
                .where(
                    ClientProfile.is_active == True,
                    ClientProfile.next_checkin <= today
                )
            )
            results = (await session.execute(stmt)).all()
            
            for user, profile in results:
                await send_notification(
                    user.id,
                    f"📋 Нагадування: час зробити чекін! Використайте команду /checkin",
                    "checkin"
                )
                # Оновлюємо наступний чекін
                profile.next_checkin = today + datetime.timedelta(days=7)
                await session.commit()
                
            if results:
                logger.info(f"Відправлено {len(results)} нагадувань про чекін")
    except Exception as e:
        logger.error(f"Error in check_checkin_reminders: {e}")


async def check_workout_reminders():
    """Нагадує про тренування (якщо клієнт не тренувався 3+ дні)."""
    try:
        async with AsyncSessionLocal() as session:
            three_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=3)
            
            # Отримуємо клієнтів без тренувань за останні 3 дні
            from database.models import WorkoutSession
            
            stmt = (
                select(User)
                .where(
                    User.is_client == True,
                    ~User.id.in_(
                        select(WorkoutSession.client_id)
                        .where(WorkoutSession.date >= three_days_ago)
                    )
                )
                .limit(50)
            )
            clients = (await session.execute(stmt)).scalars().all()
            
            for client in clients:
                await send_notification(
                    client.id,
                    "🏋️ Нагадування: давно ви не тренувались! Час зайнятися спортом 💪",
                    "workout"
                )
            
            if clients:
                logger.info(f"Відправлено {len(clients)} нагадувань про тренування")
    except Exception as e:
        logger.error(f"Error in check_workout_reminders: {e}")


async def send_trainer_weekly_report():
    """Щотижневий звіт для тренера."""
    try:
        async with AsyncSessionLocal() as session:
            # Отримуємо всіх тренерів
            stmt = select(User).where(User.is_trainer == True)
            trainers = (await session.execute(stmt)).scalars().all()
            
            week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
            
            for trainer in trainers:
                # Рахуємо кількість клієнтів
                client_count_stmt = select(CheckIn).join(
                    TrainerClient, TrainerClient.client_id == CheckIn.client_id
                ).where(
                    TrainerClient.trainer_id == trainer.id,
                    CheckIn.date >= week_ago.date()
                )
                checkins = (await session.execute(client_count_stmt)).scalars().all()
                
                report_text = (
                    f"📊 <b>Щотижневий звіт</b>\n\n"
                    f"За останній тиждень:\n"
                    f"• Чекінів: {len(checkins)}\n"
                    f"• Активних клієнтів: {len(set(c.client_id for c in checkins)) if checkins else 0}\n"
                    f"\nПродовжуйте хорошу роботу! 💪"
                )
                
                await send_notification(
                    trainer.id,
                    report_text,
                    "weekly_report"
                )
            
            if trainers:
                logger.info(f"Відправлено звіти для {len(trainers)} тренерів")
    except Exception as e:
        logger.error(f"Error in send_trainer_weekly_report: {e}")


def setup_scheduler():
    """Налаштовує та запускає шедулер."""
    # Перевірка чекінів щодня о 9:00
    scheduler.add_job(
        check_checkin_reminders,
        CronTrigger(hour=9, minute=0),
        id="checkin_reminders",
        replace_existing=True
    )
    
    # Нагадування про тренування щодня о 18:00
    scheduler.add_job(
        check_workout_reminders,
        CronTrigger(hour=18, minute=0),
        id="workout_reminders",
        replace_existing=True
    )
    
    # Щотижневий звіт для тренерів (понеділок 8:00)
    scheduler.add_job(
        send_trainer_weekly_report,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_report",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler успішно налаштовано та запущено")


def shutdown_scheduler():
    """Зупиняє шедулер."""
    scheduler.shutdown()
    logger.info("Scheduler зупинено")