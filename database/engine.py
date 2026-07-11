# FILE: ./database/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import UsersBase, CalendarBase, GymBase

# Три окремі файли замість одного finance.db.
# Видалення одного файлу більше не чіпає інші два.
users_engine = create_async_engine("sqlite+aiosqlite:///users.db")
calendar_engine = create_async_engine("sqlite+aiosqlite:///calendar.db")
gym_engine = create_async_engine("sqlite+aiosqlite:///gym.db")

UsersSessionLocal = async_sessionmaker(users_engine, expire_on_commit=False)
CalendarSessionLocal = async_sessionmaker(calendar_engine, expire_on_commit=False)
GymSessionLocal = async_sessionmaker(gym_engine, expire_on_commit=False)


async def init_db():
    async with users_engine.begin() as conn:
        await conn.run_sync(UsersBase.metadata.create_all)
    async with calendar_engine.begin() as conn:
        await conn.run_sync(CalendarBase.metadata.create_all)
    async with gym_engine.begin() as conn:
        await conn.run_sync(GymBase.metadata.create_all)