import logging
from aiogram import Router, F, types, Bot
from aiogram.utils.deep_linking import create_start_link

from bot.filters.role_filter import IsTrainer
from database.models import User
from bot.keyboards.trainer import TrainerClientCB

logger = logging.getLogger(__name__)
trainer_invite_router = Router()
trainer_invite_router.callback_query.filter(IsTrainer())

@trainer_invite_router.callback_query(TrainerClientCB.filter(F.action == "invite"))
async def cb_invite_client(callback: types.CallbackQuery, user_db: User, bot: Bot):
    """
    Генерує безпечне Deep Link посилання. 
    Коли клієнт перейде за ним, він автоматично додасться до пулу цього тренера.
    """
    try:
        # Генеруємо посилання формату: t.me/BotUsername?start=trainer_123 (енкодоване)
        link = await create_start_link(bot, f"trainer_{user_db.id}", encode=True)
        
        text = (
            f"🔗 <b>Ваше персональне посилання для запрошення клієнтів:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"Надішліть це посилання новому клієнту. Коли він перейде за ним і натисне кнопку 'Розпочати' (Start), "
            f"система автоматично додасть його до вашого списку клієнтів."
        )
        
        await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error generating invite link for trainer {user_db.id}: {e}")
        await callback.message.answer("❌ Сталася помилка при генерації посилання. Спробуйте пізніше.")
        
    await callback.answer()