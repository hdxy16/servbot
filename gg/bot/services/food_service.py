import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import FoodDay, FoodEntry, FoodProduct, RecentFoodHistory, FoodPhoto
from bot.services.food_catalog import DEFAULT_FOOD_CATALOG

async def init_default_products(session: AsyncSession) -> None:
    """Заповнює базу даних продуктами при першому запуску."""
    stmt = select(func.count(FoodProduct.id))
    count = (await session.execute(stmt)).scalar()
    
    if count == 0:
        for item in DEFAULT_FOOD_CATALOG:
            product = FoodProduct(
                category=item["category"],
                name=item["name"],
                portion_size=item["portion_size"],
                unit=item["unit"]
            )
            session.add(product)
        await session.commit()

async def get_all_products_by_category(session: AsyncSession, category: str) -> List[FoodProduct]:
    """Повертає всі продукти з категорії."""
    stmt = select(FoodProduct).where(FoodProduct.category == category).order_by(FoodProduct.name)
    return list((await session.execute(stmt)).scalars().all())

async def add_custom_product(session: AsyncSession, category: str, name: str, portion_size: float, unit: str) -> FoodProduct:
    """Додає новий продукт тренером у загальну базу."""
    product = FoodProduct(category=category, name=name, portion_size=portion_size, unit=unit)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product

async def get_or_create_food_day(session: AsyncSession, client_id: int, target_date: datetime.date) -> FoodDay:
    """Повертає або створює запис дня харчування."""
    stmt = select(FoodDay).where(FoodDay.client_id == client_id, FoodDay.date == target_date)
    food_day = (await session.execute(stmt)).scalar_one_or_none()
    
    if not food_day:
        food_day = FoodDay(client_id=client_id, date=target_date)
        session.add(food_day)
        await session.commit()
        await session.refresh(food_day)
        
    return food_day

async def calculate_progress(session: AsyncSession, client_id: int, target_date: datetime.date) -> Dict[str, float]:
    """Рахує спожиті порції за конкретний день по категоріях."""
    food_day = await get_or_create_food_day(session, client_id, target_date)
    
    stmt = (
        select(FoodEntry.category, func.sum(FoodEntry.portions), func.sum(FoodEntry.amount))
        .where(FoodEntry.food_day_id == food_day.id)
        .group_by(FoodEntry.category)
    )
    results = (await session.execute(stmt)).all()
    
    progress = {
        "protein": 0.0, "carbs": 0.0, "fats": 0.0, 
        "fruits": 0.0, "anything": 0.0, "vegetable": 0.0
    }
    
    for category, portions, amount in results:
        if category == "vegetable":
            progress[category] = float(amount or 0.0)
        else:
            progress[category] = float(portions or 0.0)
            
    return progress

async def search_products(session: AsyncSession, category: str, query: str, limit: int = 10) -> List[FoodProduct]:
    """Шукає продукти у базі за категорією та назвою."""
    stmt = (
        select(FoodProduct)
        .where(FoodProduct.category == category, FoodProduct.name.ilike(f"%{query}%"))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())

async def add_food_entry(
    session: AsyncSession, 
    client_id: int, 
    target_date: datetime.date, 
    product_id: Optional[int], 
    category: str, 
    custom_name: str, 
    amount: float, 
    portions: float
) -> FoodEntry:
    """Додає запис про з'їдену їжу до щоденника."""
    food_day = await get_or_create_food_day(session, client_id, target_date)
    
    entry = FoodEntry(
        food_day_id=food_day.id,
        category=category,
        product_name=custom_name,
        amount=amount,
        portions=portions
    )
    session.add(entry)
    
    if product_id:
        stmt = select(RecentFoodHistory).where(
            RecentFoodHistory.client_id == client_id, 
            RecentFoodHistory.food_product_id == product_id
        )
        recent = (await session.execute(stmt)).scalar_one_or_none()
        if recent:
            recent.last_used_at = datetime.datetime.utcnow()
        else:
            session.add(RecentFoodHistory(client_id=client_id, food_product_id=product_id))
            
    await session.commit()
    return entry

async def add_food_photo(session: AsyncSession, client_id: int, target_date: datetime.date, file_id: str, comment: str) -> FoodPhoto:
    """Зберігає фото їжі."""
    food_day = await get_or_create_food_day(session, client_id, target_date)
    photo = FoodPhoto(
        client_id=client_id,
        food_day_id=food_day.id,
        file_id=file_id,
        comment=comment
    )
    session.add(photo)
    await session.commit()
    return photo

async def get_day_entries(session: AsyncSession, client_id: int, target_date: datetime.date) -> List[FoodEntry]:
    """Отримує всі записи харчування за день."""
    food_day = await get_or_create_food_day(session, client_id, target_date)
    stmt = select(FoodEntry).where(FoodEntry.food_day_id == food_day.id).order_by(FoodEntry.created_at)
    return list((await session.execute(stmt)).scalars().all())

async def get_recent_products(session: AsyncSession, client_id: int, category: str, limit: int = 5) -> List[FoodProduct]:
    """Отримує останні додані продукти клієнта в певній категорії."""
    stmt = (
        select(FoodProduct)
        .join(RecentFoodHistory, RecentFoodHistory.food_product_id == FoodProduct.id)
        .where(RecentFoodHistory.client_id == client_id, FoodProduct.category == category)
        .order_by(desc(RecentFoodHistory.last_used_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())