# FILE: ./bot/handlers_system.py
import logging
import asyncio
from datetime import timedelta
from aiogram import Router, types, F, Bot
from aiogram.enums import ButtonStyle
from bot.security import IsApproved
from config import ALLOWED_USER_ID
from bot.proxmox_client import pve_client
from bot.keyboards import pve_main_keyboard, pve_guest_control_keyboard

logger = logging.getLogger(__name__)
router = Router()

def _format_uptime(seconds: int) -> str:
    return str(timedelta(seconds=int(seconds)))

def _bytes_to_gb(bytes_val: int) -> float:
    return float(bytes_val or 0) / (1024 ** 3)

async def render_node_dashboard(user_id: int) -> tuple[str, list]:
    status = await pve_client.get_node_status()
    resources = await pve_client.get_resources()
    
    if not status:
        return "❌ <b>Не вдалося зв'язатися з Proxmox API.</b> Перевірте налаштування .env або працездатність токена.", []
        
    cpu = status.get("cpu", 0.0) * 100
    cpu_info = status.get("cpuinfo", {})
    
    memory = status.get("memory", {})
    mem_used = _bytes_to_gb(memory.get("used", 0))
    mem_total = _bytes_to_gb(memory.get("total", 1))
    
    root_fs = status.get("rootfs", {})
    disk_used = _bytes_to_gb(root_fs.get("used", 0))
    disk_total = _bytes_to_gb(root_fs.get("total", 1))
    
    uptime = _format_uptime(status.get("uptime", 0))
    pve_version = status.get("pveversion", "N/A")

    text = (
        f"🖥️ <b>SYSTEM NODE CONTROL | THINKCENTRE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ ОС: <b>Proxmox VE {pve_version}</b>\n"
        f"⏱️ Uptime ноди: <code>{uptime}</code>\n\n"
        f"📊 <b>Завантаження ресурсів заліза:</b>\n"
        f"  ▫️ Процесор: <b>{cpu:.1f}%</b> ({cpu_info.get('cpus', 1)} Cores)\n"
        f"  ▫️ Пам'ять RAM: <b>{mem_used:.2f} GB</b> / {mem_total:.1f} GB\n"
        f"  ▫️ Системний SSD: <b>{disk_used:.1f} GB</b> / {disk_total:.1f} GB\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Локальні суб-вузли (Containers/VMs):</b>"
    )
    return text, resources

@router.message(F.text == "🖥️ Сервер", IsApproved())
async def cmd_system_main(message: types.Message):
    if message.from_user.id != ALLOWED_USER_ID: return
    msg = await message.answer("⏳ Зчитую телеметрію з Proxmox...")
    text, resources = await render_node_dashboard(message.from_user.id)
    await msg.edit_text(text, reply_markup=pve_main_keyboard(resources), parse_mode="HTML")

@router.callback_query(F.data == "sys_refresh", IsApproved())
async def cal_system_refresh(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID: return
    text, resources = await render_node_dashboard(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=pve_main_keyboard(resources), parse_mode="HTML")
    except Exception: pass
    await callback.answer()

@router.callback_query(F.data.startswith("sys_view_"), IsApproved())
async def cal_system_view_guest(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID: return
    _, _, gtype, vmid_str = callback.data.split("_")
    vmid = int(vmid_str)
    
    resources = await pve_client.get_resources()
    guest = next((r for r in resources if r.get("vmid") == vmid), None)
    
    if not guest:
        return await callback.answer("Вузол не знайдено в поточному пулі ресурсу.", show_alert=True)
        
    g_cpu = guest.get("cpu", 0.0) * 100
    g_mem = _bytes_to_gb(guest.get("mem", 0))
    g_maxmem = _bytes_to_gb(guest.get("maxmem", 0))
    status_emoji = "🟢 Працює (Running)" if guest.get("status") == "running" else "🔴 Зупинено (Stopped)"

    text = (
        f"📦 <b>Вузол ID: {vmid} — {guest.get('name')}</b>\n"
        f"Тип архітектури: <b>{gtype.upper()}</b>\n"
        f"Поточний статус: {status_emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Споживання виділених лімітів:</b>\n"
        f"  ▫️ Навантаження CPU: <b>{g_cpu:.1f}%</b>\n"
        f"  ▫️ Використання RAM: <b>{g_mem:.2f} GB</b> / {g_maxmem:.1f} GB\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Керування станом живлення вузла:</b>"
    )
    await callback.message.edit_text(text, reply_markup=pve_guest_control_keyboard(vmid, gtype), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("sys_act_"), IsApproved())
async def cal_system_action_guest(callback: types.CallbackQuery):
    if callback.from_user.id != ALLOWED_USER_ID: return
    _, _, gtype, vmid_str, action = callback.data.split("_")
    vmid = int(vmid_str)
    
    await callback.message.edit_text(f"⏳ Надсилаю команду ACPI <code>{action}</code> на вузол {vmid}...", parse_mode="HTML")
    ok = await pve_client.control_guest(gtype, vmid, action)
    
    if ok:
        await callback.answer(f"Команда {action} успішно передана!", show_alert=False)
    else:
        await callback.answer(f"❌ Помилка виконання команди {action} гіпервізором.", show_alert=True)
        
    await asyncio.sleep(1.5) # Даємо Proxmox змінити стейт перед рендером
    text, resources = await render_node_dashboard(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=pve_main_keyboard(resources), parse_mode="HTML")