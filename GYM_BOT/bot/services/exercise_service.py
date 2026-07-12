from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Exercise, ExerciseMedia

async def search_exercise(session: AsyncSession, query: str, limit: int = 10) -> List[Exercise]:
    """Шукає вправу в базі за назвою."""
    stmt = select(Exercise).where(Exercise.name.ilike(f"%{query}%")).limit(limit)
    return list((await session.execute(stmt)).scalars().all())

async def get_exercise(session: AsyncSession, exercise_id: int) -> Optional[Exercise]:
    """Отримує вправу за ID."""
    return await session.get(Exercise, exercise_id)

async def create_exercise(session: AsyncSession, name: str, muscle_group: str, description: Optional[str] = None) -> Exercise:
    """Створює нову вправу в довіднику."""
    ex = Exercise(name=name, muscle_group=muscle_group, description=description)
    session.add(ex)
    await session.commit()
    await session.refresh(ex)
    return ex

async def get_exercise_media(session: AsyncSession, exercise_id: int) -> List[ExerciseMedia]:
    """Отримує всі медіа файли, прив'язані до вправи."""
    stmt = select(ExerciseMedia).where(ExerciseMedia.exercise_id == exercise_id)
    return list((await session.execute(stmt)).scalars().all())

async def add_media(session: AsyncSession, exercise_id: int, media_type: str, file_id: str, description: Optional[str] = None) -> ExerciseMedia:
    """Додає відео/фото до вправи."""
    media = ExerciseMedia(
        exercise_id=exercise_id,
        type=media_type,
        file_id=file_id,
        description=description
    )
    session.add(media)
    await session.commit()
    await session.refresh(media)
    return media