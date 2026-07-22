"""Coordinators for EEVE Mower Willow.

Two coordinators are used to balance freshness vs. mower load:

* EeveMowerCoordinator   – 30-second interval for dynamic/state data
  (battery, activities, docking, mowing progress, tool planner).
* EeveMowerSystemCoordinator – 5-minute interval for static/system data
  (network, hardware, versions, GPS, SLAM, disk, …).

All sensor and binary-sensor entities share one of these two coordinators
so the mower receives at most a single batch of HTTP requests per interval,
instead of one request per sensor.

Helper:
  async_fetch_zone_settings(ip_address) – one-shot fetch of /settings/zones
  (used by number / select platforms at startup to discover per-zone entities).
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,  # re-exported so platforms can import from here
    DataUpdateCoordinator,
)

from .const import DOMAIN, NAME, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standalone helper – used at platform setup to enumerate per-zone entities
# ---------------------------------------------------------------------------

async def async_fetch_zone_settings(ip_address: str) -> list[tuple[str, str, dict]]:
    """Fetch /settings/zones and return list of (zone_id, zone_name, zone_props).

    zone_props is the ``zoneProperties`` dict for that GRASSZONE feature.
    Returns an empty list when the mower is unreachable or returns bad data.
    """
    url = f"http://{ip_address}:8080/settings/zones"
    result: list[tuple[str, str, dict]] = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "async_fetch_zone_settings: HTTP %s from %s", resp.status, url
                    )
                    return result
                data: Any = await resp.json()
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("async_fetch_zone_settings: %s", exc)
        return result

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        # zoneType is inside properties; the feature id is the zone id
        if props.get("zoneType") != "GRASSZONE":
            continue
        zone_id: str | None = feature.get("id")          # e.g. "GRASSZONE_f4bf…"
        zone_name: str = (
            props.get("customName")                       # user-given name
            or props.get("name")                          # fallback
            or zone_id
            or ""
        )
        zone_props: dict = props.get("zoneProperties", {})
        if zone_id:
            result.append((zone_id, zone_name, zone_props))

    _LOGGER.debug("async_fetch_zone_settings: found %d zones", len(result))
    return result


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class _EeveCoordinatorBase(DataUpdateCoordinator):
    """Common base for both EEVE coordinators."""

    DEFAULT_DATA: dict = {}
    _ENDPOINTS: dict[str, str] = {}

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ip_address: str,
        name: str,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self._ip_address = ip_address
        self._entry = entry
        # Pre-populate with safe defaults so sensors have data before first poll.
        self.data = dict(self.DEFAULT_DATA)

    @property
    def device_info(self) -> dict:
        """Device info shared by all entities registered under this coordinator."""
        return {
            "identifiers": {(DOMAIN, f"eeve_mower_{self._ip_address.replace('.', '_')}")},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    def _url(self, path: str) -> str:
        return f"http://{self._ip_address}:8080{path}"

    async def _async_update_data(self) -> dict:
        """Fetch all endpoints in a single aiohttp session."""
        _LOGGER.debug("%s: fetching %d endpoints", self.name, len(self._ENDPOINTS))
        result = dict(self.data) if self.data else dict(self.DEFAULT_DATA)
        headers = {"accept": "application/json"}

        async with aiohttp.ClientSession() as session:
            for key, path in self._ENDPOINTS.items():
                try:
                    async with session.get(
                        self._url(path),
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            result[key] = await resp.json()
                        else:
                            _LOGGER.debug(
                                "%s: endpoint %s returned HTTP %s", self.name, key, resp.status
                            )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    _LOGGER.debug("%s: failed to fetch %s: %s", self.name, key, exc)

        return result


# ---------------------------------------------------------------------------
# Fast coordinator — 30-second interval
# ---------------------------------------------------------------------------

class EeveMowerCoordinator(_EeveCoordinatorBase):
    """Polls dynamic/state endpoints every 30 seconds.

    Platforms using this coordinator: lawn_mower, binary_sensor (state),
    sensor (battery, activity, docking, mowing times, tool-planner).
    """

    DEFAULT_DATA: dict = {
        "activities": {},
        "battery": {},
        "emergency_stop": {"description": "none"},
        "docking_info": {},
        "mowing_info": {
            "mowingTime": {"current": 0, "max": 0, "today": [0, 0], "total": 0},
            "todayEndTime": None,
            "zoneIdToMow": None,
        },
        "toolplanner": {"tools": []},
        "rain_sensor": None,
    }

    _ENDPOINTS: dict[str, str] = {
        "activities":     "/api/activities/info",
        "battery":        "/api/system/batteryStatus",
        "emergency_stop": "/api/system/emergencyStop",
        "docking_info":   "/api/system/dockingInfo",
        "mowing_info":    "/api/system/mowingInfo",
        "toolplanner":    "/api/toolplanner/status",
        "rain_sensor":    "/sensors/rain",
    }

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ip_address: str,
    ) -> None:
        super().__init__(
            hass,
            entry,
            ip_address,
            name=f"{DOMAIN}_fast",
            update_interval=timedelta(seconds=30),
        )


# ---------------------------------------------------------------------------
# System coordinator — 5-minute interval
# ---------------------------------------------------------------------------

class EeveMowerSystemCoordinator(_EeveCoordinatorBase):
    """Polls static / slow-changing system endpoints every 5 minutes.

    Platforms using this coordinator: sensor (network, hardware, versions,
    GPS, SLAM, disk, …), binary_sensor (map recording, camera calibration).
    """

    DEFAULT_DATA: dict = {
        "network_info":     {},
        "hardware_info":    {},
        "motor_controller": {},
        "version":          {},
        "time":             {},
        "boot_count":       {},
        "gps":              {},
        "slam_odometry":    {},
        "powermanager":     {},
        "disk_info":        {},
        "zones":            [],
        "zone_settings":    {},  # full /settings/zones GeoJSON (per-zone properties)
        "exploring_info":   {},
        "mower_info":       {},
        "map_recording":    {},
        "distance_charger": {},
        "distance_person":  {},
        "camera_calibrated": None,
    }

    _ENDPOINTS: dict[str, str] = {
        "network_info":     "/api/system/networkInfo",
        "hardware_info":    "/api/system/hardwareInfo",
        "motor_controller": "/api/system/motorController/status",
        "version":          "/api/system/version",
        "time":             "/api/system/time",
        "boot_count":       "/api/system/bootcount",
        "gps":              "/api/statuslog/sensors/gps",
        "slam_odometry":    "/api/slam/odometry",
        "powermanager":     "/api/system/powermanager",
        "disk_info":        "/api/maintenance/mapsFilesystem/diskInfo",
        "zones":            "/api/zones/list",
        "zone_settings":    "/settings/zones",
        "exploring_info":   "/api/system/exploringInfo",
        "mower_info":       "/api/system/mowerInfo",
        "map_recording":    "/api/recording/maps/info",
        "distance_charger": "/api/slam/distanceToObject/toadicharger",
        "distance_person":  "/api/slam/distanceToObject/person",
        "camera_calibrated":"/api/calibration/camera/lens/isCalibrated",
    }

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ip_address: str,
    ) -> None:
        super().__init__(
            hass,
            entry,
            ip_address,
            name=f"{DOMAIN}_system",
            update_interval=timedelta(seconds=300),
        )
