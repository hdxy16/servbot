from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import (
    MeasurementLog,
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

    measurement = MeasurementLog(
        user_id=user_id,
        date=datetime.date.today(),
        weight=weight,
        chest=chest,
        waist=waist,
        hips=hips,
        arms=arms
    )

    session.add(measurement)

    await session.commit()

    return measurement



async def get_measurements(
    session: AsyncSession,
    user_id: int,
    limit=10
):

    result = await session.execute(
        select(MeasurementLog)
        .where(
            MeasurementLog.user_id == user_id
        )
        .order_by(
            desc(MeasurementLog.date)
        )
        .limit(limit)
    )

    return result.scalars().all()



async def add_progress_photo(
    session: AsyncSession,
    user_id: int,
    file_id: str,
    view: str
):

    photo = ProgressPhoto(
        user_id=user_id,
        date=datetime.date.today(),
        file_id=file_id,
        view=view
    )


    session.add(photo)

    await session.commit()

    return photo



async def get_progress_photos(
    session: AsyncSession,
    user_id: int
):

    result = await session.execute(
        select(ProgressPhoto)
        .where(
            ProgressPhoto.user_id == user_id
        )
        .order_by(
            desc(ProgressPhoto.date)
        )
    )

    return result.scalars().all()