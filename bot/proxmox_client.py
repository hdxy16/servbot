# FILE: ./bot/proxmox_client.py
import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

class ProxmoxClient:
    def __init__(self):
        self.base_url = os.getenv("PVE_URL", "").rstrip('/') + '/api2/json'
        self.node = os.getenv("PVE_NODE", "pve")
        token_id = os.getenv("PVE_TOKEN_ID", "")
        token_secret = os.getenv("PVE_TOKEN_SECRET", "")
        
        self.headers = {
            "Authorization": f"PVEAPIToken={token_id}={token_secret}",
            "Accept": "application/json"
        }
        self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Вимикаємо перевірку SSL для локальних self-signed сертифікатів ноди
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(headers=self.headers, connector=connector)
        return self._session

    async def get_node_status(self) -> dict:
        url = f"{self.base_url}/nodes/{self.node}/status"
        try:
            async with self._get_session().get(url, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
                logger.error(f"PVE Node Status Error: {resp.status}")
                return {}
        except Exception as e:
            logger.error(f"PVE Node Connection failed: {e}")
            return {}

    async def get_resources(self) -> list:
        url = f"{self.base_url}/cluster/resources"
        try:
            async with self._get_session().get(url, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Фільтруємо лише віртуальні машини (qemu) та LXC контейнери
                    return [r for r in data.get("data", []) if r.get("type") in ["lxc", "qemu"]]
                return []
        except Exception as e:
            logger.error(f"PVE Resources failed: {e}")
            return []

    async def control_guest(self, guest_type: str, vmid: int, action: str) -> bool:
        # action: start, stop, shutdown, reboot
        # guest_type: lxc або qemu
        url = f"{self.base_url}/nodes/{self.node}/{guest_type}/{vmid}/status/{action}"
        try:
            async with self._get_session().post(url, timeout=5) as resp:
                return resp.status in [200, 201, 202]
        except Exception as e:
            logger.error(f"PVE Control failed for {vmid} ({action}): {e}")
            return False

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

pve_client = ProxmoxClient()