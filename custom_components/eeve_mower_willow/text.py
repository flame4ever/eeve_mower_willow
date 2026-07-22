"""Text entities for EEVE Mower Willow.

MowerNameText  – Name des Mähers (frei wählbar).
                 GET/POST /settings/identity/name
                 Antwort/Body: JSON string
"""
from __future__ import annotations

import logging
import json
import aiohttp

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower text entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    async_add_entities([MowerNameText(ip_address)])


# ---------------------------------------------------------------------------
# Mower name text entity
# ---------------------------------------------------------------------------

class MowerNameText(TextEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mower_name"
    """Editable name of the mower (shown in the EEVE app).

    GET  /settings/identity/name  → JSON string
    POST /settings/identity/name  → Body: JSON string
    """

    _attr_icon = "mdi:robot-mower"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 1
    _attr_native_max = 64

    _ENDPOINT = "/settings/identity/name"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: str = "EEVE Mower"
        self._attr_unique_id = f"mower_name_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    async def async_update(self) -> None:
        """Read current mower name from the device."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, str) and value:
                            self._attr_native_value = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read mower name: %s", exc)

    async def async_set_value(self, value: str) -> None:
        """Send new mower name to the device."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(value),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._attr_native_value = value
                        self.async_write_ha_state()
                        _LOGGER.info("Mower name set to '%s'", value)
                    else:
                        _LOGGER.error(
                            "Set mower name failed: HTTP %s", resp.status
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set mower name failed: %s", exc)
