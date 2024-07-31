import logging

from homeassistant.components.camera import Camera
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    MANUFACTURER,
    MODEL,
    NAME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EEVE Mower camera from a config entry."""
    async_add_entities([MowerCamera(entry.data[CONF_IP_ADDRESS])])

class MowerCamera(Camera):
    def __init__(self, ip_address):
        super().__init__()
        self._ip_address = ip_address
        self._name = "Mower Camera"
        self._unique_id = f"mower_camera_{ip_address.replace('.', '_')}"
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
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            # "sw_version": "1.0",  # Optional: Software version
        }
    
    @property
    def entity_picture(self):
        """Return a picture to use of the entity in the frontend."""
        return f"http://{self._ip_address}:8080/image/front/img.jpg"

    async def async_camera_image(self):
        url = f"http://{self._ip_address}:8080/image/front/img.jpg"
        session = aiohttp_client.async_get_clientsession(self.hass)
        async with session.get(url) as response:
            return await response.read()