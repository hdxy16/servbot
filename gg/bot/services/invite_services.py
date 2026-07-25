import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, ClientProfile, TrainerClient
from bot.services.audit_service import log_action

logger = logging.getLogger(__name__)

async def link_client_to_trainer(session: AsyncSession, trainer_id: int, client_id: int) -> bool:
    """
    Зв'язує клієнта з тренером після переходу за інвайт-посиланням.
    """
    try:
        # Перевіряємо, чи існує тренер і чи має він права тренера
        trainer = await session.get(User, trainer_id)
        if not trainer or not trainer.is_trainer:
            return False
            
        # Перевіряємо, чи вже існує зв'язок
        stmt = select(TrainerClient).where(
            TrainerClient.trainer_id == trainer_id,
            TrainerClient.client_id == client_id
        )
        existing_link = (await session.execute(stmt)).scalar_one_or_none()
        
        if existing_link:
            if not existing_link.is_active:
                existing_link.is_active = True
                await session.commit()
            return True
            
        # Створюємо зв'язок Trainer -> Client
        new_link = TrainerClient(
            trainer_id=trainer_id, 
            client_id=client_id, 
            is_active=True
        )
        session.add(new_link)
        
        # Перевіряємо/створюємо ClientProfile
        stmt_profile = select(ClientProfile).where(ClientProfile.user_id == client_id)
        profile = (await session.execute(stmt_profile)).scalar_one_or_none()
        if not profile:
            profile = ClientProfile(user_id=client_id)
            session.add(profile)
            
        await session.commit()
        
        # Логуємо дію в AuditLog
        await log_action(
            session=session,
            actor_id=client_id,
            target_user_id=trainer_id,
            action="client_joined_trainer_via_link",
            details={"trainer_id": trainer_id}
        )
        return True
    except Exception as e:
        logger.error(f"Error linking client {client_id} to trainer {trainer_id}: {e}")
        return False