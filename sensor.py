import logging
import aiohttp
from homeassistant.helpers.entity import Entity
from homeassistant.const import PERCENTAGE
from .const import DOMAIN, CONF_IP_ADDRESS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EEVE Mower battery sensor from a config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    async_add_entities([BatterySensor(ip_address), ActiveSensor(ip_address)])

class BatterySensor(Entity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Mower Battery"
        self._unique_id = f"battery_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

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
    def icon(self):
        return "mdi:battery"

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

class ActiveSensor(Entity):
    """Representation of a Tool sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address  # Initialize the IP address
        self._state = None
        self._name = "Mower activities"
        self._unique_id = f"mower_activities_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

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
    def state(self):
        return self._state

    async def async_update(self):
        """Fetch new state data for the sensor."""
        url = f"http://{self._ip_address}:8080/api/toolplanner/status"  # Corrected indentation and quote
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        for tool in data['tools']:
                            if tool['active']:
                                self._state = tool['name']
                                break
                        else:
                            self._state = "no activities"
                    else:
                        _LOGGER.error(f"Failed to fetch data: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch data: {e}")
