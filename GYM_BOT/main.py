import os
import sys
import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, Any, Awaitable
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import ErrorEvent, TelegramObject, Message, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func
from handlers_gym import router as gym_router

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db, AsyncSessionLocal, User, FoodDay, FoodEntry, BotSettings
from handlers_trainer import router as trainer_router
from handlers_client import router as client_router, is_trainer

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user and not is_trainer(user.id):
            async with AsyncSessionLocal() as session:
                settings = (await session.execute(select(BotSettings).limit(1))).scalars().first()

            if settings and settings.maintenance_mode:
                text = "🛠 <b>Бот тимчасово не працює, очікуйте на сповіщення.</b>\nВибачте за незручності!"
                if isinstance(event, Message):
                    await event.answer(text, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🛠 Бот тимчасово не працює.", show_alert=True)
                return

        return await handler(event, data)


async def smart_nudge(bot: Bot):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client"))).scalars().all()
        for client in clients:
            entry_count = (await session.execute(
                select(func.count(FoodEntry.id)).where(FoodEntry.user_id == client.id, FoodEntry.date == today)
            )).scalar()
            if entry_count == 0:
                try:
                    await bot.send_message(
                        client.telegram_id,
                        "👋 <b>Привіт!</b>\nЩось твій щоденник сьогодні порожній. Не забудь зафіксувати свій обід чи перекус 😉",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


async def remind_close_day(bot: Bot):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client"))).scalars().all()
        for client in clients:
            food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == client.id, FoodDay.date == today))).scalars().first()
            if not food_day or not food_day.is_closed:
                try:
                    await bot.send_message(
                        client.telegram_id,
                        "🔔 <b>Час закривати день!</b>\nНе забудьте внести останні прийоми їжі та натиснути '🔒 Закрити день (Звіт)' у меню раціону.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


async def auto_close_unclosed_days(bot: Bot):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        clients = (await session.execute(select(User).where(User.role == "client"))).scalars().all()
        for client in clients:
            food_day = (await session.execute(select(FoodDay).where(FoodDay.user_id == client.id, FoodDay.date == today))).scalars().first()
            if not food_day:
                food_day = FoodDay(user_id=client.id, date=today, is_closed=True)
                session.add(food_day)
            elif not food_day.is_closed:
                food_day.is_closed = True
        await session.commit()
    logger.info("Автоматичне закриття днів завершено.")


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    client_router.message.outer_middleware(MaintenanceMiddleware())
    client_router.callback_query.outer_middleware(MaintenanceMiddleware())

    dp.include_router(trainer_router)
    dp.include_router(client_router)
    dp.include_router(gym_router)  # <--- ДОДАНО

    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(smart_nudge, 'cron', hour=16, minute=0, args=[bot])
    scheduler.add_job(remind_close_day, 'cron', hour=21, minute=0, args=[bot])
    scheduler.add_job(auto_close_unclosed_days, 'cron', hour=23, minute=59, args=[bot])
    scheduler.start()

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        logger.error("Необроблена помилка під час обробки update: %s", event.exception, exc_info=True)
        return True

    logger.info("Gym_Bot успішно запустився разом із розумними планувальниками завдань (APScheduler)!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Роботу завершено.")