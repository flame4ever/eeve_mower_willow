"""Coordinators for willow."""
from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp
from homeassistant.helpers.entity import Entity
from homeassistant.const import PERCENTAGE


from homeassistant.components.light import LightEntity
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, CONF_IP_ADDRESS, NAME, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)

class MowingInfoCoordinator(DataUpdateCoordinator):
    """Mowing info coordinator.

    The CoordinatorEntity class provides:
        should_poll
        async_update
        async_added_to_hass
        available
    """

    def __init__(self, hass, entry, ip_address):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=DOMAIN,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30),
        )

        self._hass = hass
        self._entry = entry
        self._ip_address = ip_address

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN].setdefault(entry.entry_id, {
                    "name": entry.title,
                    "ip": ip_address,
                    "model": MODEL,
                    "status": "OFFLINE"
                })

        self.data = {
            "mowingTime": {
                "current": 0,
                "max": 0,
                "today": 0,
                "total": 0
            },
            "todayEndTime": None,
            "zoneIdToMow": None
        }

    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return {
            "identifiers": {
                (DOMAIN, self._entry.entry_id)
                },
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL
        }

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        _LOGGER.debug("MowingInfoCoordinator _async_update_data")

        url = f"http://{self._ip_address}:8080/api/system/mowingInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self.data = data
                    return data

            except aiohttp.ClientError as e:
                _LOGGER.warn(f"Failed to update mower info: {e}")
                #raise UpdateFailed(f"Error communicating with socket: {e}")