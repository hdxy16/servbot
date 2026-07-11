# FILE: ./bot/sheets_sync.py
"""
Синхронізація тренувань з Google Sheets — резервна копія + відновлення
локальної бази, якщо finance.db загубиться.

Налаштування (одноразово):
1. Зайди на https://console.cloud.google.com/ → створи проєкт (або обери існуючий).
2. APIs & Services → Library → знайди "Google Sheets API" → Enable.
3. APIs & Services → Credentials → Create Credentials → Service Account.
   Дай будь-яке ім'я, права можна не додавати.
4. Відкрий створений Service Account → вкладка "Keys" → Add Key → Create new key → JSON.
   Файл завантажиться на комп'ютер.
5. Перейменуй його на google_creds.json і поклади в корінь проєкту на сервері
   (~/finance_bot/servbot/google_creds.json).
6. Створи нову Google Таблицю (sheets.google.com), скопіюй її ID з URL:
   https://docs.google.com/spreadsheets/d/ЦЕ_ОСЬ_ID/edit
7. У файлі google_creds.json знайди поле "client_email" (виглядає як
   xxx@xxx.iam.gserviceaccount.com) — це "пошта" сервісного акаунту.
8. Відкрий свою Google Таблицю → "Надати доступ" (Share) → встав ту пошту
   з кроку 7 → права "Редактор" (Editor).
9. В .env додай:
   GOOGLE_SHEETS_ID=ЦЕ_ОСЬ_ID_З_КРОКУ_6
   GOOGLE_SHEETS_CREDS_PATH=google_creds.json

Без цих двох змінних модуль просто мовчки вимикається (бот працює як раніше,
тільки без бекапу в Sheets) — це навмисно, щоб нічого не зламати, поки не
налаштуєш Google-частину.
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from config import GOOGLE_SHEETS_ID, GOOGLE_SHEETS_CREDS_PATH

SESSIONS_HEADER = ["session_id", "user_id", "day_key", "day_title", "started_at", "finished_at"]
SETS_HEADER = ["session_id", "exercise_key", "exercise_name", "set_number", "weight_kg", "reps", "logged_at"]

_client = None
_sheet = None
_disabled_reason: str | None = None


def _init_sync() -> bool:
    """Лінива ініціалізація клієнта. Повертає True, якщо синк реально доступний."""
    global _client, _sheet, _disabled_reason

    if _sheet is not None:
        return True
    if _disabled_reason is not None:
        return False

    if not GSPREAD_AVAILABLE:
        _disabled_reason = "бібліотека gspread не встановлена"
        logger.warning("Google Sheets sync вимкнено: %s", _disabled_reason)
        return False

    if not GOOGLE_SHEETS_ID or not GOOGLE_SHEETS_CREDS_PATH:
        _disabled_reason = "GOOGLE_SHEETS_ID/GOOGLE_SHEETS_CREDS_PATH не задані в .env"
        logger.warning("Google Sheets sync вимкнено: %s", _disabled_reason)
        return False

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDS_PATH, scopes=scopes)
        _client = gspread.authorize(creds)
        _sheet = _client.open_by_key(GOOGLE_SHEETS_ID)

        _ensure_worksheet("Sessions", SESSIONS_HEADER)
        _ensure_worksheet("Sets", SETS_HEADER)
        logger.info("Google Sheets sync успішно підключено.")
        return True
    except Exception as e:
        detail = str(e)
        response = getattr(e, "response", None)
        if response is not None:
            status = getattr(response, "status_code", "?")
            if status == 404:
                detail = "404 — таблицю з таким GOOGLE_SHEETS_ID не знайдено (перевір ID) або сервісний акаунт не має до неї доступу (перевір, чи розшарив таблицю на client_email)"
            elif status == 403:
                detail = "403 — немає прав доступу (переконайся, що таблицю розшарено на client_email з правами Editor)"
            else:
                try:
                    detail = f"{status} — {response.json().get('error', {}).get('message', str(e))}"
                except Exception:
                    detail = f"{status} — {e}"
        _disabled_reason = f"помилка підключення: {detail}"
        logger.error("Google Sheets sync вимкнено: %s", _disabled_reason)
        return False


def _ensure_worksheet(title: str, header: list[str]):
    try:
        ws = _sheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = _sheet.add_worksheet(title=title, rows=1000, cols=len(header) + 2)
        ws.append_row(header)
        return ws

    values = ws.row_values(1)
    if values != header:
        ws.update("A1", [header])
    return ws


def _sync_available() -> bool:
    return _init_sync()


# ==========================================
# ЗАПИС (виконується у фоновому потоці, щоб не гальмувати бота)
# ==========================================
def _append_set_sync(session_id: int, exercise_key: str, exercise_name: str, set_number: int, weight_kg: float, reps: int):
    ws = _sheet.worksheet("Sets")
    ws.append_row([
        session_id, exercise_key, exercise_name, set_number, weight_kg, reps,
        datetime.utcnow().isoformat(timespec="seconds"),
    ])


def _upsert_session_sync(session_id: int, user_id: int, day_key: str, day_title: str, started_at: datetime, finished_at: datetime | None):
    ws = _sheet.worksheet("Sessions")
    cell = ws.find(str(session_id), in_column=1)

    row = [
        session_id, user_id, day_key, day_title,
        started_at.isoformat(timespec="seconds"),
        finished_at.isoformat(timespec="seconds") if finished_at else "",
    ]

    if cell:
        ws.update(f"A{cell.row}:F{cell.row}", [row])
    else:
        ws.append_row(row)


async def sync_set_logged(session_id: int, exercise_key: str, exercise_name: str, set_number: int, weight_kg: float, reps: int):
    if not _sync_available():
        return
    try:
        await asyncio.to_thread(_append_set_sync, session_id, exercise_key, exercise_name, set_number, weight_kg, reps)
    except Exception as e:
        logger.error("Не вдалося записати підхід у Google Sheets: %s", e)


async def sync_session(session_id: int, user_id: int, day_key: str, day_title: str, started_at: datetime, finished_at: datetime | None):
    if not _sync_available():
        return
    try:
        await asyncio.to_thread(_upsert_session_sync, session_id, user_id, day_key, day_title, started_at, finished_at)
    except Exception as e:
        logger.error("Не вдалося записати тренування у Google Sheets: %s", e)


# ==========================================
# ВІДНОВЛЕННЯ З ТАБЛИЦІ
# ==========================================
def _fetch_all_sync() -> tuple[list[dict], list[dict]]:
    sessions_ws = _sheet.worksheet("Sessions")
    sets_ws = _sheet.worksheet("Sets")
    return sessions_ws.get_all_records(), sets_ws.get_all_records()


async def restore_from_sheets() -> tuple[list[dict], list[dict]] | None:
    """Повертає (sessions_rows, sets_rows) з Google Sheets, або None якщо синк недоступний."""
    if not _sync_available():
        return None
    try:
        return await asyncio.to_thread(_fetch_all_sync)
    except Exception as e:
        logger.error("Не вдалося прочитати дані з Google Sheets: %s", e)
        return None


def sync_status() -> str:
    if _sheet is not None:
        return "✅ Підключено"
    _init_sync()
    if _sheet is not None:
        return "✅ Підключено"

    import html
    safe_reason = html.escape(str(_disabled_reason or "не налаштовано"))
    return f"⚠️ Вимкнено ({safe_reason})"