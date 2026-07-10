import asyncio
from aiogram import Router, F, types, Bot
from aiogram.types import BufferedInputFile
from bot.security import HasPermission
from bot.keyboards import wifi_main_keyboard
from bot.fritz_api import generate_wifi_qr, get_fritz_stats, get_active_devices, reboot_fritzbox

router = Router()

async def switch_to_loading(message: types.Message, text: str) -> types.Message:
    if message.photo:
        await message.delete()
        return await message.answer(text, parse_mode="HTML")
    else:
        await message.edit_text(text, parse_mode="HTML")
        return message

@router.message(F.text == "🌐 Мережа", HasPermission("wifi"))
async def process_menu_wifi(message: types.Message):
    await message.answer("🌐 <b>Керування Мережею (Fritz!Box):</b>", reply_markup=wifi_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "wifi_main_menu", HasPermission("wifi"))
async def process_network_main_menu(callback: types.CallbackQuery):
    await switch_to_loading(callback.message, "🌐 <b>Керування Мережею (Fritz!Box):</b>")
    await callback.message.edit_reply_markup(reply_markup=wifi_main_keyboard())
    await callback.answer()

# ==========================================
# FRITZ!BOX ХЕНДЛЕРИ
# ==========================================
@router.callback_query(F.data == "wifi_qr", HasPermission("wifi"))
async def process_wifi_qr(callback: types.CallbackQuery):
    msg = await switch_to_loading(callback.message, "⏳ Генерую QR-код основного Wi-Fi...")
    qr_buffer = await generate_wifi_qr()
    
    if not qr_buffer:
        await msg.edit_text("❌ SSID або пароль не вказано в .env", reply_markup=wifi_main_keyboard())
        return await callback.answer()
        
    photo = BufferedInputFile(qr_buffer.read(), filename="wifi_qr.png")
    await msg.delete()
    await msg.answer_photo(
        photo=photo, 
        caption="🛜 <b>Основний Wi-Fi</b>\nДай гостю відсканувати цей код для миттєвого підключення.",
        parse_mode="HTML",
        reply_markup=wifi_main_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "wifi_stats", HasPermission("wifi"))
async def process_wifi_stats(callback: types.CallbackQuery):
    msg = await switch_to_loading(callback.message, "⏳ Запитую дані у Fritz!Box...")
    stats = await get_fritz_stats()
    
    if "error" in stats:
        await msg.edit_text(f"❌ Помилка: {stats['error']}", reply_markup=wifi_main_keyboard())
        return await callback.answer()
        
    text = (
        f"📊 <b>Статистика Лінії:</b>\n\n"
        f"🌍 Зовнішній IP: <code>{stats['ip']}</code>\n"
        f"⬇️ Синхронізація (Вхідна): <b>{stats['down']:.1f} Mbps</b>\n"
        f"⬆️ Синхронізація (Вихідна): <b>{stats['up']:.1f} Mbps</b>"
    )
    await msg.edit_text(text, parse_mode="HTML", reply_markup=wifi_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "wifi_devices", HasPermission("wifi"))
async def process_wifi_devices(callback: types.CallbackQuery):
    msg = await switch_to_loading(callback.message, "⏳ Сканую локальну мережу...")
    devices = await get_active_devices()
    
    if not devices:
        await msg.edit_text("❌ Жодного пристрою не знайдено або помилка.", reply_markup=wifi_main_keyboard())
        return await callback.answer()
        
    text = f"📱 <b>Підключено пристроїв: {len(devices)}</b>\n\n"
    for d in devices:
        text += f"• <b>{d['name']}</b> (<code>{d['ip']}</code>)\n"
        
    await msg.edit_text(text, parse_mode="HTML", reply_markup=wifi_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "wifi_reboot", HasPermission("wifi"))
async def process_wifi_reboot(callback: types.CallbackQuery):
    msg = await switch_to_loading(callback.message, "⏳ Відправляю команду перезавантаження...")
    success = await reboot_fritzbox()
    
    if success:
        await msg.edit_text("🔄 <b>Команда надіслана.</b> Роутер перезавантажується. Інтернет зникне на 2-3 хвилини.", parse_mode="HTML", reply_markup=wifi_main_keyboard())
    else:
        await msg.edit_text("❌ Помилка відправки команди.", reply_markup=wifi_main_keyboard())
    await callback.answer()