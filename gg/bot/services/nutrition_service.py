import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import NutritionPlan

async def get_active_plan(session: AsyncSession, client_id: int) -> Optional[NutritionPlan]:
    """Повертає поточний активний план харчування клієнта."""
    stmt = (
        select(NutritionPlan)
        .where(NutritionPlan.client_id == client_id, NutritionPlan.is_active == True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()

async def get_plan_history(session: AsyncSession, client_id: int) -> List[NutritionPlan]:
    """Повертає всю історію планів клієнта."""
    stmt = (
        select(NutritionPlan)
        .where(NutritionPlan.client_id == client_id)
        .order_by(NutritionPlan.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

async def create_plan(
    session: AsyncSession, 
    client_id: int, 
    created_by: int, 
    protein: float, 
    carbs: float, 
    fats: float, 
    fruits: float, 
    anything: float, 
    veggies_g: int,
    reason: str = "Первинне налаштування"
) -> NutritionPlan:
    """Створює новий план харчування, деактивуючи всі попередні."""
    stmt = (
        update(NutritionPlan)
        .where(NutritionPlan.client_id == client_id, NutritionPlan.is_active == True)
        .values(is_active=False)
    )
    await session.execute(stmt)
    
    new_plan = NutritionPlan(
        client_id=client_id,
        protein_portions=protein,
        carbs_portions=carbs,
        fats_portions=fats,
        fruits_portions=fruits,
        anything_portions=anything,
        vegetables_g=veggies_g,
        is_active=True,
        created_by=created_by,
        reason=reason
    )
    session.add(new_plan)
    await session.commit()
    await session.refresh(new_plan)
    return new_plan