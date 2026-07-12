from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Перевіряє, чи користувач має право адміна."""
        user_db = getattr(event, 'user_db', None)
        if not user_db:
            return False
        try:
            return user_db.active_role == "ADMIN" and user_db.is_admin
        except Exception:
            return False


class IsTrainer(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Перевіряє, чи користувач має право тренера."""
        user_db = getattr(event, 'user_db', None)
        if not user_db:
            return False
        try:
            return user_db.active_role == "TRAINER" and user_db.is_trainer
        except Exception:
            return False


class IsClient(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Перевіряє, чи користувач є клієнтом."""
        user_db = getattr(event, 'user_db', None)
        if not user_db:
            return False
        try:
            return user_db.active_role == "CLIENT" and user_db.is_client
        except Exception:
            return False