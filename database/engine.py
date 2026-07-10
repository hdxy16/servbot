# FILE: database/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database.models import Base, User, CalendarEvent # Видалено зайві моделі

DATABASE_URL = "sqlite+aiosqlite:///finance.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)