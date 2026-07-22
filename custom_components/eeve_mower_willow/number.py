"""Number entities for EEVE Mower Willow.

Global entities (always created):
  MaxMowingTimeNumber       - max mowing time when starting a mow cycle (0 = unlimited)
  ManualDriveSpeedNumber    - speed for manual navigation buttons
  StartTimeAfterSunriseNumber - minutes after sunrise when daily mowing starts
  VolumeNumber              - master volume for the mower speaker (0-100 %)
  LowBatteryThresholdNumber - battery % below which the mower considers battery "low"

Per-zone entities (created dynamically based on /settings/zones response):
  ZoneMowerHeightNumber     - cutting height in mm for a specific zone
  ZoneLineDirectionNumber   - line mowing direction in degrees (0-360) for a specific zone
"""
from __future__ import annotations

import logging
import time
import aiohttp
import asyncio
import urllib.request

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME
from .coordinator import EeveMowerSystemCoordinator, async_fetch_zone_settings

_LOGGER = logging.getLogger(__name__)


async def _post_zones_urllib(url: str, zone_data: dict) -> int:
    """POST zone data using urllib (bypasses aiohttp connection issues)."""
    import json as _json
    payload = _json.dumps(zone_data).encode("utf-8")
    def _do_post():
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "accept": "application/json",
                "Connection": "close",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    return await asyncio.get_event_loop().run_in_executor(None, _do_post)


async def _set_all_grass_zones(hass, ip_address, apply_fn) -> int | None:
    """GET /settings/zones, apply apply_fn(zoneProperties) to every GRASSZONE, POST once."""
    url = f"http://{ip_address}:8080/settings/zones"
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, headers={"accept": "application/json"},
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                _LOGGER.error("GET /settings/zones failed: HTTP %s", resp.status)
                return None
            zone_data = await resp.json()
    except aiohttp.ClientError as exc:
        _LOGGER.error("GET /settings/zones failed: %s", exc)
        return None
    count = 0
    for feature in zone_data.get("features", []):
        props = feature.get("properties", {})
        if props.get("zoneType") != "GRASSZONE":
            continue
        apply_fn(props.setdefault("zoneProperties", {}))
        count += 1
    if count == 0:
        _LOGGER.error("No GRASSZONE features found in /settings/zones")
        return None
    try:
        return await _post_zones_urllib(url, zone_data)
    except Exception as exc:
        _LOGGER.error("POST /settings/zones failed: %s", exc)
        return None



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower number entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    system_coord: EeveMowerSystemCoordinator = hass.data[DOMAIN][entry.entry_id][
        "system_coordinator"
    ]

    entities: list[NumberEntity] = [
        MaxMowingTimeNumber(ip_address),
        ManualDriveSpeedNumber(ip_address),
        StartTimeAfterSunriseNumber(ip_address),
        VolumeNumber(ip_address),
        LowBatteryThresholdNumber(ip_address),
        AllZonesMowerHeightNumber(system_coord, ip_address),
        AllZonesLineDirectionNumber(system_coord, ip_address),
    ]

    zone_list = await async_fetch_zone_settings(ip_address)
    for zone_id, zone_name, zone_props in zone_list:
        initial_height = float(
            zone_props.get("mowActivity", {}).get("mowerHeight", 40)
        )
        entities.append(
            ZoneMowerHeightNumber(
                system_coord, ip_address, zone_id, zone_name, initial_height
            )
        )
        initial_direction = float(
            zone_props.get("lineMowActivity", {}).get("lineDirection", 0)
        )
        entities.append(
            ZoneLineDirectionNumber(
                system_coord, ip_address, zone_id, zone_name, initial_direction
            )
        )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Shared device info helper
# ---------------------------------------------------------------------------

def _device_info(ip_address: str) -> dict:
    device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
    return {
        "identifiers": {(DOMAIN, device_id)},
        "name": NAME,
        "manufacturer": MANUFACTURER,
        "model": MODEL,
    }


# ---------------------------------------------------------------------------
# Max mowing time
# ---------------------------------------------------------------------------

class MaxMowingTimeNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "max_mowing_time"
    """Configures the maximum mowing time used when starting a mow cycle.

    A value of 0 means unlimited / until battery runs low.
    """

    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 480
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: float = 0
        self._attr_unique_id = f"max_mowing_time_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.debug("Max mowing time set to %s minutes", value)


# ---------------------------------------------------------------------------
# Manual drive speed
# ---------------------------------------------------------------------------

class ManualDriveSpeedNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "manual_drive_speed"
    """Controls the speed used for manual navigation buttons."""

    _attr_icon = "mdi:speedometer"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0.05
    _attr_native_max_value = 0.5
    _attr_native_step = 0.05

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: float = 0.2
        self._attr_unique_id = f"manual_drive_speed_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.debug("Manual drive speed set to %s m/s", value)


# ---------------------------------------------------------------------------
# Per-zone mower height
# ---------------------------------------------------------------------------

class ZoneMowerHeightNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "zone_mower_height"
    """Cutting height setting (in mm) for a specific mowing zone."""

    _attr_icon = "mdi:grass"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 20
    _attr_native_max_value = 80
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "mm"
    should_poll = False

    def __init__(
        self,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
        zone_id: str,
        zone_name: str,
        initial_height: float = 40.0,
    ) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._skip_coordinator_until = 0.0
        self._attr_native_value = initial_height
        safe = zone_id.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"zone_mower_height_{ip_address.replace('.', '_')}_{safe}"
        )
        self._attr_translation_placeholders = {"zone_name": zone_name}

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            height = props.get("zoneProperties", {}).get("mowActivity", {}).get("mowerHeight")
            if height is not None:
                self._attr_native_value = float(height)
            break

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self._ip_address}:8080/settings/zones"
        json_headers = {"accept": "application/json", "Content-Type": "application/json", "Connection": "close"}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, headers={"accept": "application/json"},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    _LOGGER.error("GET /settings/zones failed: HTTP %s", resp.status)
                    return
                zone_data = await resp.json()
        except aiohttp.ClientError as exc:
            _LOGGER.error("GET /settings/zones failed: %s", exc)
            return

        modified = False
        for feature in zone_data.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            zone_props = props.setdefault("zoneProperties", {})
            mow_activity = zone_props.setdefault("mowActivity", {})
            mow_activity["mowerHeight"] = int(value)
            modified = True
            break

        if not modified:
            _LOGGER.error("Zone %s not found in /settings/zones response", self._zone_id)
            return

        try:
            status = await _post_zones_urllib(url, zone_data)
            if status == 200:
                self._attr_native_value = value
                self.async_write_ha_state()
                self._skip_coordinator_until = time.monotonic() + 15
                _LOGGER.info("Zone '%s' mower height -> %d mm", self._zone_name, int(value))
                await self._system_coordinator.async_request_refresh()
            else:
                _LOGGER.error("POST /settings/zones failed: HTTP %s", status)
        except Exception as exc:
            _LOGGER.error("POST /settings/zones failed: %s", exc)


# ---------------------------------------------------------------------------
# Per-zone line mowing direction
# ---------------------------------------------------------------------------

class ZoneLineDirectionNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "zone_line_direction"
    """Line mowing direction (in degrees) for a specific mowing zone."""

    _attr_icon = "mdi:compass-outline"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 360
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "°"
    should_poll = False

    def __init__(
        self,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
        zone_id: str,
        zone_name: str,
        initial_direction: float = 0.0,
    ) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._skip_coordinator_until = 0.0
        self._attr_native_value = initial_direction
        safe_ip = ip_address.replace(".", "_")
        safe_zone = zone_id.lower().replace(" ", "_")
        self._attr_unique_id = f"zone_line_direction_{safe_ip}_{safe_zone}"
        self._attr_translation_placeholders = {"zone_name": zone_name}

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            direction = (
                props.get("zoneProperties", {})
                .get("lineMowActivity", {})
                .get("lineDirection")
            )
            if direction is not None:
                self._attr_native_value = float(direction)
            break

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self._ip_address}:8080/settings/zones"
        json_headers = {"accept": "application/json", "Content-Type": "application/json", "Connection": "close"}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, headers={"accept": "application/json"},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    _LOGGER.error("GET /settings/zones failed: HTTP %s", resp.status)
                    return
                zone_data = await resp.json()
        except aiohttp.ClientError as exc:
            _LOGGER.error("GET /settings/zones failed: %s", exc)
            return

        modified = False
        for feature in zone_data.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            zone_props = props.setdefault("zoneProperties", {})
            line_mow_activity = zone_props.setdefault("lineMowActivity", {})
            line_mow_activity["lineDirection"] = float(value)
            modified = True
            break

        if not modified:
            _LOGGER.error("Zone %s not found in /settings/zones response", self._zone_id)
            return

        try:
            status = await _post_zones_urllib(url, zone_data)
            if status == 200:
                self._attr_native_value = value
                self.async_write_ha_state()
                self._skip_coordinator_until = time.monotonic() + 15
                _LOGGER.info(
                    "Zone '%s' line direction -> %.1f°", self._zone_name, value
                )
                await self._system_coordinator.async_request_refresh()
            else:
                _LOGGER.error("POST /settings/zones failed: HTTP %s", status)
        except Exception as exc:
            _LOGGER.error("POST /settings/zones failed: %s", exc)


# ---------------------------------------------------------------------------
# Start time after sunrise
# ---------------------------------------------------------------------------

class StartTimeAfterSunriseNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "start_time_after_sunrise"
    """Minutes after sunrise when the mower starts its daily mowing session.

    GET/POST /settings/mowing/beginTimeAfterSunrise -> integer (minutes)
    """

    _attr_icon = "mdi:weather-sunset-up"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 480
    _attr_native_step = 15
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    _ENDPOINT = "/settings/mowing/beginTimeAfterSunrise"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: float = 180
        self._attr_unique_id = f"start_time_after_sunrise_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_update(self) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers={"accept": "application/json"},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, (int, float)):
                        self._attr_native_value = float(value)
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read start time after sunrise: %s", exc)

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(url,
                                    headers={"accept": "application/json",
                                             "Content-Type": "application/json"},
                                    data=str(int(value)),
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    self._attr_native_value = value
                    self.async_write_ha_state()
                    _LOGGER.info("Start time after sunrise set to %d min", int(value))
                else:
                    _LOGGER.error("Set start time failed: HTTP %s", resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set start time failed: %s", exc)


# ---------------------------------------------------------------------------
# Audio volume
# ---------------------------------------------------------------------------

class VolumeNumber(NumberEntity):

    _attr_has_entity_name = True
    # No entity_category: the volume lives with the Sound switch in the main
    # Controls section (not buried in Configuration), and it also sets the
    # playback volume used by the Sound switch.
    _attr_translation_key = "volume"
    """Master volume for the mower speaker (0-100 %).

    GET/POST /settings/audioPlayer/masterVolume -> integer 0-100
    """

    _attr_icon = "mdi:volume-high"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"

    _ENDPOINT = "/settings/audioPlayer/masterVolume"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: float = 50
        self._attr_unique_id = f"audio_volume_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_update(self) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers={"accept": "application/json"},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, (int, float)):
                        self._attr_native_value = float(value)
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read volume: %s", exc)

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(url,
                                    headers={"accept": "application/json",
                                             "Content-Type": "application/json"},
                                    data=str(int(value)),
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    self._attr_native_value = value
                    self.async_write_ha_state()
                    _LOGGER.info("Volume set to %d%%", int(value))
                else:
                    _LOGGER.error("Set volume failed: HTTP %s", resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set volume failed: %s", exc)


# ---------------------------------------------------------------------------
# Low battery threshold
# ---------------------------------------------------------------------------

class LowBatteryThresholdNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "low_battery_threshold"
    """Percentage threshold below which the mower considers battery low.

    GET/POST /settings/batteryMonitorAlgo/lowBatteryPercentageThreshold -> integer
    """

    _attr_icon = "mdi:battery-alert"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 5
    _attr_native_max_value = 50
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"

    _ENDPOINT = "/settings/batteryMonitorAlgo/lowBatteryPercentageThreshold"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._attr_native_value: float = 20
        self._attr_unique_id = f"low_battery_threshold_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_update(self) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, headers={"accept": "application/json"},
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, (int, float)):
                        self._attr_native_value = float(value)
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read low battery threshold: %s", exc)

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(url,
                                    headers={"accept": "application/json",
                                             "Content-Type": "application/json"},
                                    data=str(int(value)),
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    self._attr_native_value = value
                    self.async_write_ha_state()
                    _LOGGER.info("Low battery threshold set to %d%%", int(value))
                else:
                    _LOGGER.error("Set low battery threshold failed: HTTP %s", resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set low battery threshold failed: %s", exc)


# ---------------------------------------------------------------------------
# All-zones aggregate entities (apply one value to every GRASSZONE at once)
# ---------------------------------------------------------------------------

class AllZonesMowerHeightNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "all_zones_mower_height"
    _attr_icon = "mdi:grass"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 20
    _attr_native_max_value = 80
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "mm"
    should_poll = False

    def __init__(self, system_coordinator: EeveMowerSystemCoordinator, ip_address: str) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._skip_coordinator_until = 0.0
        self._attr_native_value = 40.0
        self._attr_unique_id = f"all_zones_mower_height_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            props = feature.get("properties", {})
            if props.get("zoneType") != "GRASSZONE":
                continue
            height = props.get("zoneProperties", {}).get("mowActivity", {}).get("mowerHeight")
            if height is not None:
                self._attr_native_value = float(height)
            break

    async def async_set_native_value(self, value: float) -> None:
        def _apply(zp):
            zp.setdefault("mowActivity", {})["mowerHeight"] = int(value)
        status = await _set_all_grass_zones(self.hass, self._ip_address, _apply)
        if status == 200:
            self._attr_native_value = value
            self.async_write_ha_state()
            self._skip_coordinator_until = time.monotonic() + 15
            _LOGGER.info("All zones mower height -> %d mm", int(value))
            await self._system_coordinator.async_request_refresh()
        else:
            _LOGGER.error("Set all-zones mower height failed (status %s)", status)


class AllZonesLineDirectionNumber(NumberEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "all_zones_line_direction"
    _attr_icon = "mdi:compass-outline"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 360
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "\u00b0"
    should_poll = False

    def __init__(self, system_coordinator: EeveMowerSystemCoordinator, ip_address: str) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._skip_coordinator_until = 0.0
        self._attr_native_value = 0.0
        self._attr_unique_id = f"all_zones_line_direction_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return _device_info(self._ip_address)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            props = feature.get("properties", {})
            if props.get("zoneType") != "GRASSZONE":
                continue
            direction = props.get("zoneProperties", {}).get("lineMowActivity", {}).get("lineDirection")
            if direction is not None:
                self._attr_native_value = float(direction)
            break

    async def async_set_native_value(self, value: float) -> None:
        def _apply(zp):
            zp.setdefault("lineMowActivity", {})["lineDirection"] = float(value)
        status = await _set_all_grass_zones(self.hass, self._ip_address, _apply)
        if status == 200:
            self._attr_native_value = value
            self.async_write_ha_state()
            self._skip_coordinator_until = time.monotonic() + 15
            _LOGGER.info("All zones line direction -> %d", int(value))
            await self._system_coordinator.async_request_refresh()
        else:
            _LOGGER.error("Set all-zones line direction failed (status %s)", status)
