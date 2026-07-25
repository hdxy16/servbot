import asyncio
import sys
from pathlib import Path

# Додаємо корінь проєкту в sys.path
sys.path.append(str(Path(__file__).parent.parent))

from database.engine import AsyncSessionLocal
from database.models import FoodProduct


PRODUCTS = {
    # ========== БІЛОК ==========
    "protein": [
        # Птиця
        {"name": "Куряче філе", "portion_size": 160},
        {"name": "Стегно курки без шкіри", "portion_size": 110},
        {"name": "Філе індички", "portion_size": 160},
        {"name": "Стегно індички без шкіри", "portion_size": 110},
        # Яловичина та інше м'ясо
        {"name": "Телятина", "portion_size": 150},
        {"name": "Вирізка свинини", "portion_size": 140},
        {"name": "Печінка куряча", "portion_size": 170},
        {"name": "Печінка яловича", "portion_size": 170},
        # Біла риба
        {"name": "Хек", "portion_size": 190},
        {"name": "Мінтай", "portion_size": 190},
        {"name": "Тріска", "portion_size": 190},
        {"name": "Судак", "portion_size": 190},
        {"name": "Пікша", "portion_size": 190},
        {"name": "Окунь", "portion_size": 190},
        {"name": "Щука", "portion_size": 190},
        {"name": "Тілапія", "portion_size": 190},
        {"name": "Тунець у власному соку", "portion_size": 200},
        # Жирна риба
        {"name": "Лосось", "portion_size": 100},
        {"name": "Форель", "portion_size": 100},
        {"name": "Скумбрія", "portion_size": 100},
        {"name": "Оселедець", "portion_size": 100},
        {"name": "Сардина", "portion_size": 110},
        {"name": "Тунець", "portion_size": 100},
        # Морепродукти
        {"name": "Креветки", "portion_size": 180},
        {"name": "Мідії без олії", "portion_size": 220},
        {"name": "Восьминіг", "portion_size": 180},
        # Яйця
        {"name": "Курячі яйця", "portion_size": 3, "unit": "шт"},
        # Молочні продукти
        {"name": "Сир кисломолочний 0%", "portion_size": 220},
        {"name": "Сир кисломолочний 2%", "portion_size": 200},
        {"name": "Сир кисломолочний 5%", "portion_size": 180},
        {"name": "Сир твердий", "portion_size": 50},
        {"name": "Грецький йогурт", "portion_size": 330},
        {"name": "Йогурт до 3%", "portion_size": 330},
        {"name": "Кефір до 3%", "portion_size": 400, "unit": "мл"},
        {"name": "Молоко до 2.5%", "portion_size": 400, "unit": "мл"},
    ],
    
    # ========== ВУГЛЕВОДИ ==========
    "carbs": [
        # Крупи
        {"name": "Рис", "portion_size": 50},
        {"name": "Гречка", "portion_size": 50},
        {"name": "Булгур", "portion_size": 50},
        {"name": "Кус-кус", "portion_size": 50},
        {"name": "Перловка", "portion_size": 50},
        {"name": "Ячна крупа", "portion_size": 50},
        {"name": "Пшоняна крупа", "portion_size": 50},
        {"name": "Вівсяні пластівці", "portion_size": 50},
        {"name": "Кукурудзяна крупа", "portion_size": 55},
        {"name": "Манка", "portion_size": 50},
        {"name": "Кіноа", "portion_size": 50},
        # Макарони
        {"name": "Макарони", "portion_size": 50},
        {"name": "Цільнозернові макарони", "portion_size": 50},
        {"name": "Локшина", "portion_size": 50},
        # Хліб
        {"name": "Лаваш", "portion_size": 70},
        {"name": "Цільнозерновий хліб", "portion_size": 70},
        {"name": "Житній хліб", "portion_size": 70},
        {"name": "Хлібці", "portion_size": 60},
        # Крохмалисті овочі
        {"name": "Картопля", "portion_size": 225},
        {"name": "Батат", "portion_size": 225},
        {"name": "Кукурудза", "portion_size": 250},
        # Бобові
        {"name": "Квасоля", "portion_size": 150},
        {"name": "Нут", "portion_size": 150},
        {"name": "Горох", "portion_size": 200},
        {"name": "Сочевиця", "portion_size": 70},
    ],
    
    # ========== ЖИРИ ==========
    "fats": [
        {"name": "Олія (будь-яка)", "portion_size": 15},
        {"name": "Авокадо", "portion_size": 80},
        {"name": "Маслини", "portion_size": 50},
        {"name": "Оливки", "portion_size": 50},
        {"name": "Майонез", "portion_size": 20},
        {"name": "Кетчуп", "portion_size": 50},
        {"name": "Горіхи (будь-які)", "portion_size": 25},
        {"name": "Насіння (будь-яке)", "portion_size": 25},
        {"name": "Арахісова паста", "portion_size": 25},
        {"name": "Тахіні", "portion_size": 25},
    ],
    
    # ========== ФРУКТИ ==========
    "fruits": [
        {"name": "Яблуко", "portion_size": 300},
        {"name": "Груша", "portion_size": 300},
        {"name": "Апельсин", "portion_size": 300},
        {"name": "Мандарини", "portion_size": 300},
        {"name": "Ківі", "portion_size": 300},
        {"name": "Персик", "portion_size": 300},
        {"name": "Абрикос", "portion_size": 300},
        {"name": "Сливи", "portion_size": 300},
        {"name": "Полуниця", "portion_size": 300},
        {"name": "Малина", "portion_size": 300},
        {"name": "Чорниця", "portion_size": 300},
        {"name": "Вишня", "portion_size": 300},
        {"name": "Черешня", "portion_size": 300},
        {"name": "Ананас", "portion_size": 300},
        {"name": "Кавун", "portion_size": 300},
        {"name": "Диня", "portion_size": 300},
        {"name": "Грейпфрут", "portion_size": 300},
        {"name": "Лимон", "portion_size": 300},
        {"name": "Банан", "portion_size": 150},
        {"name": "Манго", "portion_size": 180},
        {"name": "Хурма", "portion_size": 200},
        {"name": "Виноград", "portion_size": 180},
        {"name": "Фініки", "portion_size": 70},
    ],
    
    # ========== ОВОЧІ (без порцій, грами) ==========
    "vegetable": [
        {"name": "Огірки", "portion_size": 100},
        {"name": "Помідори", "portion_size": 100},
        {"name": "Капуста", "portion_size": 100},
        {"name": "Цвітна капуста", "portion_size": 100},
        {"name": "Броколі", "portion_size": 100},
        {"name": "Цукіні", "portion_size": 100},
        {"name": "Баклажани", "portion_size": 100},
        {"name": "Перець солодкий", "portion_size": 100},
        {"name": "Морква", "portion_size": 100},
        {"name": "Буряк", "portion_size": 100},
        {"name": "Цибуля", "portion_size": 100},
        {"name": "Часник", "portion_size": 100},
        {"name": "Зелень", "portion_size": 100},
        {"name": "Салат", "portion_size": 100},
        {"name": "Шпинат", "portion_size": 100},
        {"name": "Редис", "portion_size": 100},
        {"name": "Селера", "portion_size": 100},
        {"name": "Спаржа", "portion_size": 100},
    ],
}


async def seed_products():
    """Додає продукти в базу даних."""
    async with AsyncSessionLocal() as session:
        for category, products in PRODUCTS.items():
            for product_data in products:
                # Перевіряємо, чи існує вже такий продукт
                from sqlalchemy import select
                stmt = select(FoodProduct).where(
                    FoodProduct.category == category,
                    FoodProduct.name == product_data["name"]
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                
                if existing:
                    print(f"⏭️ Пропущено (вже існує): {category} - {product_data['name']}")
                    continue
                
                product = FoodProduct(
                    category=category,
                    name=product_data["name"],
                    portion_size=product_data["portion_size"],
                    unit=product_data.get("unit", "г")
                )
                session.add(product)
                print(f"✅ Додано: {category} - {product_data['name']} ({product_data['portion_size']} {product_data.get('unit', 'г')})")
        
        await session.commit()
        print(f"\n🎉 Всього додано продуктів: {sum(len(p) for p in PRODUCTS.values())}")


if __name__ == "__main__":
    asyncio.run(seed_products())