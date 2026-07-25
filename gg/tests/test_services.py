import pytest
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from database.models import Base, User, ClientProfile
from bot.services.client_service import get_trainer_clients, get_client_by_id, update_client_profile
from bot.services.nutrition_service import get_active_plan, create_plan
from bot.services.food_service import get_or_create_food_day, add_food_entry, calculate_progress
from bot.services.workout_service import create_program, create_day, add_exercise_to_day, get_program_days


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


@pytest.fixture
async def test_client(session):
    """Створює тестового клієнта."""
    user = User(
        telegram_id=123456789,
        username="test_client",
        full_name="Test Client",
        roles=["CLIENT"],
        active_role="CLIENT",
        is_client=True
    )
    session.add(user)
    await session.flush()
    
    profile = ClientProfile(
        user_id=user.id,
        age=25,
        start_weight=80.0,
        current_weight=78.0
    )
    session.add(profile)
    await session.commit()
    await session.refresh(user)
    
    return user


@pytest.fixture
async def test_trainer(session):
    """Створює тестового тренера."""
    trainer = User(
        telegram_id=111111,
        username="test_trainer",
        full_name="Test Trainer",
        roles=["TRAINER"],
        active_role="TRAINER",
        is_trainer=True
    )
    session.add(trainer)
    await session.commit()
    await session.refresh(trainer)
    return trainer


@pytest.mark.asyncio
async def test_get_client_by_id(session, test_client):
    """Тест отримання клієнта за ID."""
    result = await get_client_by_id(session, test_client.id)
    assert result is not None
    user, profile = result
    assert user.id == test_client.id
    assert profile.user_id == test_client.id


@pytest.mark.asyncio
async def test_update_client_profile(session, test_client):
    """Тест оновлення профілю клієнта."""
    old_val, new_val = await update_client_profile(
        session,
        test_client.id,
        "current_weight",
        76.5
    )
    assert old_val == 78.0
    assert new_val == 76.5
    
    # Перевіряємо, що зміна збереглася
    result = await get_client_by_id(session, test_client.id)
    assert result is not None
    _, profile = result
    assert profile.current_weight == 76.5


@pytest.mark.asyncio
async def test_create_nutrition_plan(session, test_client):
    """Тест створення плану харчування."""
    plan = await create_plan(
        session,
        test_client.id,
        1,  # created_by
        protein=3.0,
        carbs=4.0,
        fats=2.0,
        fruits=2.0,
        anything=1.0,
        veggies_g=400,
        reason="Тестовий план"
    )
    
    assert plan is not None
    assert plan.client_id == test_client.id
    assert plan.protein_portions == 3.0
    assert plan.is_active is True


@pytest.mark.asyncio
async def test_get_active_plan(session, test_client):
    """Тест отримання активного плану."""
    # Створюємо план
    await create_plan(
        session,
        test_client.id,
        1,
        protein=3.0,
        carbs=4.0,
        fats=2.0,
        fruits=2.0,
        anything=1.0,
        veggies_g=400
    )
    
    # Отримуємо активний план
    plan = await get_active_plan(session, test_client.id)
    assert plan is not None
    assert plan.is_active is True


@pytest.mark.asyncio
async def test_food_day_operations(session, test_client):
    """Тест операцій з днями харчування."""
    today = datetime.date.today()
    
    # Створюємо день
    food_day = await get_or_create_food_day(session, test_client.id, today)
    assert food_day is not None
    assert food_day.client_id == test_client.id
    
    # Додаємо запис
    entry = await add_food_entry(
        session,
        test_client.id,
        today,
        product_id=None,
        category="protein",
        custom_name="Курка",
        amount=150.0,
        portions=1.5
    )
    assert entry is not None
    assert entry.product_name == "Курка"
    
    # Рахуємо прогрес
    progress = await calculate_progress(session, test_client.id, today)
    assert progress["protein"] == 1.5


@pytest.mark.asyncio
async def test_workout_operations(session, test_trainer):
    """Тест операцій з тренуваннями."""
    # Створюємо програму
    program = await create_program(
        session,
        test_trainer.id,
        "Тестова програма",
        "Опис"
    )
    assert program is not None
    assert program.name == "Тестова програма"
    
    # Створюємо день
    day = await create_day(
        session,
        program.id,
        "День 1",
        1
    )
    assert day is not None
    assert day.name == "День 1"
    
    # Отримуємо дні програми
    days = await get_program_days(session, program.id)
    assert len(days) == 1
    assert days[0].name == "День 1"


@pytest.mark.asyncio
async def test_multiple_nutrition_plans(session, test_client):
    """Тест, що при створенні нового плану старий деактивується."""
    # Створюємо перший план
    plan1 = await create_plan(
        session,
        test_client.id,
        1,
        protein=2.0,
        carbs=3.0,
        fats=1.0,
        fruits=1.0,
        anything=0.5,
        veggies_g=300
    )
    assert plan1.is_active is True
    
    # Створюємо другий план
    plan2 = await create_plan(
        session,
        test_client.id,
        1,
        protein=4.0,
        carbs=5.0,
        fats=3.0,
        fruits=3.0,
        anything=2.0,
        veggies_g=500
    )
    assert plan2.is_active is True
    
    # Перевіряємо, що перший план деактивовано
    await session.refresh(plan1)
    assert plan1.is_active is False


@pytest.mark.asyncio
async def test_get_trainer_clients_empty(session, test_trainer):
    """Тест отримання порожнього списку клієнтів тренера."""
    clients, total_pages = await get_trainer_clients(session, test_trainer.id)
    assert len(clients) == 0
    assert total_pages == 1