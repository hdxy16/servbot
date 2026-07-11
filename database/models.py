# FILE: ./database/models.py
from datetime import datetime

from sqlalchemy import (
    String,
    DateTime,
    BigInteger,
    Boolean,
    Integer,
    Float,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ============================================================
# ТРИ ОКРЕМІ БАЗИ — кожна відповідає за свій файл БД.
# Так видалення одного файлу (наприклад, gym.db) не чіпає інших.
# ============================================================

class UsersBase(DeclarativeBase):
    pass


class CalendarBase(DeclarativeBase):
    pass


class GymBase(DeclarativeBase):
    pass


# ============================================================
# users.db — користувачі, ролі, права доступу
# ============================================================

class User(UsersBase):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)

    role: Mapped[str] = mapped_column(String, default="guest")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    notify_finance: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_calendar: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_climate: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_network: Mapped[bool] = mapped_column(Boolean, default=True)

    permissions: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "finance": False,
            "calendar": False,
            "ha_light": False,
            "ha_climate": False,
            "ha_alarm": False,
            "bus": False,
            "wifi": False,
            "gym": False,
        },
    )

    next_workout_index: Mapped[int] = mapped_column(Integer, default=0)


# ============================================================
# calendar.db — особистий планер
# ============================================================

class CalendarEvent(CalendarBase):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    daily_reminder: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # UID події в iCloud Calendar (CalDAV). NULL, якщо подія ще не
    # синхронізована або прийшла з iCloud і локально ще не позначена.
    icloud_uid: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    # Джерело події: "bot" (створена в Telegram) або "icloud" (імпортована з iPhone)
    source: Mapped[str] = mapped_column(String, default="bot")


# ============================================================
# gym.db — спортзал
# ============================================================

class WorkoutSession(GymBase):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    day_key: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkoutSet(GymBase):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("workout_sessions.id"), index=True, nullable=False)
    exercise_key: Mapped[str] = mapped_column(String, nullable=False)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)