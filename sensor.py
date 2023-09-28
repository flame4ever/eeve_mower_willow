import logging
import aiohttp
from homeassistant.helpers.entity import Entity
from homeassistant.const import PERCENTAGE
from .const import DOMAIN, CONF_IP_ADDRESS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EEVE Mower battery sensor from a config entry."""
    async_add_entities([BatterySensor(entry.data[CONF_IP_ADDRESS])])

class BatterySensor(Entity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._unique_id = f"battery_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return "Mower Battery"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        """Get information about this device."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": "EEVE Mower",
            "manufacturer": "EEVE",
            "model": "Willow",
        }

    @property
    def unit_of_measurement(self):
        return PERCENTAGE

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/batteryStatus"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self._state = data.get("percentage")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to update battery status: {e}")
