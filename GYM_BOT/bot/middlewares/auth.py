import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy import select

from database.engine import AsyncSessionLocal
from database.models import User, ClientProfile
from config import SUPERADMIN_ID

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        tg_user: TgUser = data.get("event_from_user")
        
        if not tg_user:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            try:
                stmt = select(User).where(User.telegram_id == tg_user.id)
                result = await session.execute(stmt)
                user_db = result.scalar_one_or_none()

                if not user_db:
                    roles = ["CLIENT"]
                    active_role = "CLIENT"
                    is_client = True
                    is_admin = False
                    is_trainer = False

                    if tg_user.id == SUPERADMIN_ID:
                        roles = ["ADMIN", "TRAINER", "CLIENT"]
                        active_role = "ADMIN"
                        is_admin = True
                        is_trainer = True
                        is_client = True

                    user_db = User(
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                        full_name=tg_user.full_name,
                        roles=roles,
                        active_role=active_role,
                        is_admin=is_admin,
                        is_trainer=is_trainer,
                        is_client=is_client
                    )
                    session.add(user_db)
                    await session.flush()
                    
                    client_profile = ClientProfile(
                        user_id=user_db.id,
                        is_active=True
                    )
                    session.add(client_profile)
                    
                    await session.commit()
                    await session.refresh(user_db)
                    logger.info(f"Новий користувач: {tg_user.full_name} ({tg_user.id})")
                else:
                    if user_db.username != tg_user.username:
                        user_db.username = tg_user.username
                    if user_db.full_name != tg_user.full_name:
                        user_db.full_name = tg_user.full_name
                    await session.commit()
                    await session.refresh(user_db)

                data["session"] = session
                data["user_db"] = user_db
                
                return await handler(event, data)
            except Exception as e:
                logger.error(f"AuthMiddleware error: {e}")
                await session.rollback()
                return await handler(event, data)