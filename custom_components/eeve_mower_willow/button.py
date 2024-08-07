import logging
import aiohttp
from homeassistant.components.button import ButtonEntity

from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    MANUFACTURER,
    MODEL,
    NAME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    ip_address = entry.data[CONF_IP_ADDRESS]
    buttons = [
        RebootControlButton(ip_address),
        StopControlButton(ip_address)
        ]
    async_add_entities(buttons)

class RebootControlButton(ButtonEntity):

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._unique_id = f"reboot_button_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        """Get information about this device."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def name(self):
        return "Reboot Mower"

    @property
    def icon(self):
        return "mdi:autorenew"

    async def async_press(self):
        _LOGGER.info(f"Rebooting mower with IP address {self._ip_address}")
        url = f"http://{self._ip_address}:8080/api/maintenance/reboot"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    _LOGGER.info(f"Reboot mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to reboot mower: {e}")

class StopControlButton(ButtonEntity):

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._unique_id = f"stop_button_{ip_address.replace('.', '_')}"  # Corrected unique_id
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        """Get information about this device."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def name(self):
        return "Stop Mower"

    @property
    def icon(self):
        return "mdi:stop"

    async def async_press(self):
        _LOGGER.info(f"Stopping mower with IP address {self._ip_address}")  # Corrected log message
        url = f"http://{self._ip_address}:8080/api/navigation/stop"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    _LOGGER.info(f"Stop mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to stop mower: {e}")