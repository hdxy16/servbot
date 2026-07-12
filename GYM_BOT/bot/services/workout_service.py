import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import (
    WorkoutProgram, WorkoutDay, WorkoutExercise, AssignedProgram,
    WorkoutSession, WorkoutSet, Exercise
)


async def create_program(session: AsyncSession, trainer_id: int, name: str, description: str) -> WorkoutProgram:
    try:
        program = WorkoutProgram(trainer_id=trainer_id, name=name, description=description)
        session.add(program)
        await session.commit()
        await session.refresh(program)
        return program
    except Exception as e:
        await session.rollback()
        raise e


async def create_day(session: AsyncSession, program_id: int, name: str, order: int) -> WorkoutDay:
    try:
        day = WorkoutDay(program_id=program_id, name=name, order=order)
        session.add(day)
        await session.commit()
        await session.refresh(day)
        return day
    except Exception as e:
        await session.rollback()
        raise e


async def add_exercise_to_day(
    session: AsyncSession,
    workout_day_id: int,
    exercise_id: int,
    target_sets: int,
    target_reps: str,
    trainer_note: Optional[str] = None
) -> WorkoutExercise:
    try:
        we = WorkoutExercise(
            workout_day_id=workout_day_id,
            exercise_id=exercise_id,
            target_sets=target_sets,
            target_reps=target_reps,
            trainer_note=trainer_note
        )
        session.add(we)
        await session.commit()
        await session.refresh(we)
        return we
    except Exception as e:
        await session.rollback()
        raise e


async def get_trainer_programs(session: AsyncSession, trainer_id: int) -> List[WorkoutProgram]:
    try:
        stmt = select(WorkoutProgram).where(WorkoutProgram.trainer_id == trainer_id)
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e


async def assign_program(session: AsyncSession, client_id: int, template_id: int) -> AssignedProgram:
    """Глибоке копіювання шаблону програми для конкретного клієнта."""
    try:
        template = await session.get(WorkoutProgram, template_id)
        if not template:
            raise ValueError("Шаблон не знайдено.")
        
        # 1. Створюємо копію програми
        cloned_prog = WorkoutProgram(
            trainer_id=template.trainer_id,
            name=f"{template.name} (Персональна)",
            description=template.description
        )
        session.add(cloned_prog)
        await session.flush()
        
        # 2. Копіюємо дні
        stmt_days = select(WorkoutDay).where(WorkoutDay.program_id == template_id).order_by(WorkoutDay.order)
        days = (await session.execute(stmt_days)).scalars().all()
        
        for day in days:
            cloned_day = WorkoutDay(program_id=cloned_prog.id, name=day.name, order=day.order)
            session.add(cloned_day)
            await session.flush()
            
            # 3. Копіюємо вправи дня
            stmt_ex = select(WorkoutExercise).where(WorkoutExercise.workout_day_id == day.id)
            exercises = (await session.execute(stmt_ex)).scalars().all()
            for we in exercises:
                session.add(WorkoutExercise(
                    workout_day_id=cloned_day.id,
                    exercise_id=we.exercise_id,
                    target_sets=we.target_sets,
                    target_reps=we.target_reps,
                    trainer_note=we.trainer_note,
                    trainer_video_file_id=we.trainer_video_file_id
                ))
        
        # 4. Видаляємо стару прив'язку клієнта і створюємо нову
        stmt_old = select(AssignedProgram).where(AssignedProgram.user_id == client_id)
        old_assigned = (await session.execute(stmt_old)).scalar_one_or_none()
        if old_assigned:
            await session.delete(old_assigned)
            await session.flush()
        
        assigned = AssignedProgram(
            user_id=client_id,
            template_id=template_id,
            program_data={"cloned_program_id": cloned_prog.id}
        )
        session.add(assigned)
        await session.commit()
        await session.refresh(assigned)
        return assigned
    except Exception as e:
        await session.rollback()
        raise e


async def get_client_program(session: AsyncSession, client_id: int) -> Optional[WorkoutProgram]:
    try:
        stmt = select(AssignedProgram).where(AssignedProgram.user_id == client_id)
        assigned = (await session.execute(stmt)).scalar_one_or_none()
        if not assigned or not assigned.program_data.get("cloned_program_id"):
            return None
        
        prog_id = assigned.program_data["cloned_program_id"]
        return await session.get(WorkoutProgram, prog_id)
    except Exception as e:
        await session.rollback()
        raise e


async def get_program_days(session: AsyncSession, program_id: int) -> List[WorkoutDay]:
    try:
        stmt = select(WorkoutDay).where(WorkoutDay.program_id == program_id).order_by(WorkoutDay.order)
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e


async def get_day_exercises(session: AsyncSession, workout_day_id: int) -> List[Tuple[WorkoutExercise, Exercise]]:
    try:
        stmt = (
            select(WorkoutExercise, Exercise)
            .join(Exercise, Exercise.id == WorkoutExercise.exercise_id)
            .where(WorkoutExercise.workout_day_id == workout_day_id)
            .order_by(WorkoutExercise.id)
        )
        return list((await session.execute(stmt)).all())
    except Exception as e:
        await session.rollback()
        raise e


# ===============================
# ВИКОНАННЯ ТРЕНУВАННЯ
# ===============================
async def start_workout(session: AsyncSession, client_id: int, workout_day_id: int, day_name: str) -> WorkoutSession:
    try:
        ws = WorkoutSession(
            client_id=client_id,
            workout_day_id=workout_day_id,
            day_name=day_name
        )
        session.add(ws)
        await session.commit()
        await session.refresh(ws)
        return ws
    except Exception as e:
        await session.rollback()
        raise e


async def get_active_session(session: AsyncSession, client_id: int) -> Optional[WorkoutSession]:
    try:
        stmt = select(WorkoutSession).where(
            WorkoutSession.client_id == client_id,
            WorkoutSession.completed == False
        ).order_by(WorkoutSession.date.desc())
        return (await session.execute(stmt)).scalar_one_or_none()
    except Exception as e:
        await session.rollback()
        raise e


async def finish_workout(session: AsyncSession, session_id: int) -> None:
    try:
        ws = await session.get(WorkoutSession, session_id)
        if ws:
            ws.completed = True
            await session.commit()
    except Exception as e:
        await session.rollback()
        raise e


async def get_done_sets(session: AsyncSession, session_id: int, workout_exercise_id: int) -> List[WorkoutSet]:
    try:
        stmt = select(WorkoutSet).where(
            WorkoutSet.session_id == session_id,
            WorkoutSet.workout_exercise_id == workout_exercise_id
        ).order_by(WorkoutSet.set_number)
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e


async def save_set(session: AsyncSession, session_id: int, we_id: int, weight: float, reps: int, rpe: Optional[int]) -> WorkoutSet:
    try:
        done_sets = await get_done_sets(session, session_id, we_id)
        set_num = len(done_sets) + 1
        
        w_set = WorkoutSet(
            session_id=session_id,
            workout_exercise_id=we_id,
            weight=weight,
            reps=reps,
            set_number=set_num,
            rpe=rpe
        )
        session.add(w_set)
        await session.commit()
        await session.refresh(w_set)
        return w_set
    except Exception as e:
        await session.rollback()
        raise e


async def get_exercise_history(session: AsyncSession, client_id: int, exercise_id: int, limit: int = 5) -> List[WorkoutSet]:
    """Повертає останні підходи клієнта по конкретній вправі."""
    try:
        stmt = (
            select(WorkoutSet)
            .join(WorkoutSession, WorkoutSession.id == WorkoutSet.session_id)
            .join(WorkoutExercise, WorkoutExercise.id == WorkoutSet.workout_exercise_id)
            .where(
                WorkoutSession.client_id == client_id,
                WorkoutExercise.exercise_id == exercise_id,
                WorkoutSession.completed == True
            )
            .order_by(WorkoutSession.date.desc(), WorkoutSet.set_number)
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())
    except Exception as e:
        await session.rollback()
        raise e