import logging
import aiohttp
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

class GPSSensor(Entity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._latitude = None
        self._longitude = None
        self._accuracy = None
        self._datetime = None
        self._num_satellites = None
        self._speed = None
        self._status = None
        self._attr_should_poll = True

    async def async_update(self):
        """Fetch the latest GPS data from the device."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{self._ip_address}:8080/api/statuslog/sensors/gps"
                headers = {'accept': 'application/json'}
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self._latitude = data.get("latitude")
                    self._longitude = data.get("longitude")
                    self._accuracy = data.get("accuracy")
                    self._datetime = data.get("datetime")
                    self._num_satellites = data.get("numSatellites")
                    self._speed = data.get("speed")
                    self._status = data.get("status")
        except Exception as e:
            _LOGGER.error(f"Error fetching GPS data: {e}")

    @property
    def latitude(self):
        return self._latitude

    @property
    def longitude(self):
        return self._longitude

    @property
    def accuracy(self):
        return self._accuracy

    @property
    def datetime(self):
        return self._datetime

    @property
    def num_satellites(self):
        return self._num_satellites

    @property
    def speed(self):
        return self._speed

    @property
    def status(self):
        return self._status

    @property
    def state(self):
        """Return the state of the sensor."""
        return f"Lat: {self._latitude}, Lon: {self._longitude}"
