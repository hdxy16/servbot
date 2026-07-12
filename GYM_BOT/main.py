import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.engine import init_db
from bot.handlers.client import client_router
from bot.middlewares.auth import AuthMiddleware
from bot.handlers import base_router
from bot.handlers.trainer import trainer_router
from bot.handlers.trainer_food import trainer_food_router
from bot.handlers.trainer_gym import trainer_gym_router
from bot.handlers.client_food import client_food_router
from bot.handlers.client_gym import client_gym_router
from bot.handlers.checkin import client_checkin_router, trainer_checkin_router
from bot.handlers.progress import client_progress_router, trainer_progress_router
from bot.handlers.admin import admin_router

from scheduler.cron_jobs import setup_scheduler, shutdown_scheduler

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Запуск GYM_BOT...")
    
    # Ініціалізація бази даних
    await init_db()
    
    # Налаштування бота та диспетчера
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())
    
    # Підключення глобальних Middleware
    dp.update.middleware(AuthMiddleware())
    
    # Підключення роутерів (handlers)
    dp.include_router(base_router)
    dp.include_router(admin_router)
    dp.include_router(client_router)
    dp.include_router(trainer_router)
    dp.include_router(trainer_food_router)
    dp.include_router(trainer_gym_router)
    dp.include_router(client_food_router)
    dp.include_router(client_gym_router)
    dp.include_router(client_checkin_router)
    dp.include_router(trainer_checkin_router)
    dp.include_router(client_progress_router)
    dp.include_router(trainer_progress_router)
    
    # Запуск шедулера
    setup_scheduler()
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот успішно запущений і готовий до роботи (Polling).")
        await dp.start_polling(bot)
    finally:
        shutdown_scheduler()
        await bot.session.close()
        logger.info("Бот зупинено.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Вихід з програми.")
    except Exception as e:
        logger.error(f"Критична помилка: {e}")
        raise