"""Switch entities for EEVE Mower Willow.

MowDaySwitch (x7)  - Wochentag-Maehplanung (Montag-Sonntag).
                     GET/POST /settings/mowingPlanner/mowOn{Day}
                     Antwort/Body: JSON boolean (true / false)

Damit laesst sich der taegliche Maehplan direkt aus HA oder Automationen steuern,
z. B. an Regentagen abschalten oder vor Partys am Wochenende deaktivieren.
"""
from __future__ import annotations

import logging
import aiohttp

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME

_LOGGER = logging.getLogger(__name__)

# (HA-Anzeigename, API-Schluessel im Pfad)
_DAYS = [
    ("Monday",    "mowOnMonday"),
    ("Tuesday",   "mowOnTuesday"),
    ("Wednesday", "mowOnWednesday"),
    ("Thursday",  "mowOnThursday"),
    ("Friday",    "mowOnFriday"),
    ("Saturday",  "mowOnSaturday"),
    ("Sunday",    "mowOnSunday"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower switch entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    entities = [
        MowDaySwitch(ip_address, display_name, api_key)
        for display_name, api_key in _DAYS
    ]
    entities.append(BeaconsSwitch(ip_address))
    entities.append(AutoAnnotationSwitch(ip_address))
    async_add_entities(entities)


class MowDaySwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    """Ein Schalter pro Wochentag, der den Maeher an diesem Tag aktiviert/deaktiviert.

    GET  /settings/mowingPlanner/mowOn{Day}  -> JSON boolean
    POST /settings/mowingPlanner/mowOn{Day}  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:calendar-check"

    def __init__(self, ip_address: str, display_name: str, api_key: str) -> None:
        self._ip_address = ip_address
        self._display_name = display_name
        self._api_key = api_key
        self._state: bool = True
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"mow_{api_key.lower()}_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"
        self._attr_translation_key = f"mow_on_{display_name.lower()}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_update(self) -> None:
        """Read the current mowing day setting from the mower."""
        url = f"http://{self._ip_address}:8080/settings/mowingPlanner/{self._api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read mow day %s: %s", self._display_name, exc)

    async def _set_day(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/mowingPlanner/{self._api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("Mow on %s -> %s", self._display_name, enabled)
                    else:
                        _LOGGER.error(
                            "Set mow day %s failed: HTTP %s",
                            self._display_name,
                            resp.status,
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set mow day %s failed: %s", self._display_name, exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_day(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_day(False)


# ---------------------------------------------------------------------------
# Beacons switch
# ---------------------------------------------------------------------------

class BeaconsSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "starlight_beacons"
    """Toggles the StarLight LED beacon on/off.

    GET  /settings/beacons/enabled  -> JSON boolean
    POST /settings/beacons/enabled  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:lightbulb-group"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"beacons_enabled_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_update(self) -> None:
        """Read the current beacon state from the mower."""
        url = f"http://{self._ip_address}:8080/settings/beacons/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read beacons enabled: %s", exc)

    async def _set_beacons(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/beacons/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("StarLight Beacons -> %s", enabled)
                    else:
                        _LOGGER.error(
                            "Set beacons enabled failed: HTTP %s", resp.status
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set beacons enabled failed: %s", exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_beacons(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_beacons(False)


# ---------------------------------------------------------------------------
# Auto annotation switch
# ---------------------------------------------------------------------------

class AutoAnnotationSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "auto_annotation"
    """Toggles AI auto-annotation of obstacles on/off.

    GET  /settings/autoAnnotation/enabled  -> JSON boolean
    POST /settings/autoAnnotation/enabled  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:robot"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"auto_annotation_enabled_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_update(self) -> None:
        """Read the current auto-annotation state from the mower."""
        url = f"http://{self._ip_address}:8080/settings/autoAnnotation/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read auto annotation enabled: %s", exc)

    async def _set_auto_annotation(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/autoAnnotation/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("Auto Annotation -> %s", enabled)
                    else:
                        _LOGGER.error(
                            "Set auto annotation enabled failed: HTTP %s", resp.status
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set auto annotation enabled failed: %s", exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_auto_annotation(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_auto_annotation(False)
