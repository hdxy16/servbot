from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from database.models import User

class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, user_db: User) -> bool:
        """Перевіряє, чи користувач має право адміна ТА його поточний режим - ADMIN"""
        return user_db.active_role == "ADMIN" and user_db.is_admin

class IsTrainer(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, user_db: User) -> bool:
        """Перевіряє, чи користувач має право тренера ТА його поточний режим - TRAINER"""
        return user_db.active_role == "TRAINER" and user_db.is_trainer

class IsClient(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, user_db: User) -> bool:
        """Перевіряє, чи користувач є клієнтом ТА його поточний режим - CLIENT"""
        return user_db.active_role == "CLIENT" and user_db.is_client