# FILE: bot/services/tools.py
import io
import logging
from datetime import datetime
from gtts import gTTS
from aiogram.types import BufferedInputFile
from bot.actual_api import get_budget_data
from bot.home_assistant import ha_client
import re  # <--- ЦЕЙ ІМПОРТ ВИРІШУЄ ТВОЮ ПРОБЛЕМУ
logger = logging.getLogger(__name__)

class TTSService:
    @staticmethod
    def generate_voice_msg(text: str, filename: str = "reply.ogg") -> BufferedInputFile:
        """
        Генерує аудіо з тексту повністю в оперативній пам'яті (In-Memory Buffer),
        запобігаючи зносу SSD/диска на mini-PC. Повертає готовий для aiogram BufferedInputFile.
        """
        try:
            # Очищаємо текст від HTML-тегів, які бот використовує для розмітки чату
            clean_text = re.sub(r'<[^>]+>', '', text)
            
            mp3_fp = io.BytesIO()
            # Використовуємо gTTS для чистої української вимови
            tts = gTTS(text=clean_text, lang='uk', slow=False)
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)
            
            return BufferedInputFile(mp3_fp.read(), filename=filename)
        except Exception as e:
            logger.error(f"Помилка генерації TTS: {e}")
            return None

class ReportService:
    @staticmethod
    async def generate_financial_report() -> str:
        """Генерує enterprise-рівень фінансового звіту на основі Actual Budget"""
        data = await get_budget_data()
        if not data:
            return "❌ <b>Не вдалося отримати дані з Actual Budget.</b> Перевірте контейнер API."
            
        report = [
            f"📊 <b>ФІНАНСОВИЙ АНАЛІТИЧНИЙ ЗВІТ | {data['month']}</b>",
            f"━━━━━━━━━━━━━━━━━━━━━━━━",
            f"💰 Загальний вільний залишок: <b>{data['total_balance']:.2f}€</b>\n",
            "<b>Розподіл по групах категорій:</b>"
        ]
        
        for group_name, group in data["groups"].items():
            report.append(f"📁 <b>{group_name}</b>: {group['balance']:.2f}€")
            spent = abs(group["spent"])
            budgeted = group["budgeted"]
            
            if budgeted > 0:
                ratio = min(spent / budgeted, 1.0)
                filled = int(round(ratio * 10))
                bar = "🟩" * filled + "⬜" * (10 - filled)
                report.append(f"<code>[{bar}]</code> {spent:.2f}€ / {budgeted:.2f}€")
            else:
                report.append(f"📉 Витрачено: {spent:.2f}€ (Без ліміту)")
            report.append("")
            
        return "\n".join(report)

    @staticmethod
    async def generate_climate_report() -> str:
        """Генерує детермінований кліматичний звіт розумного дому"""
        k_t = (await ha_client.get_entity_state("sensor.kitchen_sensor_climate_temperature")).get("state", "Н/Д")
        k_h = (await ha_client.get_entity_state("sensor.kitchen_sensor_climate_humidity")).get("state", "Н/Д")
        b_t = (await ha_client.get_entity_state("sensor.bathroom_sensor_climate_temperature")).get("state", "Н/Д")
        b_h = (await ha_client.get_entity_state("sensor.bathroom_sensor_climate_humidity")).get("state", "Н/Д")
        
        report = [
            f"🌡 <b>КЛІМАТИЧНИЙ ЗВІТ ДОМУ</b>",
            f"📅 Станом на: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🍳 <b>Кухня:</b>",
            f"  ▫️ Температура: {k_t}°C",
            f"  ▫️ Вологість: {k_h}%",
            f"",
            f"🛁 <b>Ванна кімната:</b>",
            f"  ▫️ Температура: {b_t}°C",
            f"  ▫️ Вологість: {b_h}%",
            f"━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<i>Статус систем вентиляції: Автоматичний режим.</i>"
        ]
        return "\n".join(report)