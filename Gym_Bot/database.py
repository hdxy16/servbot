# Gym_Bot/database.py
import datetime
from sqlalchemy import select, ForeignKey, String, Integer, Float, Boolean, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="client")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    
    # Гейміфікація стріків дисципліни
    streak: Mapped[int] = mapped_column(Integer, default=0)
    last_closed_date: Mapped[str] = mapped_column(String, nullable=True)
    
    # Кастомний час щоденного звіту (тільки для тренерів)
    digest_time: Mapped[str] = mapped_column(String, default="21:00")
    last_digest_date: Mapped[str] = mapped_column(String, nullable=True)
    
    targets: Mapped["ClientTarget"] = relationship("ClientTarget", back_populates="user", cascade="all, delete-orphan")
    entries: Mapped[list["FoodEntry"]] = relationship("FoodEntry", back_populates="user", cascade="all, delete-orphan")

class ClientTarget(Base):
    __tablename__ = "client_targets"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    protein_target: Mapped[float] = mapped_column(Float, default=3.5)
    carbs_target: Mapped[float] = mapped_column(Float, default=3.0)
    fats_target: Mapped[float] = mapped_column(Float, default=3.0)
    fruits_target: Mapped[float] = mapped_column(Float, default=1.0)
    veggies_target: Mapped[float] = mapped_column(Float, default=400.0)
    
    user: Mapped["User"] = relationship("User", back_populates="targets")

class FoodEntry(Base):
    __tablename__ = "food_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    product_name: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    portions: Mapped[float] = mapped_column(Float)
    
    user: Mapped["User"] = relationship("User", back_populates="entries")

class InviteToken(Base):
    __tablename__ = "invite_tokens"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class FoodProduct(Base):
    __tablename__ = "food_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    size: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="г")

# ТАБЛИЦЯ ОБЛІКУ ВАГИ (ІДЕЯ 3)
class WeightLog(Base):
    __tablename__ = "weight_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True) # YYYY-MM-DD
    weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

# ТАБЛИЦЯ ФІКСАЦІЇ ЗАКРИТТЯ ДНІВ (ІДЕЯ 4)
class DayClosure(Base):
    __tablename__ = "day_closures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    closed_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        prod_check = await session.execute(select(FoodProduct).limit(1))
        if not prod_check.scalar_one_or_none():
            from config import FOOD_CATALOG
            print("🗄️ Виявлено порожню таблицю продуктів. Запускаю міграцію повного базового раціону...")
            for cat_key, cat_data in FOOD_CATALOG.items():
                for p_name, p_info in cat_data["items"].items():
                    session.add(FoodProduct(
                        category=cat_key,
                        name=p_name,
                        size=p_info["size"],
                        unit=p_info["unit"]
                    ))
            await session.commit()
            print("✅ Еталонний раціон успішно перенесено в базу!")