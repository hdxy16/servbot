import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.engine import init_db

from bot.middlewares.auth import AuthMiddleware
from bot.handlers import base_router

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
    # Наступні роутери будуть додаватись сюди:
    # dp.include_router(admin.router)
    # dp.include_router(trainer.router)
    # dp.include_router(client_food.router)
    # dp.include_router(client_training.router)
    
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