import datetime
from sqlalchemy import select, event, ForeignKey, String, Integer, Float, Boolean, Text, JSON, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# ==================== ПІДКАТЕГОРІЇ ====================
SUBCATEGORIES = {
    "protein": {
        "🐔 Птиця": ["куряче", "стегно", "індичка", "філе"],
        "🥩 М'ясо": ["телятина", "свинина", "печінка", "яловича"],
        "🐟 Риба": ["хек", "мінтай", "тріска", "судак", "пікша", "окунь", "щука", "тілапія", "тунець", "лосось", "форель", "скумбрія", "оселедець", "сардина"],
        "🦐 Морепродукти": ["креветки", "мідії", "восьминіг"],
        "🥚 Яйця/Молочка": ["яйця", "сир", "йогурт", "кефір", "молоко"],
    },
    "carbs": {
        "🍚 Крупи": ["рис", "гречка", "булгур", "кус-кус", "перловка", "ячна", "пшоняна", "вівсяні", "кукурудзяна", "манка", "кіноа"],
        "🍝 Макарони/Хліб": ["макарони", "локшина", "лаваш", "хліб", "хлібці"],
        "🥔 Овочі/Бобові": ["картопля", "батат", "кукурудза", "квасоля", "нут", "горох", "сочевиця"],
    },
    "fats": {
        "🫒 Олії/Соуси": ["олія", "майонез", "кетчуп"],
        "🥑 Авокадо/Оливки": ["авокадо", "маслини", "оливки"],
        "🥜 Горіхи/Насіння": ["горіхи", "арахісова", "тахіні"],
    },
    "fruits": {
        "🍎 Фрукти та ягоди": ["фрукти", "банан", "манго", "хурма", "виноград", "фініки", "ягоди"],
    },
}

def get_subcategory_for_product(category: str, name: str) -> str | None:
    if category not in SUBCATEGORIES:
        return None
    name_lower = name.lower()
    for sub_key, keywords in SUBCATEGORIES[category].items():
        for kw in keywords:
            if kw in name_lower:
                return sub_key
    return None

# ==================== КЛАСИ БД ====================

@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="client")
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)

    target: Mapped["ClientTarget"] = relationship("ClientTarget", back_populates="user", cascade="all, delete-orphan", uselist=False)
    entries: Mapped[list["FoodEntry"]] = relationship("FoodEntry", back_populates="user", cascade="all, delete-orphan")
    food_days: Mapped[list["FoodDay"]] = relationship("FoodDay", back_populates="user", cascade="all, delete-orphan")
    weights: Mapped[list["WeightEntry"]] = relationship("WeightEntry", back_populates="user", cascade="all, delete-orphan")

class ClientTarget(Base):
    __tablename__ = "client_targets"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    protein_target: Mapped[float] = mapped_column(Float, default=4.0)
    carbs_target: Mapped[float] = mapped_column(Float, default=4.0)
    fats_target: Mapped[float] = mapped_column(Float, default=3.0)
    fruits_target: Mapped[float] = mapped_column(Float, default=2.0)
    veggies_target: Mapped[float] = mapped_column(Float, default=1.0)
    other_target: Mapped[float] = mapped_column(Float, default=2.0)
    custom_instruction: Mapped[str] = mapped_column(Text, nullable=True)
    trainer_notes: Mapped[str] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="target")

class FoodEntry(Base):
    __tablename__ = "food_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    product_name: Mapped[str] = mapped_column(String)
    amount: Mapped[float] = mapped_column(Float)
    portions: Mapped[float] = mapped_column(Float)
    time_added: Mapped[str] = mapped_column(String, default=lambda: datetime.datetime.now().strftime("%H:%M"))

    user: Mapped["User"] = relationship("User", back_populates="entries")

class FoodDay(Base):
    __tablename__ = "food_days"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    
    steps: Mapped[int] = mapped_column(Integer, default=0)
    workout_done: Mapped[bool] = mapped_column(Boolean, default=False)
    wellbeing: Mapped[int] = mapped_column(Integer, default=0)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    
    swap_protein: Mapped[float] = mapped_column(Float, default=0.0)
    swap_carbs: Mapped[float] = mapped_column(Float, default=0.0)
    swap_fats: Mapped[float] = mapped_column(Float, default=0.0)
    swap_fruits: Mapped[float] = mapped_column(Float, default=0.0)
    swap_veggies: Mapped[float] = mapped_column(Float, default=0.0)
    swap_other: Mapped[float] = mapped_column(Float, default=0.0)
    
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship("User", back_populates="food_days")

class ClientMeal(Base):
    __tablename__ = "client_meals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    components: Mapped[list] = mapped_column(JSON)

    user: Mapped["User"] = relationship("User")

class InviteToken(Base):
    __tablename__ = "invite_tokens"
    token: Mapped[str] = mapped_column(String, primary_key=True)
    is_used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)

class FoodProduct(Base):
    __tablename__ = "food_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String, index=True)
    subcategory: Mapped[str] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    size: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="г")

class BotSettings(Base):
    __tablename__ = "bot_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instruction_text: Mapped[str] = mapped_column(Text)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)

class WeightEntry(Base):
    __tablename__ = "weight_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)
    weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)
    note: Mapped[str] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="weights")

# ==================== МОДЕЛІ ДЛЯ ТРЕНУВАНЬ ====================

class Exercise(Base):
    __tablename__ = "exercises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    muscle_group: Mapped[str] = mapped_column(String, nullable=True)
    emoji: Mapped[str] = mapped_column(String, default="🏋️")
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    is_template: Mapped[bool] = mapped_column(Boolean, default=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)


class PlanExercise(Base):
    __tablename__ = "plan_exercises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_plans.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id", ondelete="CASCADE"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    sets: Mapped[int] = mapped_column(Integer, default=3)
    reps_min: Mapped[int] = mapped_column(Integer, default=8)
    reps_max: Mapped[int] = mapped_column(Integer, default=12)
    weight_step: Mapped[float] = mapped_column(Float, default=2.5)
    start_weight: Mapped[float] = mapped_column(Float, nullable=True)
    technical_tip: Mapped[dict] = mapped_column(JSON, nullable=True)


class AssignedPlan(Base):
    __tablename__ = "assigned_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_plans.id", ondelete="CASCADE"))
    assigned_date: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    current_day: Mapped[int] = mapped_column(Integer, default=1)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_plans.id", ondelete="CASCADE"))
    date: Mapped[str] = mapped_column(String, index=True)
    start_time: Mapped[str] = mapped_column(String, nullable=True)
    end_time: Mapped[str] = mapped_column(String, nullable=True)
    total_volume: Mapped[float] = mapped_column(Float, default=0.0)
    total_sets: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(default=datetime.datetime.utcnow)


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_sessions.id", ondelete="CASCADE"))
    plan_exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("plan_exercises.id", ondelete="CASCADE"))
    set_number: Mapped[int] = mapped_column(Integer)
    weight: Mapped[float] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        result = await conn.execute(text("PRAGMA table_info(food_products)"))
        columns = [row[1] for row in result.fetchall()]
        if 'subcategory' not in columns:
            await conn.execute(text("ALTER TABLE food_products ADD COLUMN subcategory VARCHAR"))
            print("✅ Додано колонку subcategory до таблиці food_products")

        result2 = await conn.execute(text("PRAGMA table_info(client_targets)"))
        cols2 = [row[1] for row in result2.fetchall()]
        if 'trainer_notes' not in cols2:
            await conn.execute(text("ALTER TABLE client_targets ADD COLUMN trainer_notes TEXT"))
            print("✅ Додано колонку trainer_notes до таблиці client_targets")

        result3 = await conn.execute(text("PRAGMA table_info(bot_settings)"))
        cols3 = [row[1] for row in result3.fetchall()]
        if 'maintenance_mode' not in cols3:
            await conn.execute(text("ALTER TABLE bot_settings ADD COLUMN maintenance_mode BOOLEAN DEFAULT 0"))
            print("✅ Додано колонку maintenance_mode до таблиці bot_settings")

    async with AsyncSessionLocal() as session:
        settings_check = await session.execute(select(BotSettings).limit(1))
        if not settings_check.scalar_one_or_none():
            from config import DEFAULT_INSTRUCTION
            session.add(BotSettings(instruction_text=DEFAULT_INSTRUCTION))

        prod_check = await session.execute(select(FoodProduct).limit(1))
        if not prod_check.scalar_one_or_none():
            from config import FOOD_CATALOG
            print("🗄️ Порожня база продуктів — завантажую еталонний каталог...")
            for cat_key, cat_data in FOOD_CATALOG.items():
                for p_name, p_info in cat_data["items"].items():
                    sub = get_subcategory_for_product(cat_key, p_name)
                    session.add(FoodProduct(
                        category=cat_key,
                        name=p_name,
                        size=p_info["size"],
                        unit=p_info["unit"],
                        subcategory=sub
                    ))
            await session.commit()
            print("✅ Каталог продуктів завантажено з підкатегоріями!")
        else:
            products_without_sub = (await session.execute(
                select(FoodProduct).where(FoodProduct.subcategory.is_(None))
            )).scalars().all()
            if products_without_sub:
                print("🔄 Призначаємо підкатегорії для існуючих продуктів...")
                for product in products_without_sub:
                    sub = get_subcategory_for_product(product.category, product.name)
                    if sub:
                        product.subcategory = sub
                await session.commit()
                print("✅ Підкатегорії призначено.")
            await session.commit()