import datetime
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AuditLog


async def log_action(
    session: AsyncSession,
    actor_id: int,
    target_user_id: Optional[int],
    action: str,
    details: Optional[dict[str, Any]] = None
) -> None:
    """
    Записує подію до журналу аудиту бази даних.
    """
    try:
        log_entry = AuditLog(
            actor_id=actor_id,
            target_id=target_user_id,
            action=action,
            details=details,
            date=datetime.datetime.utcnow()
        )
        session.add(log_entry)
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e