# FILE: ./bot/fritz_api.py
import asyncio
import io
import qrcode
from fritzconnection import FritzConnection
from config import FRITZ_IP, FRITZ_USER, FRITZ_PASS, WIFI_MAIN_SSID, WIFI_MAIN_PASS

def _get_fc() -> FritzConnection:
    if not FRITZ_PASS:
        raise ValueError("Пароль від Fritz!Box не вказано в .env")
    return FritzConnection(address=FRITZ_IP, user=FRITZ_USER, password=FRITZ_PASS, timeout=5.0)

def _generate_qr_sync():
    if not WIFI_MAIN_SSID or not WIFI_MAIN_PASS:
        return None
    qr_data = f"WIFI:T:WPA;S:{WIFI_MAIN_SSID};P:{WIFI_MAIN_PASS};;"
    img = qrcode.make(qr_data)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def _get_stats_sync() -> dict:
    try:
        fc = _get_fc()
        dsl = fc.call_action('WANDSLInterfaceConfig:1', 'GetInfo')
        down_mbps = dsl.get('NewDownstreamMaxRate', 0) / 1000
        up_mbps = dsl.get('NewUpstreamMaxRate', 0) / 1000
        
        try:
            ip_info = fc.call_action('WANPPPConnection:1', 'GetInfo')
            ext_ip = ip_info.get('NewExternalIPAddress', 'Невідомо')
        except:
            ext_ip = "Невідомо (IP Client)"
            
        return {"down": down_mbps, "up": up_mbps, "ip": ext_ip}
    except Exception as e:
        return {"error": str(e)}

def _get_devices_sync() -> list:
    try:
        fc = _get_fc()
        hosts_info = fc.call_action('Hosts:1', 'GetHostNumberOfEntries')
        total_hosts = hosts_info.get('NewHostNumberOfEntries', 0)
        
        active_devices = []
        for i in range(total_hosts):
            host = fc.call_action('Hosts:1', 'GetGenericHostEntry', NewIndex=i)
            if host.get('NewActive'):
                active_devices.append({
                    "name": host.get('NewHostName', 'Unknown'),
                    "ip": host.get('NewIPAddress', '-'),
                    "mac": host.get('NewMACAddress', '-')
                })
        return active_devices
    except Exception:
        return []

def _reboot_sync() -> bool:
    try:
        fc = _get_fc()
        fc.reboot()
        return True
    except Exception:
        return False

async def generate_wifi_qr(): return await asyncio.to_thread(_generate_qr_sync)
async def get_fritz_stats(): return await asyncio.to_thread(_get_stats_sync)
async def get_active_devices(): return await asyncio.to_thread(_get_devices_sync)
async def reboot_fritzbox(): return await asyncio.to_thread(_reboot_sync)