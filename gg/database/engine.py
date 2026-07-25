import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from config import DB_URL

logger = logging.getLogger(__name__)

# Створюємо асинхронний двигун
engine = create_async_engine(DB_URL, echo=False, future=True)

# Увімкнення Foreign Keys для SQLite
@event.listens_for(engine.sync_engine, "connect")
def enable_sqlite_fks(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, 'cursor'):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Фабрика сесій
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def init_db():
    """Ініціалізація бази даних (створення таблиць)."""
    from database.models import Base
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)  # Розкоментувати для скидання БД
        await conn.run_sync(Base.metadata.create_all)
    logger.info("База даних успішно ініціалізована.")