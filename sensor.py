import logging
import aiohttp

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import PERCENTAGE

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass
)

from homeassistant.core import (
    HomeAssistant,
    callback
)

from .coordinator import (
    MowingInfoCoordinator,
    EmergencyStopCoordinator
)

from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    MANUFACTURER,
    MODEL,
    NAME
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the EEVE Mower battery sensor from a config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    async_add_entities([
        BatterySensor(ip_address),
        ActiveSensor(ip_address)
        ])

    #Add mowing info sensors
    mowing_info_coordinator = MowingInfoCoordinator(hass, entry, ip_address)
    async_add_entities([
        MowingTimeTodaySensor(mowing_info_coordinator, ip_address),
        MowingTimeTotalSensor(mowing_info_coordinator, ip_address)
        ])

    #Add emergency stop sensors
    emergency_stop_coordinator = EmergencyStopCoordinator(hass, entry, ip_address)
    async_add_entities([
        EmergencyStopDescriptionSensor(emergency_stop_coordinator, ip_address)
        ])

class BatterySensor(Entity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._available_mowing_time = None
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
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
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

    @property
    def available_mowing_time(self):
        return self._available_mowing_time

    @property
    def extra_state_attributes(self):
        return {
            "available_mowing_time": self.available_mowing_time,
            }

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/batteryStatus"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    self._state = data.get("percentage")
                    self._available_mowing_time = data.get("availableMowingTime")
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
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
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


class MowingTimeTodaySensor(CoordinatorEntity, SensorEntity):
    """Mowing time today sensor."""
    
    _attr_icon = "mdi:mower"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "min"
    _attr_suggested_display_precision = 0
    _attr_suggested_unit_of_measurement = "min"

    def __init__(self, coordinator, ip_address):
        super().__init__(coordinator, context=0)

        self._ip_address = ip_address  # Initialize the IP address
        self._state = None
        self._name = "Mowing Time Today"
        self._unique_id = f"mowing_time_today_sensor_{ip_address.replace('.', '_')}"
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
        }

    @property
    def state(self):
        return self.coordinator.data["mowingTime"]["today"]


    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


    async def async_update(self):
        """Synchronize state"""
        await self.coordinator.async_request_refresh()


class MowingTimeTotalSensor(CoordinatorEntity, SensorEntity):
    """Mowing time total sensor."""
    
    _attr_icon = "mdi:mower"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "min"
    _attr_suggested_display_precision = 0
    _attr_suggested_unit_of_measurement = "min"

    def __init__(self, coordinator, ip_address):
        super().__init__(coordinator, context=0)

        self._ip_address = ip_address  # Initialize the IP address
        self._state = None
        self._name = "Mowing Time Total"
        self._unique_id = f"mowing_time_total_sensor_{ip_address.replace('.', '_')}"
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
        }

    @property
    def state(self):
        return self.coordinator.data["mowingTime"]["total"]


    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


    async def async_update(self):
        """Synchronize state"""
        await self.coordinator.async_request_refresh()





class EmergencyStopDescriptionSensor(CoordinatorEntity, SensorEntity):
    """Emergency stop description sensor."""
    
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [ "none" , "Sensors: [\"slam\"]"]

    def __init__(self, coordinator, ip_address):
        super().__init__(coordinator, context=0)

        self._ip_address = ip_address  # Initialize the IP address
        self._state = None
        self._name = "Emergency Stop Description"
        self._unique_id = f"emergency_stop_desc_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def icon(self):
            return "mdi:check-bold" if self.state == "none" else "mdi:alert"

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
    def state(self):
        return self.coordinator.data["description"]


    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


    async def async_update(self):
        """Synchronize state"""
        await self.coordinator.async_request_refresh()