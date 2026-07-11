import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не знайдено у файлі .env")

ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))
DB_URL = "sqlite+aiosqlite:///finance.db"

# Home Assistant конфігурація
HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

GUEST_PASSWORD = os.getenv("GUEST_PASSWORD", "090675090675")
ACTUAL_URL = os.getenv("ACTUAL_URL")
ACTUAL_PASSWORD = os.getenv("ACTUAL_PASSWORD")
ACTUAL_SYNC_ID = os.getenv("ACTUAL_SYNC_ID")
ACTUAL_ACCOUNT_NAME = os.getenv("ACTUAL_ACCOUNT_NAME", "Sparkasse")

# Fritz!Box конфігурація
FRITZ_IP = os.getenv("FRITZ_IP", "192.168.178.1")
FRITZ_USER = os.getenv("FRITZ_USER", "admin")
FRITZ_PASS = os.getenv("FRITZ_PASS")
WIFI_MAIN_SSID = os.getenv("WIFI_MAIN_SSID")
WIFI_MAIN_PASS = os.getenv("WIFI_MAIN_PASS")

# Google Sheets синхронізація тренувань (опційно)
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_SHEETS_CREDS_PATH = os.getenv("GOOGLE_SHEETS_CREDS_PATH", "google_creds.json")

# iCloud Calendar синхронізація (опційно)
ICLOUD_EMAIL = os.getenv("ICLOUD_EMAIL")
ICLOUD_APP_PASSWORD = os.getenv("ICLOUD_APP_PASSWORD")
ICLOUD_CALENDAR_NAME = os.getenv("ICLOUD_CALENDAR_NAME", "Bot")