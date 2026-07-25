import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.engine import init_db, AsyncSessionLocal

from bot.middlewares.auth import AuthMiddleware
from bot.handlers import base_router
from bot.services.food_service import init_default_products

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

async def startup_db_seed():
    """Сіялка бази даних при першому запуску"""
    async with AsyncSessionLocal() as session:
        await init_default_products(session)
        logger.info("База продуктів перевірена/завантажена.")

async def main():
    logger.info("Запуск GYM_BOT...")
    
    await init_db()
    await startup_db_seed()
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.update.middleware(AuthMiddleware())
    
    # Імпорт та підключення роутерів
    from bot.handlers.admin import admin_router
    from bot.handlers.trainer import trainer_router
    from bot.handlers.trainer_food import trainer_food_router
    from bot.handlers.client import client_router
    from bot.handlers.client_food import client_food_router
    from bot.handlers.checkin import client_checkin_router, trainer_checkin_router
    
    dp.include_router(base_router)
    dp.include_router(admin_router)
    dp.include_router(trainer_router)
    dp.include_router(trainer_food_router)
    dp.include_router(client_router)
    dp.include_router(client_food_router)
    dp.include_router(client_checkin_router)
    dp.include_router(trainer_checkin_router)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот успішно запущений і готовий до роботи (Polling).")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Бот зупинено.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Вихід з програми.")