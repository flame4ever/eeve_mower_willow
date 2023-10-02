import logging
import aiohttp
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, CONF_IP_ADDRESS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    ip_address = entry.data[CONF_IP_ADDRESS]
    switches = [
                MowerControlSwitch(ip_address),
                DockControlSwitch(ip_address)
                 ]
    async_add_entities(switches)

class MowerControlSwitch(SwitchEntity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = False
        self._unique_id = f"mower_switch_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

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
    def name(self):
        return "Start Mowing"

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
        url = f"http://{self._ip_address}:8080/api/navigation/stop"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    self._state = response.status != 200
                    _LOGGER.info(f"Turn off mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to turn off mower: {e}")

    async def async_update(self):

        url = f"http://{self._ip_address}:8080/api/activities/info"
        headers = {"accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self._state = not (data.get("scheduledActivity") == "" and data.get("userActivity") == "")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to update mower state: {e}")

class DockControlSwitch(SwitchEntity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = False
        self._unique_id = f"dock_switch_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
 
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
    def name(self):
        return "Go back to the Dock"

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"Sending mower {self._ip_address} back to dock")
        url = f"http://{self._ip_address}:8080/api/navigation/startdocking"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    self._state = response.status == 200
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to send mower back to dock: {e}")

    async def async_turn_off(self, **kwargs):
        _LOGGER.info(f"Stop docking mower with IP address {self._ip_address}")
        url = f"http://{self._ip_address}:8080/api/navigation/stopdocking"
        headers = {"accept": "*/*"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, headers=headers) as response:
                    self._state = response.status != 200
                    _LOGGER.info(f"Stop docking mower response: {response.status}")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to Stop docking mower: {e}")

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/activities/info"
        headers = {"accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self._state = not (data.get("scheduledActivity") == "" and data.get("userActivity") == "")
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to update mower state: {e}")
