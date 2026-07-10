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


class Base(DeclarativeBase):
    pass


# ============================================================
# USERS
# ============================================================

class User(Base):
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

    # Індекс наступного дня в ротації (0=Верх А, 1=Низ А, 2=Верх Б, 3=Низ Б)
    next_workout_index: Mapped[int] = mapped_column(Integer, default=0)


# ============================================================
# CALENDAR / ОСОБИСТИЙ ПЛАНЕР
# ============================================================

class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    event_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    is_notified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # --- ПЛАНЕР: щоденні нагадування + вечірнє підтвердження ---

    # Чи включати подію у щоденний ранковий дайджест-лічильник ("за N днів")
    daily_reminder: Mapped[bool] = mapped_column(Boolean, default=True)

    # Чи підтвердив користувач "я пам'ятаю" ввечері напередодні події
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Скільки разів вже надсилали вечірнє підтвердження (для ескалації тону)
    reminder_stage: Mapped[int] = mapped_column(Integer, default=0)

    # Час останнього надісланого вечірнього нагадування (щоб не дублювати в межах одного вікна)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Подія вже завершилась і прибрана з активних списків
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)


# ============================================================
# СПОРТЗАЛ
# ============================================================

class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)

    # "upper_a" / "lower_a" / "upper_b" / "lower_b"
    day_key: Mapped[str] = mapped_column(String, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("workout_sessions.id"), index=True, nullable=False)

    exercise_key: Mapped[str] = mapped_column(String, nullable=False)
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)

    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)