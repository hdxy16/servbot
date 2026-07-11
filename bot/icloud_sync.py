# FILE: ./bot/icloud_sync.py
"""
Двостороння синхронізація календаря бота з Apple iCloud Calendar (CalDAV).
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
        pass  # вже видалено чи не знайдено


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


# ==========================================
# ФОНОВА ЗАДАЧА ДЛЯ ПЛАНУВАЛЬНИКА (APSched)
# ==========================================
async def icloud_pull_sync():
    """
    Автоматична інтервальна задача, яка викликається з run.py.
    Забирає нові події з iCloud та реєструє їх у локальній базі.
    """
    if not _sync_ready():
        return

    from database.engine import CalendarSessionLocal
    from database.models import CalendarEvent
    from sqlalchemy import select
    from config import ALLOWED_USER_ID

    try:
        # 1. Отримуємо унікальні UID подій, які вже є в базі, щоб уникнути дублів
        async with CalendarSessionLocal() as session:
            stmt = select(CalendarEvent.icloud_uid).where(CalendarEvent.icloud_uid.isnot(None))
            existing_uids = set((await session.execute(stmt)).scalars().all())

        # 2. Стягуємо нові події з iCloud
        new_events = await pull_new_events(existing_uids)
        if not new_events:
            return

        # 3. Записуємо нові події в локальну базу даних календаря
        async with CalendarSessionLocal() as session:
            for ev in new_events:
                session.add(CalendarEvent(
                    user_id=ALLOWED_USER_ID,
                    title=ev["title"],
                    event_date=ev["event_date"],
                    icloud_uid=ev["uid"],
                    source="icloud",
                    daily_reminder=True,
                    confirmed=False,
                ))
            await session.commit()
            
        logger.info(f"🔄 Фонова синхронізація: успішно імпортовано {len(new_events)} подій з iCloud.")
    except Exception as e:
        logger.error(f"Помилка виконання автоматичного пулу iCloud: {e}")