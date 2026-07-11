# FILE: ./bot/security.py
import logging
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from database.engine import UsersSessionLocal as AsyncSessionLocal
from database.models import User
from config import ALLOWED_USER_ID

logger = logging.getLogger(__name__)

class IsApproved(BaseFilter):
    """Перевіряє, чи користувач має базовий доступ до бота (для загальних команд)."""
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        if user_id == ALLOWED_USER_ID:
            return True
            
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            if user and user.is_approved:
                return True
                
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ У вас немає доступу. Введіть /start", show_alert=True)
            return False

class HasPermission(BaseFilter):
    """Перевіряє точкові права доступу у JSON (фінанси, клімат, тощо)."""
    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        if user_id == ALLOWED_USER_ID:
            return True
            
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            
            if not user or not user.is_approved:
                if isinstance(event, CallbackQuery):
                    await event.answer("⛔ У вас немає доступу. Введіть /start", show_alert=True)
                return False
                
            if user.role == "admin":
                return True
                
            has_access = user.permissions.get(self.permission, False)
            if not has_access and isinstance(event, CallbackQuery):
                await event.answer(f"⛔ Доступ заборонено (Потрібне право: {self.permission})", show_alert=True)
                
            return has_access