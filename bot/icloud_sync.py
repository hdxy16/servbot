# FILE: ./bot/icloud_sync.py
"""
Двостороння синхронізація календаря бота з Apple iCloud Calendar (CalDAV).

Навіщо: якщо calendar.db на сервері раптом загубиться (видалив вручну,
переїзд на новий сервер) — усі події, що бот вже встиг запушити в iCloud,
підтягнуться назад автоматично при наступному циклі синхронізації.
Плюс: події, додані прямо в застосунку "Календар" на iPhone, теж
потраплять в бота і отримають ті самі щоденні нагадування й вечірнє
підтвердження, що й події, створені через Telegram.

НАЛАШТУВАННЯ (одноразово):
1. Зайди на appleid.apple.com → увійди → "Пароль і безпека" →
   "Паролі для застосунків" → Створити пароль для застосунку.
   (Це НЕ твій звичайний Apple ID пароль — CalDAV з ним не працює,
   потрібен саме окремий App-Specific Password.)
2. У застосунку "Календар" на iPhone/Mac створи ОКРЕМИЙ календар,
   наприклад "Bot" (не використовуй основний "Home"/"Особисте" — так
   синхронізація буде ізольована і ти зможеш окремо вимкнути видимість
   цього календаря, якщо набридне).
3. В .env додай:
   ICLOUD_EMAIL=твоя_пошта@icloud.com
   ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   (той самий з кроку 1)
   ICLOUD_CALENDAR_NAME=Bot                   (назва з кроку 2)

Без цих змінних модуль просто вимикається — бот працює як раніше.
"""

import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import caldav
    from icalendar import Calendar as ICalendar, Event as IEvent
    CALDAV_AVAILABLE = True
except ImportError:
    CALDAV_AVAILABLE = False

from config import ICLOUD_EMAIL, ICLOUD_APP_PASSWORD, ICLOUD_CALENDAR_NAME

ICLOUD_URL = "https://caldav.icloud.com"

_calendar = None
_disabled_reason: str | None = None


def _init_sync():
    global _calendar, _disabled_reason

    if _calendar is not None:
        return _calendar
    if _disabled_reason is not None:
        return None

    if not CALDAV_AVAILABLE:
        _disabled_reason = "бібліотеки caldav/icalendar не встановлені"
        logger.warning("iCloud sync вимкнено: %s", _disabled_reason)
        return None

    if not ICLOUD_EMAIL or not ICLOUD_APP_PASSWORD:
        _disabled_reason = "ICLOUD_EMAIL/ICLOUD_APP_PASSWORD не задані в .env"
        logger.warning("iCloud sync вимкнено: %s", _disabled_reason)
        return None

    try:
        client = caldav.DAVClient(url=ICLOUD_URL, username=ICLOUD_EMAIL, password=ICLOUD_APP_PASSWORD)
        principal = client.principal()
        calendars = principal.calendars()

        target = next((c for c in calendars if c.name == ICLOUD_CALENDAR_NAME), None)
        if target is None:
            available = ", ".join(c.name for c in calendars)
            _disabled_reason = (
                f"календар '{ICLOUD_CALENDAR_NAME}' не знайдено в iCloud "
                f"(доступні: {available}). Створи його на iPhone в застосунку Календар."
            )
            logger.error("iCloud sync вимкнено: %s", _disabled_reason)
            return None

        _calendar = target
        logger.info("iCloud sync успішно підключено до календаря '%s'.", ICLOUD_CALENDAR_NAME)
        return _calendar
    except Exception as e:
        _disabled_reason = f"помилка підключення: {e}"
        logger.error("iCloud sync вимкнено: %s", _disabled_reason)
        return None


def _sync_ready() -> bool:
    return _init_sync() is not None


# ==========================================
# ПУШ: подія бота → iCloud
# ==========================================
def _push_event_sync(title: str, event_date: datetime) -> str | None:
    cal = _init_sync()
    if cal is None:
        return None

    ical = ICalendar()
    ical.add("prodid", "-//ServBot//UA")
    ical.add("version", "2.0")

    vevent = IEvent()
    vevent.add("summary", title)
    vevent.add("dtstart", event_date)
    vevent.add("dtend", event_date + timedelta(hours=1))
    vevent.add("dtstamp", datetime.utcnow())
    ical.add_component(vevent)

    created = cal.save_event(ical.to_ical().decode("utf-8"))
    return str(created.icalendar_component.get("uid"))


def _delete_event_sync(icloud_uid: str):
    cal = _init_sync()
    if cal is None:
        return
    try:
        event = cal.event_by_uid(icloud_uid)
        event.delete()
    except Exception:
        pass  # вже видалено чи не знайдено — нічого страшного


async def push_event(title: str, event_date: datetime) -> str | None:
    if not _sync_ready():
        return None
    try:
        return await asyncio.to_thread(_push_event_sync, title, event_date)
    except Exception as e:
        logger.error("Не вдалося запушити подію в iCloud: %s", e)
        return None


async def delete_event(icloud_uid: str):
    if not icloud_uid or not _sync_ready():
        return
    try:
        await asyncio.to_thread(_delete_event_sync, icloud_uid)
    except Exception as e:
        logger.error("Не вдалося видалити подію з iCloud: %s", e)


# ==========================================
# ПУЛ: нові події з iCloud (додані прямо на iPhone)
# ==========================================
def _pull_new_events_sync(known_uids: set[str], days_ahead: int) -> list[dict]:
    cal = _init_sync()
    if cal is None:
        return []

    start = datetime.utcnow()
    end = start + timedelta(days=days_ahead)
    events = cal.date_search(start=start, end=end)

    result = []
    for ev in events:
        vevent = ev.icalendar_component
        uid = str(vevent.get("uid"))
        if uid in known_uids:
            continue
        summary = str(vevent.get("summary", "Подія з iPhone"))
        dtstart = vevent.get("dtstart").dt
        if isinstance(dtstart, datetime):
            event_date = dtstart.replace(tzinfo=None)
        else:
            event_date = datetime.combine(dtstart, datetime.min.time())
        result.append({"uid": uid, "title": summary, "event_date": event_date})

    return result


async def pull_new_events(known_uids: set[str], days_ahead: int = 90) -> list[dict]:
    if not _sync_ready():
        return []
    try:
        return await asyncio.to_thread(_pull_new_events_sync, known_uids, days_ahead)
    except Exception as e:
        logger.error("Не вдалося прочитати нові події з iCloud: %s", e)
        return []


def sync_status() -> str:
    import html
    if _calendar is not None:
        return "✅ Підключено"
    _init_sync()
    if _calendar is not None:
        return "✅ Підключено"
    return f"⚠️ Вимкнено ({html.escape(str(_disabled_reason or 'не налаштовано'))})"