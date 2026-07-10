# FILE: ./bot/home_assistant.py
import logging
import aiohttp
import re
from typing import Optional
from config import HA_URL, HA_TOKEN

logger = logging.getLogger(__name__)

# Entity ID хелперів будильника. Їх треба один раз створити в Home Assistant:
# Settings -> Devices & Services -> Helpers -> Add Helper
#   1. Toggle -> назва "smart_alarm_enabled"
#   2. Date and/or time (тільки Time) -> назва "smart_alarm_time"
ALARM_ENABLED_ENTITY = "input_boolean.smart_alarm_enabled"
ALARM_TIME_ENTITY = "input_datetime.smart_alarm_time"

LIGHT_ENTITY_ALIASES = {
    "ванн": "light.bathroom_light_ceiling",
    "коридор": "light.hallway_lights",
    "спальн": "light.bedroom_light_floor",
    "вітальн": "light.livingroom_light_floor",
}

LIGHT_ENTITIES = list(LIGHT_ENTITY_ALIASES.values())

LIGHT_COLOR_ALIASES = {
    "червон": "red",
    "зелений": "green",
    "синій": "blue",
    "жовт": "yellow",
    "пурпур": "purple",
    "білий": "white",
    "white": "white",
}

LIGHT_COLOR_DISPLAY = {
    "red": "червоний",
    "green": "зелений",
    "blue": "синій",
    "yellow": "жовтий",
    "purple": "пурпурний",
    "white": "білий",
}

TEMPERATURE_SENSOR_ALIASES = {
    "кухн": "sensor.kitchen_sensor_climate_temperature",
    "ванн": "sensor.bathroom_sensor_climate_temperature",
}

HUMIDITY_SENSOR_ALIASES = {
    "кухн": "sensor.kitchen_sensor_climate_humidity",
    "ванн": "sensor.bathroom_sensor_climate_humidity",
}


class HomeAssistantClient:
    """
    Клієнт для роботи з Home Assistant REST API.
    Використовує ОДНУ persistent aiohttp-сесію замість створення нової на
    кожен запит — стабільніше і швидше при частих зверненнях.
    """

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        }
        self.base_url = f"{HA_URL}/api"
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_entity_state(self, entity_id: str) -> dict:
        url = f"{self.base_url}/states/{entity_id}"
        try:
            async with self._get_session().get(url, timeout=aiohttp.ClientTimeout(total=4)) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning("HA get_entity_state(%s): статус %s", entity_id, response.status)
                return {"state": "unknown", "attributes": {}}
        except Exception as e:
            logger.error("HA get_entity_state(%s) помилка: %s", entity_id, e)
            return {"state": "error", "attributes": {}}

    async def toggle_device(self, domain: str, service: str, entity_id: str) -> bool:
        url = f"{self.base_url}/services/{domain}/{service}"
        data = {"entity_id": entity_id}
        try:
            async with self._get_session().post(url, json=data, timeout=aiohttp.ClientTimeout(total=4)) as response:
                if response.status != 200:
                    logger.warning("HA toggle_device(%s): статус %s", entity_id, response.status)
                return response.status == 200
        except Exception as e:
            logger.error("HA toggle_device(%s) помилка: %s", entity_id, e)
            return False

    async def set_light_state(
        self,
        entity_id: str,
        brightness_pct: int = None,
        color_name: str = None,
        kelvin: int = None,
    ) -> bool:
        url = f"{self.base_url}/services/light/turn_on"
        data = {"entity_id": entity_id}

        if brightness_pct is not None:
            data["brightness_pct"] = brightness_pct

        if color_name is not None:
            colors = {
                "red": [255, 0, 0],
                "green": [0, 255, 0],
                "blue": [0, 0, 255],
                "yellow": [255, 255, 0],
                "purple": [128, 0, 128],
            }
            if color_name in colors:
                data["rgb_color"] = colors[color_name]

        if kelvin is not None:
            data["color_temp_kelvin"] = kelvin

        try:
            async with self._get_session().post(url, json=data, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    logger.warning("HA set_light_state(%s): статус %s", entity_id, response.status)
                return response.status == 200
        except Exception as e:
            logger.error("HA set_light_state(%s) помилка: %s", entity_id, e)
            return False

    async def set_alarm_time(self, time_str: str) -> bool:
        url = f"{self.base_url}/services/input_datetime/set_datetime"
        data = {"entity_id": ALARM_TIME_ENTITY, "time": time_str}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data, timeout=4) as response:
                    return response.status == 200
            except Exception:
                return False

    async def toggle_alarm(self, state: str) -> bool:
        url = f"{self.base_url}/services/input_boolean/{state}"
        data = {"entity_id": ALARM_ENABLED_ENTITY}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=data, timeout=4) as response:
                    return response.status == 200
            except Exception:
                return False

    @staticmethod
    def _find_light_entity(text: str) -> Optional[str]:
        lower = text.lower()
        for alias, entity in LIGHT_ENTITY_ALIASES.items():
            if alias in lower:
                return entity
        return None

    @staticmethod
    def _is_global_light_target(text: str) -> bool:
        lower = text.lower()
        if "світл" not in lower and "светл" not in lower and "light" not in lower:
            return False

        return any(
            keyword in lower
            for keyword in [
                "всі",
                "усі",
                "все",
                "весь",
                "всій",
                "всіх",
                "в кожній",
                "на всій",
                "на все",
                "по всій",
                "по всьому",
                "в квартирі",
                "квартирі",
                "дома",
                "дому",
                "домі",
                "будинку",
                "будинок",
                "квартира",
                "квартири",
                "кімнатах",
                "кожній",
            ]
        )

    @staticmethod
    def _find_color(text: str) -> Optional[str]:
        lower = text.lower()
        for alias, name in LIGHT_COLOR_ALIASES.items():
            if alias in lower:
                return name
        return None

    @staticmethod
    def _find_time(text: str) -> Optional[str]:
        match = re.search(r"(\d{1,2}):(\d{2})", text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
        else:
            match = re.search(r"(\d{1,2})\s*год", text)
            if not match:
                return None
            hour = int(match.group(1))
            minute = 0

        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d}:00"
        return None

    async def interpret_command(self, text: str) -> dict:
        lower = text.lower()
        result = {"action": None, "entity": None, "value": None, "message": None}

        if any(k in lower for k in ["увімкни", "включи", "вкл", "включити", "запали", "ввімкни", "turn on", "on"]):
            light = self._find_light_entity(text)
            if light:
                color = self._find_color(text)
                result.update({"action": "light_on", "entity": light, "value": color or True})
                result["message"] = "Увімкнути світло."
                return result
            if self._is_global_light_target(text):
                color = self._find_color(text)
                result.update({"action": "light_on_all", "value": color or True})
                result["message"] = "Увімкнути всі світла."
                return result

        if any(k in lower for k in ["вимкни", "выключи", "викл", "вимкнути", "гаси", "гасни", "turn off", "off"]):
            light = self._find_light_entity(text)
            if light:
                result.update({"action": "light_off", "entity": light, "value": False})
                result["message"] = "Вимкнути світло."
                return result
            if self._is_global_light_target(text):
                result.update({"action": "light_off_all", "value": False})
                result["message"] = "Вимкнути всі світла."
                return result

        if any(k in lower for k in ["колір", "кольор", "red", "blue", "green", "жовт", "син", "червон", "зелений", "purple"]):
            light = self._find_light_entity(text)
            color = self._find_color(text)
            if light and color:
                result.update({"action": "light_color", "entity": light, "value": color})
                result["message"] = f"Змінити колір світла на {color}."
                return result

        if any(k in lower for k in ["температур", "вологіст", "датчик", "sensor"]):
            sensor = None
            for alias, entity in TEMPERATURE_SENSOR_ALIASES.items():
                if alias in lower:
                    sensor = entity
                    break
            if not sensor:
                for alias, entity in HUMIDITY_SENSOR_ALIASES.items():
                    if alias in lower:
                        sensor = entity
                        break
            if sensor:
                result.update({"action": "sensor_read", "entity": sensor})
                result["message"] = "Запитати стан сенсора."
                return result

        if "будильник" in lower or "alarm" in lower:
            if "вимк" in lower or "викл" in lower:
                result.update({"action": "alarm_off", "message": "Вимкнути будильник."})
                return result
            time_str = self._find_time(text)
            if time_str:
                result.update({"action": "alarm_set", "value": time_str, "message": f"Встановити будильник на {time_str[:5]}."})
                return result
            result.update({"action": "alarm_on", "message": "Увімкнути будильник."})
            return result

        return result

    async def execute_command(self, command: dict) -> str:
        action = command.get("action")
        entity = command.get("entity")
        value = command.get("value")

        if action == "light_on" and entity:
            if isinstance(value, str):
                ok = await self.set_light_state(entity, color_name=value)
                color_name = LIGHT_COLOR_DISPLAY.get(value, value)
                return f"✅ Світло увімкнено і встановлено на {color_name}." if ok else "⚠️ Не вдалося ввімкнути світло."
            ok = await self.toggle_device("light", "turn_on", entity)
            return "✅ Світло увімкнено." if ok else "⚠️ Не вдалося ввімкнути світло."

        if action == "light_off" and entity:
            ok = await self.toggle_device("light", "turn_off", entity)
            return "✅ Світло вимкнено." if ok else "⚠️ Не вдалося вимкнути світло."

        if action == "light_on_all":
            color = value if isinstance(value, str) else None
            results = []
            for entity_id in LIGHT_ENTITIES:
                if color:
                    results.append(await self.set_light_state(entity_id, color_name=color))
                else:
                    results.append(await self.toggle_device(entity_id.split(".")[0], "turn_on", entity_id))
            ok = all(results)
            if ok:
                if color:
                    color_name = LIGHT_COLOR_DISPLAY.get(color, color)
                    return f"✅ Усе освітлення увімкнено на {color_name}."
                return "✅ Усе освітлення увімкнено."
            return "⚠️ Не вдалося виконати команду для усього освітлення."

        if action == "light_off_all":
            results = [await self.toggle_device(entity.split(".")[0], "turn_off", entity) for entity in LIGHT_ENTITIES]
            ok = all(results)
            return "✅ Усе освітлення вимкнено." if ok else "⚠️ Не вдалося виконати команду для усього освітлення."

        if action == "light_color" and entity and isinstance(value, str):
            ok = await self.set_light_state(entity, color_name=value)
            return "✅ Колір світла змінено." if ok else "⚠️ Не вдалося змінити колір світла."

        if action == "sensor_read" and entity:
            state = await self.get_entity_state(entity)
            attribute = state.get("attributes", {}) if isinstance(state, dict) else {}
            return f"📊 {entity}: {state.get('state', 'Н/Д')} {attribute.get('unit_of_measurement', '')}".strip()

        if action == "alarm_set" and value:
            ok = await self.set_alarm_time(value)
            if ok:
                await self.toggle_alarm("turn_on")
                return f"✅ Будильник встановлено на {value[:5]}."
            return "⚠️ Не вдалося встановити будильник."

        if action == "alarm_on":
            ok = await self.toggle_alarm("turn_on")
            return "✅ Будильник увімкнено." if ok else "⚠️ Не вдалося ввімкнути будильник."

        if action == "alarm_off":
            ok = await self.toggle_alarm("turn_off")
            return "✅ Будильник вимкнено." if ok else "⚠️ Не вдалося вимкнути будильник."

        return "Не вдалося інтерпретувати команду HA."

ha_client = HomeAssistantClient()
