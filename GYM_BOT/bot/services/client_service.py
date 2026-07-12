import datetime
import math
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, ClientProfile, TrainerClient


async def get_trainer_clients(
    session: AsyncSession,
    trainer_id: int,
    page: int = 1,
    limit: int = 5
) -> Tuple[List[Tuple[User, ClientProfile]], int]:
    """Повертає список клієнтів тренера з пагінацією."""
    try:
        offset = (page - 1) * limit
        
        # Запит для підрахунку загальної кількості
        count_stmt = select(func.count()).select_from(TrainerClient).where(TrainerClient.trainer_id == trainer_id)
        total_count = (await session.execute(count_stmt)).scalar() or 0
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        
        # Запит на отримання клієнтів
        stmt = (
            select(User, ClientProfile)
            .join(TrainerClient, TrainerClient.client_id == User.id)
            .join(ClientProfile, ClientProfile.user_id == User.id)
            .where(TrainerClient.trainer_id == trainer_id)
            .order_by(TrainerClient.assigned_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        clients = result.all()
        
        return clients, total_pages
    except Exception as e:
        await session.rollback()
        raise e


async def get_client_by_id(session: AsyncSession, client_id: int) -> Optional[Tuple[User, ClientProfile]]:
    """Повертає користувача та його профіль за ID."""
    try:
        stmt = (
            select(User, ClientProfile)
            .join(ClientProfile, ClientProfile.user_id == User.id)
            .where(User.id == client_id)
        )
        return (await session.execute(stmt)).first()
    except Exception as e:
        await session.rollback()
        raise e


async def update_client_profile(
    session: AsyncSession,
    client_id: int,
    field: str,
    value: Any
) -> Tuple[Any, Any]:
    """
    Оновлює одне поле у клієнта або його профілі.
    Повертає tuple (старе_значення, нове_значення) для AuditLog.
    """
    try:
        user, profile = await get_client_by_id(session, client_id)
        if not user or not profile:
            raise ValueError(f"Клієнта з ID {client_id} не знайдено")
            
        old_val = None
        
        if field == "name":
            old_val = user.full_name
            user.full_name = str(value)
        elif hasattr(profile, field):
            old_val = getattr(profile, field)
            
            # Конвертація типів
            if field in ("age", "height"):
                value = int(value) if value else None
            elif field in ("start_weight", "current_weight"):
                if isinstance(value, str):
                    value = float(value.replace(",", "."))
                else:
                    value = float(value)
            elif field == "next_checkin":
                if isinstance(value, str):
                    value = datetime.datetime.strptime(value, "%d.%m.%Y").date()
                elif value is None:
                    pass
                else:
                    value = value  # вже date
            
            setattr(profile, field, value)
        else:
            raise ValueError(f"Поле {field} не знайдено в профілі клієнта.")
        
        await session.commit()
        return old_val, value
    except Exception as e:
        await session.rollback()
        raise e


async def delete_client(session: AsyncSession, trainer_id: int, client_id: int) -> bool:
    """Відкріплює клієнта від тренера (видаляє зв'язок TrainerClient)."""
    try:
        stmt = select(TrainerClient).where(
            TrainerClient.trainer_id == trainer_id,
            TrainerClient.client_id == client_id
        )
        tc = (await session.execute(stmt)).scalar_one_or_none()
        
        if tc:
            await session.delete(tc)
            await session.commit()
            return True
        return False
    except Exception as e:
        await session.rollback()
        raise e


async def get_trainer_statistics(session: AsyncSession, trainer_id: int) -> Dict[str, Any]:
    """Збирає статистику для тренера по його клієнтах."""
    try:
        stmt = (
            select(ClientProfile, TrainerClient)
            .join(TrainerClient, TrainerClient.client_id == ClientProfile.user_id)
            .where(TrainerClient.trainer_id == trainer_id)
        )
        records = (await session.execute(stmt)).all()
        
        total = len(records)
        active = sum(1 for cp, tc in records if cp.is_active and tc.is_active)
        
        now = datetime.datetime.utcnow()
        first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        new_this_month = sum(1 for cp, tc in records if tc.assigned_at >= first_day_of_month)
        
        weights = [cp.current_weight for cp, tc in records if cp.current_weight]
        avg_weight = sum(weights) / len(weights) if weights else 0.0
        
        weight_changes = [
            (cp.start_weight - cp.current_weight)
            for cp, tc in records
            if cp.start_weight and cp.current_weight
        ]
        avg_change = sum(weight_changes) / len(weight_changes) if weight_changes else 0.0
        
        return {
            "total": total,
            "active": active,
            "new_month": new_this_month,
            "avg_weight": avg_weight,
            "avg_change": avg_change
        }
    except Exception as e:
        await session.rollback()
        raise e