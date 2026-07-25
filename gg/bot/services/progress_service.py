from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import (
    Measurement,
    ProgressPhoto,
    User
)

import datetime


async def add_measurement(
    session: AsyncSession,
    user_id: int,
    weight=None,
    chest=None,
    waist=None,
    hips=None,
    arms=None
):
    """Додає новий замір для клієнта."""
    try:
        measurement = Measurement(
            client_id=user_id,
            date=datetime.date.today(),
            weight=weight,
            chest=chest,
            waist=waist,
            hips=hips,
            arms=arms
        )
        
        session.add(measurement)
        await session.commit()
        await session.refresh(measurement)
        return measurement
    except Exception as e:
        await session.rollback()
        raise e


async def get_measurements(
    session: AsyncSession,
    user_id: int,
    limit=10
):
    """Отримує останні заміри клієнта."""
    try:
        result = await session.execute(
            select(Measurement)
            .where(
                Measurement.client_id == user_id
            )
            .order_by(
                desc(Measurement.date)
            )
            .limit(limit)
        )
        return result.scalars().all()
    except Exception as e:
        await session.rollback()
        raise e


async def add_progress_photo(
    session: AsyncSession,
    user_id: int,
    file_id: str,
    view: str
):
    """Додає фото прогресу."""
    try:
        photo = ProgressPhoto(
            client_id=user_id,
            date=datetime.date.today(),
            file_id=file_id,
            type=view
        )
        
        session.add(photo)
        await session.commit()
        await session.refresh(photo)
        return photo
    except Exception as e:
        await session.rollback()
        raise e


async def get_progress_photos(
    session: AsyncSession,
    user_id: int
):
    """Отримує всі фото прогресу клієнта."""
    try:
        result = await session.execute(
            select(ProgressPhoto)
            .where(
                ProgressPhoto.client_id == user_id
            )
            .order_by(
                desc(ProgressPhoto.date)
            )
        )
        return result.scalars().all()
    except Exception as e:
        await session.rollback()
        raise e


async def get_latest_measurement(
    session: AsyncSession,
    user_id: int
):
    """Отримує останній замір клієнта."""
    try:
        result = await session.execute(
            select(Measurement)
            .where(
                Measurement.client_id == user_id
            )
            .order_by(
                desc(Measurement.date)
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        await session.rollback()
        raise e