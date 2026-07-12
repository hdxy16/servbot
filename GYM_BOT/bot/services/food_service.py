import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import FoodDay, FoodEntry, FoodProduct, FavoriteFood, RecentFoodHistory, FoodPhoto


async def get_or_create_food_day(session: AsyncSession, client_id: int, target_date: datetime.date) -> FoodDay:
    """Повертає або створює запис дня харчування."""
    try:
        stmt = select(FoodDay).where(FoodDay.client_id == client_id, FoodDay.date == target_date)
        food_day = (await session.execute(stmt)).scalar_one_or_none()
        
        if not food_day:
            food_day = FoodDay(client_id=client_id, date=target_date)
            session.add(food_day)
            await session.commit()
            await session.refresh(food_day)
        
        return food_day
    except Exception as e:
        await session.rollback()
        raise e


async def calculate_progress(session: AsyncSession, client_id: int, target_date: datetime.date) -> Dict[str, float]:
    """Рахує спожиті порції за конкретний день по категоріях."""
    try:
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
    except Exception as e:
        await session.rollback()
        raise e


async def search_products(session: AsyncSession, category: str, query: str, limit: int = 5) -> List[FoodProduct]:
    """Шукає продукти у базі за категорією та назвою."""
    try:
        stmt = (
            select(FoodProduct)
            .where(FoodProduct.category == category, FoodProduct.name.ilike(f"%{query}%"))
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e


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
    try:
        food_day = await get_or_create_food_day(session, client_id, target_date)
        
        entry = FoodEntry(
            food_day_id=food_day.id,
            category=category,
            product_name=custom_name,
            amount=amount,
            portions=portions
        )
        session.add(entry)
        
        # Оновлення недавніх
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
        await session.refresh(entry)
        return entry
    except Exception as e:
        await session.rollback()
        raise e


async def add_food_photo(session: AsyncSession, client_id: int, target_date: datetime.date, file_id: str, comment: str) -> FoodPhoto:
    """Зберігає фото їжі."""
    try:
        food_day = await get_or_create_food_day(session, client_id, target_date)
        photo = FoodPhoto(
            client_id=client_id,
            food_day_id=food_day.id,
            file_id=file_id,
            comment=comment
        )
        session.add(photo)
        await session.commit()
        await session.refresh(photo)
        return photo
    except Exception as e:
        await session.rollback()
        raise e


async def get_day_entries(session: AsyncSession, client_id: int, target_date: datetime.date) -> List[FoodEntry]:
    """Отримує всі записи харчування за день."""
    try:
        food_day = await get_or_create_food_day(session, client_id, target_date)
        stmt = select(FoodEntry).where(FoodEntry.food_day_id == food_day.id).order_by(FoodEntry.created_at)
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e