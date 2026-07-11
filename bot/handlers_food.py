# FILE: ./bot/handlers_food.py
import logging
import re
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import text

from database.engine import UsersSessionLocal as AsyncSessionLocal
from bot.security import IsApproved

logger = logging.getLogger(__name__)
router = Router()

FOOD_CATALOG = {
    "protein": [
        {"name": "Куряче філе", "unit": "г", "size": 160.0},
        {"name": "Стегно курки без шкіри", "unit": "г", "size": 110.0},
        {"name": "Филе індички", "unit": "г", "size": 160.0},
        {"name": "Стегно індички без шкіри", "unit": "г", "size": 110.0},
        {"name": "Телятина", "unit": "г", "size": 150.0},
        {"name": "Вирізка свинини", "unit": "г", "size": 140.0},
        {"name": "Хек", "unit": "г", "size": 190.0},
        {"name": "Мінтай", "unit": "г", "size": 190.0},
        {"name": "Тріска", "unit": "г", "size": 190.0},
        {"name": "Судак", "unit": "г", "size": 190.0},
        {"name": "Пікша", "unit": "г", "size": 190.0},
        {"name": "Окунь", "unit": "г", "size": 190.0},
        {"name": "Щука", "unit": "г", "size": 190.0},
        {"name": "Тілапія", "unit": "г", "size": 190.0},
        {"name": "Тунець у власному соку", "unit": "г", "size": 200.0},
        {"name": "Лосось", "unit": "г", "size": 100.0},
        {"name": "Форель", "unit": "г", "size": 100.0},
        {"name": "Скумбрія", "unit": "г", "size": 100.0},
        {"name": "Оселедець", "unit": "г", "size": 100.0},
        {"name": "Сардина", "unit": "г", "size": 110.0},
        {"name": "Тунець жирний", "unit": "г", "size": 100.0},
        {"name": "Креветки", "unit": "г", "size": 180.0},
        {"name": "Мідії без олії", "unit": "г", "size": 220.0},
        {"name": "Восьминіг", "unit": "г", "size": 180.0},
        {"name": "Курячі яйця", "unit": "шт", "size": 3.0},
        {"name": "Сир кисломолочний 0%", "unit": "г", "size": 220.0},
        {"name": "Сир кисломолочний 2%", "unit": "г", "size": 200.0},
        {"name": "Сир кисломолочний 5%", "unit": "г", "size": 180.0},
        {"name": "Сири тверді", "unit": "г", "size": 50.0},
        {"name": "Йогурт до 3%", "unit": "г", "size": 330.0},
        {"name": "Кефір до 3%", "unit": "мл", "size": 400.0},
        {"name": "Молоко до 2.5%", "unit": "мл", "size": 400.0},
    ],
    "carbs": [
        {"name": "Рис", "unit": "г", "size": 50.0},
        {"name": "Гречка", "unit": "г", "size": 50.0},
        {"name": "Булгур", "unit": "г", "size": 50.0},
        {"name": "Кус-кус", "unit": "г", "size": 50.0},
        {"name": "Перловка", "unit": "г", "size": 50.0},
        {"name": "Ячна крупа", "unit": "г", "size": 50.0},
        {"name": "Пшоняна крупа", "unit": "г", "size": 50.0},
        {"name": "Вівсяні пластівці", "unit": "г", "size": 50.0},
        {"name": "Кукурудзяна крупа", "unit": "г", "size": 55.0},
        {"name": "Манка", "unit": "г", "size": 50.0},
        {"name": "Кіноа", "unit": "г", "size": 50.0},
        {"name": "Вівсянка", "unit": "г", "size": 50.0},
        {"name": "Макарони", "unit": "г", "size": 50.0},
        {"name": "Цільнозернові макарони", "unit": "г", "size": 50.0},
        {"name": "Локшина", "unit": "г", "size": 50.0},
        {"name": "Лаваш", "unit": "г", "size": 70.0},
        {"name": "Цільнозерновий хліб", "unit": "г", "size": 70.0},
        {"name": "Житній хліб", "unit": "г", "size": 70.0},
        {"name": "Хлібці", "unit": "г", "size": 60.0},
        {"name": "Картопля", "unit": "г", "size": 225.0},
        {"name": "Батат", "unit": "г", "size": 225.0},
        {"name": "Кукурудза", "unit": "г", "size": 250.0},
        {"name": "Квасоля", "unit": "г", "size": 150.0},
        {"name": "Нут", "unit": "г", "size": 150.0},
        {"name": "Горох", "unit": "г", "size": 200.0},
        {"name": "Сочевиця", "unit": "г", "size": 70.0},
    ],
    "fats": [
        {"name": "Оливкова олія", "unit": "г", "size": 15.0},
        {"name": "Соняшникова олія", "unit": "г", "size": 15.0},
        {"name": "Лляна олія", "unit": "г", "size": 15.0},
        {"name": "Кокосова олія", "unit": "г", "size": 15.0},
        {"name": "Авокадова олія", "unit": "г", "size": 15.0},
        {"name": "Авокадо", "unit": "г", "size": 80.0},
        {"name": "Маслини", "unit": "г", "size": 50.0},
        {"name": "Оливки", "unit": "г", "size": 50.0},
        {"name": "Майонез", "unit": "г", "size": 20.0},
        {"name": "Кетчуп", "unit": "г", "size": 50.0},
        {"name": "Волоські горіхи", "unit": "г", "size": 25.0},
        {"name": "Мигдаль", "unit": "г", "size": 25.0},
        {"name": "Фундук", "unit": "г", "size": 25.0},
        {"name": "Кеш'ю", "unit": "г", "size": 30.0},
        {"name": "Фісташки", "unit": "г", "size": 30.0},
        {"name": "Арахіс", "unit": "г", "size": 30.0},
        {"name": "Макадамія", "unit": "г", "size": 20.0},
        {"name": "Пекан", "unit": "г", "size": 20.0},
        {"name": "Бразильський горіх", "unit": "г", "size": 25.0},
        {"name": "Насіння соняшника", "unit": "г", "size": 30.0},
        {"name": "Насіння гарбуза", "unit": "г", "size": 30.0},
        {"name": "Насіння льону", "unit": "г", "size": 25.0},
        {"name": "Насіння чіа", "unit": "г", "size": 25.0},
        {"name": "Кунжут", "unit": "г", "size": 30.0},
        {"name": "Арахісова паста", "unit": "г", "size": 25.0},
        {"name": "Тахіні", "unit": "г", "size": 25.0},
    ],
    "fruits": [
        {"name": "Будь-які фрукти (універсал)", "unit": "г", "size": 300.0},
        {"name": "Банан", "unit": "г", "size": 150.0},
        {"name": "Манго", "unit": "г", "size": 180.0},
        {"name": "Хурма", "unit": "г", "size": 200.0},
        {"name": "Виноград", "unit": "г", "size": 180.0},
    ]
}

CAT_NAMES = {
    "protein": "🥩 Білки",
    "carbs": "🍚 Вуглеводи",
    "fruits": "🍎 Фрукти",
    "fats": "🥜 Жири",
    "anything": "🍩 Будь-що",
    "veggies": "🥗 Овочі"
}

class FoodFSM(StatesGroup):
    waiting_for_amount = State()
    waiting_for_veggies = State()
    waiting_for_anything = State()

async def ensure_food_table():
    async with AsyncSessionLocal() as session:
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS food_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                product_name TEXT NOT NULL,
                amount REAL NOT NULL,
                portions REAL NOT NULL
            );
        """))
        await session.commit()

async def get_today_totals(user_id: int, date_str: str) -> dict:
    await ensure_food_table()
    totals = {"protein": 0.0, "carbs": 0.0, "fruits": 0.0, "fats": 0.0, "anything": 0.0, "veggies": 0.0, "steps": 0}
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT category, SUM(amount), SUM(portions) 
            FROM food_entries 
            WHERE user_id = :uid AND date = :dt 
            GROUP BY category
        """)
        rows = (await session.execute(query, {"uid": user_id, "dt": date_str})).all()
        for row in rows:
            cat = row[0]
            if cat == "veggies":
                totals["veggies"] = float(row[1] or 0)
            elif cat == "steps":
                totals["steps"] = int(row[1] or 0)
            else:
                totals[cat] = float(row[2] or 0)
    return totals

async def upsert_iphone_steps(user_id: int, date_str: str, steps_count: int):
    await ensure_food_table()
    async with AsyncSessionLocal() as session:
        # Примусово очищаємо старі записи кроків за цей день.
        # Це на 100% захищає базу від мікросекундних дублів з iPhone.
        await session.execute(text("""
            DELETE FROM food_entries 
            WHERE user_id = :uid AND date = :dt AND category = 'steps'
        """), {"uid": user_id, "dt": date_str})
        
        # Вставляємо один свіжий актуальний показник
        insert_query = text("""
            INSERT INTO food_entries (user_id, date, category, product_name, amount, portions)
            VALUES (:uid, :dt, 'steps', 'Кроки з iPhone', :amt, 0.0)
        """)
        await session.execute(insert_query, {"uid": user_id, "dt": date_str, "amt": steps_count})
        await session.commit()
def render_dashboard_text(totals: dict, date_str: str) -> str:
    p_mark = "✅" if totals['protein'] >= 3.5 else "⏳"
    c_mark = "✅" if totals['carbs'] >= 3.0 else "⏳"
    fr_mark = "✅" if totals['fruits'] >= 1.0 else "⏳"
    f_mark = "✅" if totals['fats'] >= 3.0 else "⏳"
    a_mark = "✅" if totals['anything'] >= 2.0 else "⏳"
    v_mark = "✅" if totals['veggies'] >= 300 else "⏳"

    return (
        f"🍏 <b>Контроль раціону | {date_str}</b>\n\n"
        f"🥩 Білки: <b>{totals['protein']:.2f}</b> / 3.5 порц. {p_mark}\n"
        f"🍚 Вуглеводи: <b>{totals['carbs']:.2f}</b> / 3.0 порц. {c_mark}\n"
        f"🍎 Фрукти: <b>{totals['fruits']:.2f}</b> / 1.0 порц. {fr_mark}\n"
        f"🥜 Жири: <b>{totals['fats']:.2f}</b> / 3.0 порц. {f_mark}\n"
        f"🍩 Будь-що: <b>{totals['anything']:.2f}</b> / 2.0 порц. {a_mark}\n"
        f"🥗 Овочі: <b>{int(totals['veggies'])} г</b> (ціль 300-500г) {v_mark}\n"
        f"🏃 Кроки (iOS): <b>{totals['steps']:,}</b>\n"
    )

def main_food_keyboard() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🥩 Білок", callback_data="food_cat_protein")
    kb.button(text="🍚 Вуглевод", callback_data="food_cat_carbs")
    kb.button(text="🍎 Фрукт", callback_data="food_cat_fruits")
    kb.button(text="🥜 Жир", callback_data="food_cat_fats")
    kb.button(text="🥗 Овочі (г)", callback_data="food_add_veggies")
    kb.button(text="🍩 Будь-що (порц.)", callback_data="food_add_anything")
    kb.button(text="📋 Сформувати звіт тренеру", callback_data="food_build_report")
    kb.button(text="🗑 Очистити журнал", callback_data="food_clear_day")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()

# ==========================================
# ОБРОБНИКИ НАВІГАЦІЇ ТА КНОПОК
# ==========================================
@router.message(F.text == "🍏 Трекер їжі", IsApproved())
async def cmd_food_main(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    totals = await get_today_totals(message.from_user.id, today)
    await message.answer(render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "food_home", IsApproved())
async def cal_food_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    totals = await get_today_totals(callback.from_user.id, today)
    await callback.message.edit_text(render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("food_cat_"), IsApproved())
async def process_category_click(callback: types.CallbackQuery):
    category = callback.data.replace("food_cat_", "")
    products = FOOD_CATALOG.get(category, [])
    
    kb = InlineKeyboardBuilder()
    for idx, prod in enumerate(products):
        kb.button(text=f"{prod['name']} ({prod['size']}{prod['unit']})", callback_data=f"food_prod_{category}_{idx}")
    kb.button(text="🔙 Назад", callback_data="food_home")
    kb.adjust(2)
    
    await callback.message.edit_text(f"👇 <b>Обери продукт з категорії {CAT_NAMES[category]}:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("food_prod_"), IsApproved())
async def process_product_click(callback: types.CallbackQuery, state: FSMContext):
    _, _, category, idx_str = callback.data.split("_")
    idx = int(idx_str)
    product = FOOD_CATALOG[category][idx]
    
    await state.set_state(FoodFSM.waiting_for_amount)
    await state.update_data(cat=category, prod_name=product['name'], unit=product['unit'], size=product['size'], msg_id=callback.message.message_id)
    
    kb = InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="food_home").as_markup()
    await callback.message.edit_text(
        f"✍️ Введіть кількість для: <b>{product['name']}</b>\n"
        f"Базова порція = <b>{product['size']} {product['unit']}</b>\n"
        f"Введіть чисті грами (або шт) з ваг:",
        parse_mode="HTML", reply_markup=kb
    )
    await callback.answer()

@router.message(FoodFSM.waiting_for_amount, IsApproved())
async def process_amount_input(message: types.Message, state: FSMContext, bot: Bot):
    text_input = message.text.strip().replace(",", ".")
    if not re.match(r"^\d+(?:\.\d+)?$", text_input):
        await message.answer("❌ Введіть коректне число!")
        return
        
    amount = float(text_input)
    data = await state.get_data()
    await state.clear()
    
    portions_calculated = amount / data['size']
    today = datetime.now().strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO food_entries (user_id, date, category, product_name, amount, portions)
            VALUES (:uid, :dt, :cat, :pname, :amt, :port)
        """)
        await session.execute(query, {
            "uid": message.from_user.id, "dt": today, "cat": data['cat'],
            "pname": data['prod_name'], "amt": amount, "port": portions_calculated
        })
        await session.commit()
        
    try: await bot.delete_message(message.chat.id, data['msg_id'])
    except Exception: pass
    await message.delete()
    
    totals = await get_today_totals(message.from_user.id, today)
    await message.answer(render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "food_add_veggies", IsApproved())
async def cal_add_veggies(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FoodFSM.waiting_for_veggies)
    await state.update_data(msg_id=callback.message.message_id)
    kb = InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="food_home").as_markup()
    await callback.message.edit_text("🥗 <b>Введіть вагу овочів у грамах</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.message(FoodFSM.waiting_for_veggies, F.text.regexp(r"^\d+$"))
async def txt_add_veggies(message: types.Message, state: FSMContext, bot: Bot):
    grams = float(message.text)
    data = await state.get_data()
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO food_entries (user_id, date, category, product_name, amount, portions)
            VALUES (:uid, :dt, 'veggies', 'Овочі', :amt, 0.0)
        """)
        await session.execute(query, {"uid": message.from_user.id, "dt": today, "amt": grams})
        await session.commit()
        
    try: await bot.delete_message(message.chat.id, data['msg_id'])
    except Exception: pass
    await message.delete()
    
    totals = await get_today_totals(message.from_user.id, today)
    await message.answer(render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "food_add_anything", IsApproved())
async def cal_add_anything(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FoodFSM.waiting_for_anything)
    await state.update_data(msg_id=callback.message.message_id)
    kb = InlineKeyboardBuilder().button(text="❌ Скасувати", callback_data="food_home").as_markup()
    await callback.message.edit_text("🍩 <b>Введіть кількість порцій 'Будь-що'</b>:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.message(FoodFSM.waiting_for_anything, IsApproved())
async def txt_add_anything(message: types.Message, state: FSMContext, bot: Bot):
    input_val = message.text.strip().replace(",", ".")
    if not re.match(r"^\d+(?:\.\d+)?$", input_val):
        await message.answer("❌ Введіть число!")
        return
    portions = float(input_val)
    data = await state.get_data()
    await state.clear()
    today = datetime.now().strftime("%Y-%m-%d")
    
    async with AsyncSessionLocal() as session:
        query = text("""
            INSERT INTO food_entries (user_id, date, category, product_name, amount, portions)
            VALUES (:uid, :dt, 'anything', 'Будь-що / Доп. вуглеводи', 1.0, :port)
        """)
        await session.execute(query, {"uid": message.from_user.id, "dt": today, "port": portions})
        await session.commit()
        
    try: await bot.delete_message(message.chat.id, data['msg_id'])
    except Exception: pass
    await message.delete()
    
    totals = await get_today_totals(message.from_user.id, today)
    await message.answer(render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "food_clear_day", IsApproved())
async def cal_clear_food(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM food_entries WHERE user_id = :uid AND date = :dt"), {"uid": callback.from_user.id, "dt": today})
        await session.commit()
    totals = await get_today_totals(callback.from_user.id, today)
    await callback.message.edit_text("🧹 Журнал очищено!\n\n" + render_dashboard_text(totals, today), reply_markup=main_food_keyboard(), parse_mode="HTML")
    await callback.answer()

# АВТОМАТИЧНЕ ПІДСТАВЛЯННЯ КРОКІВ У ЗВІТ ДЛЯ ТРЕНЕРА
@router.callback_query(F.data == "food_build_report", IsApproved())
async def cal_build_report(callback: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    totals = await get_today_totals(callback.from_user.id, today)
    
    async with AsyncSessionLocal() as session:
        query = text("SELECT category, product_name, amount, portions FROM food_entries WHERE user_id = :uid AND date = :dt")
        entries = (await session.execute(query, {"uid": callback.from_user.id, "dt": today})).all()
        
    structured = {k: [] for k in CAT_NAMES.keys()}
    for row in entries:
        if row[0] in structured:
            unit = "шт" if "яйця" in row[1].lower() else ("порц." if row[0] == "anything" else "г")
            structured[row[0]].append(f"  ▫️ {row[1]}: {row[2]:g} {unit} ({row[3]:.2f} popц.)")

    report_lines = [
        f"📋 <b>ЗВІТ ПО ХАРЧУВАННЮ ЗА {datetime.now().strftime('%d.%m.%Y')}</b>\n",
        f"‼️ <b>Ціль:</b> 🥩 3.5 Б | 🍚 3 В | 🍎 1 Ф | 🥜 3 Ж | 🍩 2 'Будь-що'",
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    for cat_key, name in CAT_NAMES.items():
        if cat_key == "veggies":
            report_lines.append(f"<b>{name}:</b> {int(totals['veggies'])} г / 300-500г")
        elif cat_key == "anything":
            report_lines.append(f"<b>{name}:</b> {totals['anything']:.2f} / 2.0 порц.")
        else:
            report_lines.append(f"<b>{name}:</b> {totals[cat_key]:.2f} порц.")
            
        if structured[cat_key]:
            report_lines.extend(structured[cat_key])
        report_lines.append("")

    report_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    # АВТОМАТИЧНИЙ СТАТУС АКТИВНОСТІ
    report_lines.append(f"🏃 <b>Активність за день:</b> {totals['steps']:,} кроків")
    report_lines.append("🥤 Напої: Вода / Cola Zero / Чай / Кава без цукру — вільно.")
    
    final_report = "\n".join(report_lines)
    kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="food_home").as_markup()
    
    await callback.message.edit_text(
        f"👇 <b>Затисни пальцем блок нижче, скопіюй та відправ тренеру:</b>\n\n<code>{final_report}</code>", 
        parse_mode="HTML", reply_markup=kb
    )
    await callback.answer()