import logging
import aiohttp

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import PERCENTAGE
from .device_tracker import GPSSensor

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
        ActiveSensor(ip_address),
		SchedulerSensor(ip_address),
        GPSSensorEntity(ip_address),
        NetworkStateSensor(ip_address),
        NetworkDefaultSensor(ip_address),
        NetworkMobileReasonSensor(ip_address),
        NetworkMobileStateSensor(ip_address),
        NetworkWifiLocalIpSensor(ip_address),
        NetworkWifiReasonSensor(ip_address),
        NetworkWifiSignalSensor(ip_address),
        NetworkWifiSsidSensor(ip_address),
        NetworkWifiStateSensor(ip_address)
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
        url = f"http://{self._ip_address}:8080/api/toolplanner/status"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        active_tool_found = False

                        for tool in data['tools']:
                            if tool['active']:
                                self._state = tool['name']
                                active_tool_found = True
                                break

                        if not active_tool_found:
                            for tool in data['tools']:
                                if tool['name'] == 'docking':
                                    blocked_by = tool.get('manual', {}).get('blockedBy', [])
                                    if any(block['name'] == 'inChargingStation' for block in blocked_by):
                                        self._state = "in Charging Station"
                                        break
                            else:
                                self._state = "no activities"

                    else:
                        _LOGGER.error(f"Failed to fetch data: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch data: {e}")
                self._state = None

class SchedulerSensor(Entity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Scheduler"
        self._unique_id = f"scheduler_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:calendar-clock"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/toolplanner/status"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        for tool in data['tools']:
                            if tool['name'] == 'mowing':
                                schedule = tool.get('auto', {}).get('schedule', [])
                                if schedule:
                                    self._state = schedule[0].get('resume', 'No schedule')
                                else:
                                    self._state = 'No schedule'
                                break
                        else:
                            self._state = 'No mowing tool found'
                    else:
                        _LOGGER.error(f"Failed to fetch data: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch data: {e}")
                self._state = None

class GPSSensorEntity(Entity):
    """Representation of a GPS sensor."""

    def __init__(self, ip_address):
        self._gps_sensor = GPSSensor(ip_address)  # Use the imported GPSSensor class
        self._name = "GPS"
        self._unique_id = f"gps_sensor_{ip_address.replace('.', '_')}"
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
    def icon(self):
        return "mdi:map-marker"

    @property
    def state(self):
        return f"{self._gps_sensor.latitude}, {self._gps_sensor.longitude}"

    @property
    def extra_state_attributes(self):
        return {
            "latitude": self._gps_sensor.latitude,
            "longitude": self._gps_sensor.longitude,
            "gps_accuracy": self._gps_sensor.accuracy,
            "datetime": self._gps_sensor.datetime,
            "num_satellites": self._gps_sensor.num_satellites,
            "speed": self._gps_sensor.speed,
            "status": self._gps_sensor.status,
        }

    async def async_update(self):
        await self._gps_sensor.async_update()


class NetworkStateSensor(Entity):
    """Representation of the network state sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network State"
        self._unique_id = f"network_state_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:lan-connect"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("state")
                    else:
                        _LOGGER.error(f"Failed to fetch network state: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network state: {e}")
                self._state = None

class NetworkDefaultSensor(Entity):
    """Representation of the network default sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Default"
        self._unique_id = f"network_default_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:lan"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("default")
                    else:
                        _LOGGER.error(f"Failed to fetch network default: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network default: {e}")
                self._state = None

class NetworkMobileReasonSensor(Entity):
    """Representation of the network mobile reason sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Mobile Reason"
        self._unique_id = f"network_mobile_reason_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:cellphone-link"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("mobile", {}).get("reason")
                    else:
                        _LOGGER.error(f"Failed to fetch network mobile reason: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network mobile reason: {e}")
                self._state = None

class NetworkMobileStateSensor(Entity):
    """Representation of the network mobile state sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Mobile State"
        self._unique_id = f"network_mobile_state_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:cellphone-wireless"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("mobile", {}).get("state")
                    else:
                        _LOGGER.error(f"Failed to fetch network mobile state: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network mobile state: {e}")
                self._state = None

class NetworkWifiLocalIpSensor(Entity):
    """Representation of the network wifi local IP sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Wifi Local IP"
        self._unique_id = f"network_wifi_local_ip_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:ip"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("wifi", {}).get("localIp")
                    else:
                        _LOGGER.error(f"Failed to fetch network wifi local IP: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network wifi local IP: {e}")
                self._state = None

class NetworkWifiReasonSensor(Entity):
    """Representation of the network wifi reason sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Wifi Reason"
        self._unique_id = f"network_wifi_reason_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:wifi"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("wifi", {}).get("reason")
                    else:
                        _LOGGER.error(f"Failed to fetch network wifi reason: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network wifi reason: {e}")
                self._state = None

class NetworkWifiSignalSensor(Entity):
    """Representation of the network wifi signal sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Wifi Signal"
        self._unique_id = f"network_wifi_signal_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def unit_of_measurement(self):
        return "%"

    @property
    def icon(self):
        return "mdi:wifi"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("wifi", {}).get("signal")
                    else:
                        _LOGGER.error(f"Failed to fetch network wifi signal: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network wifi signal: {e}")
                self._state = None

class NetworkWifiSsidSensor(Entity):
    """Representation of the network wifi SSID sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Wifi SSID"
        self._unique_id = f"network_wifi_ssid_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:wifi"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("wifi", {}).get("ssid")
                    else:
                        _LOGGER.error(f"Failed to fetch network wifi SSID: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network wifi SSID: {e}")
                self._state = None

class NetworkWifiStateSensor(Entity):
    """Representation of the network wifi state sensor."""

    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = None
        self._name = "Network Wifi State"
        self._unique_id = f"network_wifi_state_sensor_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def icon(self):
        return "mdi:wifi"

    @property
    def state(self):
        return self._state

    async def async_update(self):
        url = f"http://{self._ip_address}:8080/api/system/networkInfo"
        headers = {"accept": "application/json"}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self._state = data.get("wifi", {}).get("state")
                    else:
                        _LOGGER.error(f"Failed to fetch network wifi state: {response.status}")
                        self._state = None
            except aiohttp.ClientError as e:
                _LOGGER.error(f"Failed to fetch network wifi state: {e}")
                self._state = None

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