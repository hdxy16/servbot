import asyncio
from database.engine import init_db
from bot.services.memory_service import MemoryService


async def run_tests():
    await init_db()
    user_id = 999999

    tests = [
        "Запиши що 27.07 йду в міграційку",
        "Пароль від адмінки - 09045694856",
        "які у мене плани найближчим часом?",
        "Додай зустріч 2026-08-01T10:00:00 зустріч з командою",
        "який у мене пароль від адмінки?",
    ]

    for t in tests:
        print('\n>>> INPUT:', t)
        res = await MemoryService.process_input(user_id, t)
        print('RESULT:', res)

    stats = await MemoryService.get_stats(user_id)
    print('\nSTATS:', stats)

    nodes = await MemoryService.get_nodes_by_category(user_id, 'Інше')
    print('\nNODES (Інше):')
    for n in nodes:
        print('-', n.content)


if __name__ == '__main__':
    asyncio.run(run_tests())
