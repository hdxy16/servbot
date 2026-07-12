# Gym_Bot/main.py
import os
import sys
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher
from sqlalchemy import select, text

# ХАК: Робимо папку Gym_Bot головною для цього процесу
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BOT_TOKEN
from database import init_db, AsyncSessionLocal, User, ClientTarget, DayClosure
from handlers_trainer import router as trainer_router
from handlers_client import router as client_router

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# АВТОНОМНИЙ КРОН-МОНІТОР ДЛЯ ЩОДЕННИХ ЗВІТІВ ТРЕНЕРА (ІДЕЯ 2)
async def auto_daily_report_scheduler(bot: Bot):
    print("🕒 Безпечний внутрішній Крон-планувальник звітів успішно ініціалізовано.")
    while True:
        try:
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")
            
            async with AsyncSessionLocal() as session:
                # Знаходимо всіх тренерів, у яких час звіту збігається з поточним хвилиною, і звіт ще не надсилався сьогодні
                res = await session.execute(
                    select(User).where(
                        User.role == "trainer",
                        User.digest_time == current_time_str,
                        (User.last_digest_date.is_(None)) | (User.last_digest_date != today_str)
                    )
                )
                trainers_to_alert = res.scalars().all()
                
                if trainers_to_alert:
                    # Збираємо зведену аналітику по ВСІХ клієнтах у базі
                    clients_res = await session.execute(select(User).where(User.role == "client").order_by(User.full_name))
                    all_clients = clients_res.scalars().all()
                    
                    if all_clients:
                        report_lines = [
                            f"📋 <b>ЩОДЕННИЙ СВЕДЕНИЙ РАПОРТ КЛІЄНТІВ</b>",
                            f"Дата: <b>{now.strftime('%d.%m.%Y')}</b>",
                            f"Час тригера: <code>{current_time_str}</code>",
                            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        ]
                        
                        for client in all_clients:
                            target = await session.get(ClientTarget, client.id)
                            
                            # Вага
                            w_res = await session.execute(text("SELECT weight FROM weight_logs WHERE user_id = :uid ORDER BY date DESC LIMIT 1").bindparams(uid=client.id))
                            w_row = w_res.fetchone()
                            w_str = f"{w_row[0]:.1f} кг" if w_row else "немає даних"
                            
                            # Зважена їжа за сьогодні
                            f_res = await session.execute(text("SELECT category, SUM(portions) FROM food_entries WHERE user_id = :uid AND date = :dt GROUP BY category").bindparams(uid=client.id, dt=today_str))
                            f_rows = f_res.fetchall()
                            
                            totals = {"protein": 0.0, "carbs": 0.0, "fats": 0.0}
                            for r in f_rows:
                                if r[0] in totals: totals[r[0]] = float(r[1] or 0)
                                
                            # Статус закриття дня
                            close_res = await session.execute(select(DayClosure).where(DayClosure.user_id == client.id, DayClosure.date == today_str))
                            status_icon = "🔒 ЗАКРИТО" if close_res.scalar_one_or_none() else "⏳ В процесі"
                            
                            report_lines.append(
                                f"👤 <b>{client.full_name}</b> [{status_icon}]\n"
                                f"  🔥 Стрік: <code>{client.streak} дн.</code> | Вага: <code>{w_str}</code>\n"
                                f"  🥩 Б: <b>{totals['protein']:.1f}</b>/{target.protein_target:.1f} порц.\n"
                                f"  🍚 В: <b>{totals['carbs']:.1f}</b>/{target.carbs_target:.1f} порц.\n"
                                f"  🥜 Ж: <b>{totals['fats']:.1f}</b>/{target.fats_target:.1f} порц.\n"
                            )
                        
                        master_report_text = "\n".join(report_lines)
                        
                        # Відправляємо звіт кожному тренеру, чий таймер спрацював
                        for trainer in trainers_to_alert:
                            try:
                                await bot.send_message(chat_id=trainer.telegram_id, text=master_report_text, parse_mode="HTML")
                                trainer.last_digest_date = today_str # Відмічаємо успішне виконання
                            except Exception:
                                pass
                        
                        await session.commit()
                        
        except Exception as e:
            logging.error(f"Помилка всередині Крон-планувальника звітів: {e}")
            
        await asyncio.sleep(60) # Перевірка раз на хвилину

async def main():
    await init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(trainer_router)
    dp.include_router(client_router)
    
    # Запуск фонового Крон-процесу паралельно з пулінгом Telegram
    asyncio.create_task(auto_daily_report_scheduler(bot))
    
    logging.info("Gym_Bot успішно запустився на особистому ізольованому шляху!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())