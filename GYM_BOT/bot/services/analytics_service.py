from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database.models import (
    User,
    MeasurementLog,
    WorkoutSession,
    FoodDay
)

import datetime


async def get_client_full_analytics(
        session: AsyncSession,
        client_id:int
):

    user = await session.get(User, client_id)


    measurements = await session.execute(
        select(MeasurementLog)
        .where(
            MeasurementLog.user_id == client_id
        )
        .order_by(
            MeasurementLog.date
        )
    )

    measurements = measurements.scalars().all()


    start_weight = None
    current_weight = None


    if measurements:

        start_weight = measurements[0].weight
        current_weight = measurements[-1].weight


    workouts = await session.execute(
        select(func.count(WorkoutSession.id))
        .where(
            WorkoutSession.user_id == client_id
        )
    )


    workout_count = workouts.scalar() or 0



    food = await session.execute(
        select(func.count(FoodDay.id))
        .where(
            FoodDay.client_id == client_id
        )
    )


    food_days = food.scalar() or 0



    return {

        "weight": {

            "start_weight": start_weight,

            "current_weight": current_weight,

            "diff_total":
                (
                    current_weight-start_weight
                    if start_weight and current_weight
                    else None
                )

        },


        "workouts": {

            "total_count": workout_count

        },


        "nutrition": {

            "days_tracked": food_days

        }

    }