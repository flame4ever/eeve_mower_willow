import logging
import aiohttp
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, CONF_IP_ADDRESS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EEVE Mower switch from a config entry."""
    async_add_entities([MowerControlSwitch(entry.data[CONF_IP_ADDRESS])])

class MowerControlSwitch(SwitchEntity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = False
        self._unique_id = f"mower_{ip_address.replace('.', '_')}"
        _LOGGER.info(f"Initialized MowerControlSwitch with IP: {self._ip_address}")

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return self._unique_id

    @property
    def device_info(self):
        """Get information about this device."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": "Mower Control",
            "manufacturer": "EEVE",
            "model": "Willow",
            # "sw_version": "1.0",  # Optional: Software version
        }

    @property
    def name(self):
        return "Mower Control"

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"Turning on mower with IP address {self._ip_address}")
        url = f"http://{self._ip_address}:8080/api/navigation/startmowing?maxMowingTime=0"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    self._state = response.status == 200
                    _LOGGER.info(f"Turn on mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to turn on mower: {e}")

    async def async_turn_off(self, **kwargs):
        _LOGGER.info(f"Turning off mower with IP address {self._ip_address}")
        url = f"http://{self._ip_address}:8080/api/navigation/startdocking"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    self._state = response.status != 200
                    _LOGGER.info(f"Turn off mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to turn off mower: {e}")

    async def async_update(self):
        # Implement logic to update the state of the entity
        pass
