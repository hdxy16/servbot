import pytest
import asyncio
import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base, User, ClientProfile, TrainerClient, NutritionPlan, FoodDay, FoodEntry, WorkoutProgram, WorkoutDay, WorkoutSession, WorkoutSet, CheckIn, Measurement


# Тестова база даних (SQLite in-memory)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def session():
    """Створює тестову сесію БД."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user(session):
    """Тест створення користувача."""
    user = User(
        telegram_id=123456789,
        username="test_user",
        full_name="Test User",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True,
        is_admin=False,
        is_trainer=False
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    
    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.full_name == "Test User"


@pytest.mark.asyncio
async def test_create_client_profile(session):
    """Тест створення профілю клієнта."""
    user = User(
        telegram_id=123456789,
        username="test_user",
        full_name="Test User",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(user)
    await session.flush()
    
    profile = ClientProfile(
        user_id=user.id,
        age=25,
        gender="male",
        height=180,
        start_weight=80.0,
        current_weight=78.0,
        goal="Схуднути",
        is_active=True
    )
    session.add(profile)
    await session.commit()
    
    assert profile.id is not None
    assert profile.user_id == user.id
    assert profile.age == 25
    assert profile.current_weight == 78.0


@pytest.mark.asyncio
async def test_create_trainer_client_relation(session):
    """Тест зв'язку тренер-клієнт."""
    trainer = User(
        telegram_id=111111,
        username="trainer",
        full_name="Trainer",
        roles=["TRAINER"],
        active_role="TRAINER",
        is_trainer=True
    )
    session.add(trainer)
    await session.flush()
    
    client = User(
        telegram_id=222222,
        username="client",
        full_name="Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(client)
    await session.flush()
    
    relation = TrainerClient(
        trainer_id=trainer.id,
        client_id=client.id,
        is_active=True
    )
    session.add(relation)
    await session.commit()
    
    assert relation.id is not None
    assert relation.trainer_id == trainer.id
    assert relation.client_id == client.id


@pytest.mark.asyncio
async def test_create_nutrition_plan(session):
    """Тест створення плану харчування."""
    client = User(
        telegram_id=123456789,
        full_name="Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(client)
    await session.flush()
    
    plan = NutritionPlan(
        client_id=client.id,
        protein_portions=3.0,
        carbs_portions=4.0,
        fats_portions=2.0,
        fruits_portions=2.0,
        anything_portions=1.0,
        vegetables_g=400,
        is_active=True,
        created_by=1,
        reason="Первинне налаштування"
    )
    session.add(plan)
    await session.commit()
    
    assert plan.id is not None
    assert plan.client_id == client.id
    assert plan.protein_portions == 3.0
    assert plan.vegetables_g == 400


@pytest.mark.asyncio
async def test_create_food_day_and_entry(session):
    """Тест створення дня харчування та запису."""
    client = User(
        telegram_id=123456789,
        full_name="Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(client)
    await session.flush()
    
    food_day = FoodDay(
        client_id=client.id,
        date=datetime.date.today(),
        is_closed=False,
        water_ml=1500
    )
    session.add(food_day)
    await session.flush()
    
    entry = FoodEntry(
        food_day_id=food_day.id,
        category="protein",
        product_name="Курка",
        amount=150.0,
        portions=1.5
    )
    session.add(entry)
    await session.commit()
    
    assert food_day.id is not None
    assert entry.id is not None
    assert entry.product_name == "Курка"


@pytest.mark.asyncio
async def test_create_workout(session):
    """Тест створення тренування."""
    trainer = User(
        telegram_id=111111,
        full_name="Trainer",
        roles=["TRAINER"],
        active_role="TRAINER",
        is_trainer=True
    )
    session.add(trainer)
    await session.flush()
    
    program = WorkoutProgram(
        trainer_id=trainer.id,
        name="Програма 1",
        description="Базове тренування"
    )
    session.add(program)
    await session.flush()
    
    day = WorkoutDay(
        program_id=program.id,
        name="День 1: Верх",
        order=1
    )
    session.add(day)
    await session.commit()
    
    assert program.id is not None
    assert day.id is not None
    assert program.name == "Програма 1"


@pytest.mark.asyncio
async def test_create_checkin(session):
    """Тест створення чекіну."""
    client = User(
        telegram_id=123456789,
        full_name="Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(client)
    await session.flush()
    
    checkin = CheckIn(
        client_id=client.id,
        date=datetime.date.today(),
        sleep=4,
        energy=3,
        hunger=2,
        stress=1,
        feeling="Добре"
    )
    session.add(checkin)
    await session.commit()
    
    assert checkin.id is not None
    assert checkin.client_id == client.id
    assert checkin.sleep == 4
    assert checkin.feeling == "Добре"


@pytest.mark.asyncio
async def test_create_measurement(session):
    """Тест створення заміру."""
    client = User(
        telegram_id=123456789,
        full_name="Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(client)
    await session.flush()
    
    measurement = Measurement(
        client_id=client.id,
        date=datetime.date.today(),
        weight=75.5,
        waist=80.0,
        chest=100.0
    )
    session.add(measurement)
    await session.commit()
    
    assert measurement.id is not None
    assert measurement.weight == 75.5