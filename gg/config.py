import os
from pathlib import Path
from dotenv import load_dotenv

# Завантажуємо змінні з .env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///gym.db")
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", 0))

BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)