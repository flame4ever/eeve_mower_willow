"""Sensor entities for EEVE Mower Willow.

All sensors use one of the two shared coordinators (fast / system) so that
the mower receives at most one batch of HTTP requests per polling interval,
instead of one separate HTTP session per sensor.

Unique-IDs are intentionally kept identical to the original implementation
so that existing Home Assistant entity registrations, dashboards and
automations continue to work after upgrading.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME
from .coordinator import EeveMowerCoordinator, EeveMowerSystemCoordinator

_LOGGER = logging.getLogger(__name__)


def _parse_mower_datetime(data: dict, field_name: str) -> datetime | None:
    """Parse a naive datetime string from the mower's time API and attach timezone.

    The mower returns strings like "2026-05-25 05:14:39" (no tzinfo).
    HA's TIMESTAMP device class requires a timezone-aware datetime object.
    The timezone is read from the same /api/system/time response (timeZone field).
    """
    time_data = data.get("time", {})
    dt_str = time_data.get(field_name)
    tz_str = time_data.get("timeZone", "UTC")
    if not dt_str:
        return None
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=ZoneInfo(tz_str))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helper functions for complex state derivations
# ---------------------------------------------------------------------------

def _active_tool(data: dict) -> str:
    """Return the currently active tool name from toolplanner data."""
    tools = data.get("toolplanner", {}).get("tools", [])
    for tool in tools:
        if tool.get("active"):
            return tool.get("name", "unknown")
    # If nothing is active, check whether the mower is in the charging station
    for tool in tools:
        if tool.get("name") == "docking":
            blocked_by = tool.get("manual", {}).get("blockedBy", [])
            if any(b.get("name") == "inChargingStation" for b in blocked_by):
                return "in Charging Station"
    return "no activities"


def _scheduler_next(data: dict) -> str | None:
    """Return the next scheduled mowing time."""
    tools = data.get("toolplanner", {}).get("tools", [])
    for tool in tools:
        if tool.get("name") == "mowing":
            schedule = tool.get("auto", {}).get("schedule", [])
            if schedule:
                return schedule[0].get("resume", "No schedule")
            return "No schedule"
    return "No mowing tool"


def _mowing_time_today_min(data: dict) -> float | None:
    """Return mowing-activity time today in minutes (index 1 = mowing)."""
    today = data.get("mowing_info", {}).get("mowingTime", {}).get("today", [0, 0])
    if len(today) > 1:
        return round(today[1] / 60, 1)
    return None


def _mower_active_time_today_min(data: dict) -> float | None:
    """Return total active time today in minutes (index 0 = full active time)."""
    today = data.get("mowing_info", {}).get("mowingTime", {}).get("today", [0, 0])
    if today:
        return round(today[0] / 60, 1)
    return None


def _mowing_time_total_min(data: dict) -> float:
    """Return total all-time mowing time in minutes."""
    return round(
        data.get("mowing_info", {}).get("mowingTime", {}).get("total", 0) / 60, 1
    )


def _tool_planner_active(data: dict) -> str:
    """Return comma-separated list of active tools, or 'None'."""
    tools = data.get("toolplanner", {}).get("tools", [])
    active = [t["name"] for t in tools if t.get("active")]
    return ", ".join(active) if active else "None"


def _gps_state(data: dict) -> str | None:
    gps = data.get("gps", {})
    lat = gps.get("latitude")
    lon = gps.get("longitude")
    if lat is None or lon is None:
        return None
    return f"{lat}, {lon}"


def _slam_state(data: dict) -> str | None:
    slam = data.get("slam_odometry", {})
    lat = slam.get("lat")
    lon = slam.get("lon")
    if lat is None or lon is None:
        return None
    return f"{lat}, {lon}"



def _parse_last_rain(data: dict) -> datetime | None:
    """Parse lastRainTime from mowingInfo, ensuring timezone-aware datetime."""
    raw = data.get("mowing_info", {}).get("lastRainTime")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Sensor description dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class EeveSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with coordinator type and value accessors."""

    coordinator_type: str = "fast"
    value_fn: Callable[[dict], object] = lambda d: None
    extra_fn: Callable[[dict], dict] | None = None
    # Override the unique_id suffix (defaults to key if not set).
    # Used to preserve legacy unique-IDs after refactoring.
    legacy_unique_id_suffix: str = ""


# ---------------------------------------------------------------------------
# Sensor descriptions — FAST coordinator (30-second polling)
# ---------------------------------------------------------------------------

FAST_SENSOR_DESCRIPTIONS: tuple[EeveSensorDescription, ...] = (
    # --- Battery ---
    EeveSensorDescription(
        key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        coordinator_type="fast",
        legacy_unique_id_suffix="battery_sensor",
        value_fn=lambda d: d.get("battery", {}).get("percentage"),
        extra_fn=lambda d: {
            "available_mowing_time": d.get("battery", {}).get("availableMowingTime")
        },
    ),
    # --- Activity / Tool Planner ---
    EeveSensorDescription(
        key="mower_activities",
        icon="mdi:robot-mower",
        coordinator_type="fast",
        legacy_unique_id_suffix="mower_activities_sensor",
        value_fn=_active_tool,
    ),
    EeveSensorDescription(
        key="scheduler",
        icon="mdi:calendar-clock",
        coordinator_type="fast",
        legacy_unique_id_suffix="scheduler_sensor",
        value_fn=_scheduler_next,
    ),
    EeveSensorDescription(
        key="tool_planner_status",
        icon="mdi:clipboard-list",
        coordinator_type="fast",
        legacy_unique_id_suffix="tool_planner_status_sensor",
        value_fn=_tool_planner_active,
        extra_fn=lambda d: d.get("toolplanner", {}),
    ),
    # --- Emergency Stop ---
    EeveSensorDescription(
        key="emergency_stop_desc",
        icon="mdi:alert",
        coordinator_type="fast",
        legacy_unique_id_suffix="emergency_stop_desc_sensor",
        value_fn=lambda d: d.get("emergency_stop", {}).get("description", "none"),
    ),
    # --- Docking Info ---
    EeveSensorDescription(
        key="docking_state",
        icon="mdi:ev-station",
        coordinator_type="fast",
        legacy_unique_id_suffix="docking_state_sensor",
        value_fn=lambda d: d.get("docking_info", {}).get("dockingState"),
    ),
    EeveSensorDescription(
        key="charge_status",
        icon="mdi:battery-charging",
        coordinator_type="fast",
        legacy_unique_id_suffix="charge_status_sensor",
        value_fn=lambda d: d.get("docking_info", {}).get("chargeStatus"),
    ),
    EeveSensorDescription(
        key="charger_state",
        icon="mdi:power-plug",
        coordinator_type="fast",
        legacy_unique_id_suffix="charger_state_sensor",
        value_fn=lambda d: d.get("docking_info", {}).get("chargerState"),
    ),
    EeveSensorDescription(
        key="charging_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="fast",
        legacy_unique_id_suffix="charging_current_sensor",
        value_fn=lambda d: d.get("docking_info", {}).get("chargingCurrent"),
    ),
    EeveSensorDescription(
        key="charging_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="fast",
        legacy_unique_id_suffix="charging_power_sensor",
        value_fn=lambda d: d.get("docking_info", {}).get("chargingPower"),
    ),
    # --- Mowing Times ---
    EeveSensorDescription(
        key="mowing_activity_time_today",
        icon="mdi:mower",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        coordinator_type="fast",
        legacy_unique_id_suffix="mowing_time_today_sensor",
        value_fn=_mowing_time_today_min,
    ),
    EeveSensorDescription(
        key="mower_active_time_today",
        icon="mdi:mower",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        coordinator_type="fast",
        legacy_unique_id_suffix="mower_active_time_today_sensor",
        value_fn=_mower_active_time_today_min,
    ),
    EeveSensorDescription(
        key="mowing_time_total",
        icon="mdi:mower",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        coordinator_type="fast",
        legacy_unique_id_suffix="mowing_time_total_sensor",
        value_fn=_mowing_time_total_min,
    ),
    # --- Mowing session detail ---
    EeveSensorDescription(
        key="current_mowing_session",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        coordinator_type="fast",
        legacy_unique_id_suffix="current_mowing_session_sensor",
        value_fn=lambda d: d.get("mowing_info", {}).get("mowingTime", {}).get("current"),
    ),
    EeveSensorDescription(
        key="current_mowing_zone",
        icon="mdi:map-marker",
        coordinator_type="fast",
        legacy_unique_id_suffix="current_mowing_zone_sensor",
        value_fn=lambda d: d.get("mowing_info", {}).get("zoneIdToMow"),
    ),
    EeveSensorDescription(
        key="today_end_time",
        icon="mdi:calendar-clock",
        coordinator_type="fast",
        legacy_unique_id_suffix="today_end_time_sensor",
        value_fn=lambda d: d.get("mowing_info", {}).get("todayEndTime"),
    ),
    # --- Rain sensor ---
    EeveSensorDescription(
        key="rain_sensor_value",
        icon="mdi:weather-rainy",
        coordinator_type="fast",
        value_fn=lambda d: (
            d.get("rain_sensor", {}).get("value")
            if isinstance(d.get("rain_sensor"), dict)
            else (
                d.get("rain_sensor", {}).get("rain")
                if isinstance(d.get("rain_sensor"), dict)
                else (
                    d.get("rain_sensor")
                    if isinstance(d.get("rain_sensor"), (int, float))
                    else None
                )
            )
        ),
    ),
    EeveSensorDescription(
        key="last_rain_time",
        icon="mdi:weather-pouring",
        device_class=SensorDeviceClass.TIMESTAMP,
        coordinator_type="fast",
        value_fn=lambda d: _parse_last_rain(d),
    ),
)


# ---------------------------------------------------------------------------
# Sensor descriptions — SYSTEM coordinator (5-minute polling)
# ---------------------------------------------------------------------------

SYSTEM_SENSOR_DESCRIPTIONS: tuple[EeveSensorDescription, ...] = (
    # --- Network ---
    EeveSensorDescription(
        key="network_state",
        icon="mdi:lan-connect",
        coordinator_type="system",
        legacy_unique_id_suffix="network_state_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("state"),
    ),
    EeveSensorDescription(
        key="network_default",
        icon="mdi:lan",
        coordinator_type="system",
        legacy_unique_id_suffix="network_default_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("default"),
    ),
    EeveSensorDescription(
        key="network_mobile_reason",
        icon="mdi:cellphone-link",
        coordinator_type="system",
        legacy_unique_id_suffix="network_mobile_reason_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("mobile", {}).get("reason"),
    ),
    EeveSensorDescription(
        key="network_mobile_state",
        icon="mdi:cellphone-wireless",
        coordinator_type="system",
        legacy_unique_id_suffix="network_mobile_state_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("mobile", {}).get("state"),
    ),
    EeveSensorDescription(
        key="network_wifi_local_ip",
        icon="mdi:ip",
        coordinator_type="system",
        legacy_unique_id_suffix="network_wifi_local_ip_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("wifi", {}).get("localIp"),
    ),
    EeveSensorDescription(
        key="network_wifi_reason",
        icon="mdi:wifi",
        coordinator_type="system",
        legacy_unique_id_suffix="network_wifi_reason_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("wifi", {}).get("reason"),
    ),
    EeveSensorDescription(
        key="network_wifi_signal",
        icon="mdi:wifi",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="system",
        legacy_unique_id_suffix="network_wifi_signal_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("wifi", {}).get("signal"),
    ),
    EeveSensorDescription(
        key="network_wifi_ssid",
        icon="mdi:wifi",
        coordinator_type="system",
        legacy_unique_id_suffix="network_wifi_ssid_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("wifi", {}).get("ssid"),
    ),
    EeveSensorDescription(
        key="network_wifi_state",
        icon="mdi:wifi",
        coordinator_type="system",
        legacy_unique_id_suffix="network_wifi_state_sensor",
        value_fn=lambda d: d.get("network_info", {}).get("wifi", {}).get("state"),
    ),
    # --- GPS ---
    EeveSensorDescription(
        key="gps",
        icon="mdi:map-marker",
        coordinator_type="system",
        legacy_unique_id_suffix="gps_sensor",
        value_fn=_gps_state,
        extra_fn=lambda d: {
            "latitude":       d.get("gps", {}).get("latitude"),
            "longitude":      d.get("gps", {}).get("longitude"),
            "gps_accuracy":   d.get("gps", {}).get("accuracy"),
            "datetime":       d.get("gps", {}).get("datetime"),
            "num_satellites": d.get("gps", {}).get("numSatellites"),
            "speed":          d.get("gps", {}).get("speed"),
            "status":         d.get("gps", {}).get("status"),
        },
    ),
    # --- System info ---
    EeveSensorDescription(
        key="boot_count",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        coordinator_type="system",
        legacy_unique_id_suffix="boot_count_sensor",
        value_fn=lambda d: d.get("boot_count", {}).get("bootcount"),
    ),
    EeveSensorDescription(
        key="exploring_state",
        icon="mdi:map-search",
        coordinator_type="system",
        legacy_unique_id_suffix="exploring_state_sensor",
        value_fn=lambda d: d.get("exploring_info", {}).get("exploringState"),
    ),
    # --- Hardware info (disabled by default – rarely changes) ---
    EeveSensorDescription(
        key="hardware_version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="hardware_version_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("hardwareVersion"),
    ),
    EeveSensorDescription(
        key="motor_direction",
        icon="mdi:rotate-3d-variant",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_direction_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("motorDirection"),
    ),
    EeveSensorDescription(
        key="mower_type",
        icon="mdi:robot-mower",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="mower_type_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("mowerType"),
    ),
    EeveSensorDescription(
        key="serial_number",
        icon="mdi:identifier",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="serial_number_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("serialNumber"),
    ),
    EeveSensorDescription(
        key="unique_hardware_id",
        icon="mdi:fingerprint",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="unique_hardware_id_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("uniqueHardwareId"),
    ),
    EeveSensorDescription(
        key="wheel_motors_type",
        icon="mdi:tire",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="wheel_motors_type_sensor",
        value_fn=lambda d: d.get("hardware_info", {}).get("wheelMotorsType"),
    ),
    # --- Motor Controller ---
    EeveSensorDescription(
        key="motor_ctrl_firmware",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_controller_firmware_version_sensor",
        value_fn=lambda d: d.get("motor_controller", {}).get("firmwareVersion"),
    ),
    EeveSensorDescription(
        key="motor_ctrl_hw_version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_controller_hardware_version_sensor",
        value_fn=lambda d: d.get("motor_controller", {}).get("hardwareVersion"),
    ),
    EeveSensorDescription(
        key="motor_ctrl_serial",
        icon="mdi:identifier",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_controller_serial_number_sensor",
        value_fn=lambda d: d.get("motor_controller", {}).get("serialNumber"),
    ),
    EeveSensorDescription(
        key="motor_ctrl_type",
        icon="mdi:cog",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_controller_type_sensor",
        value_fn=lambda d: d.get("motor_controller", {}).get("type"),
    ),
    EeveSensorDescription(
        key="motor_ctrl_uptime",
        icon="mdi:timer",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="motor_controller_uptime_sensor",
        value_fn=lambda d: d.get("motor_controller", {}).get("uptime"),
    ),
    # --- Mower motor ---
    EeveSensorDescription(
        key="mower_rpm",
        icon="mdi:rotate-right",
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="system",
        legacy_unique_id_suffix="mower_rpm_sensor",
        value_fn=lambda d: d.get("mower_info", {}).get("rpm"),
    ),
    # --- Power manager ---
    EeveSensorDescription(
        key="power_manager_status",
        icon="mdi:battery-heart",
        coordinator_type="system",
        legacy_unique_id_suffix="power_manager_status_sensor",
        value_fn=lambda d: d.get("powermanager", {}).get("status"),
    ),
    # --- Time ---
    EeveSensorDescription(
        key="sunrise",
        device_class=SensorDeviceClass.TIMESTAMP,
        coordinator_type="system",
        legacy_unique_id_suffix="sunrise_sensor",
        value_fn=lambda d: _parse_mower_datetime(d, "sunrise"),
    ),
    EeveSensorDescription(
        key="sunset",
        device_class=SensorDeviceClass.TIMESTAMP,
        coordinator_type="system",
        legacy_unique_id_suffix="sunset_sensor",
        value_fn=lambda d: _parse_mower_datetime(d, "sunset"),
    ),
    EeveSensorDescription(
        key="system_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="system_time_sensor",
        value_fn=lambda d: _parse_mower_datetime(d, "systemTime"),
    ),
    EeveSensorDescription(
        key="time_zone",
        icon="mdi:earth",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="time_zone_sensor",
        value_fn=lambda d: d.get("time", {}).get("timeZone"),
    ),
    EeveSensorDescription(
        key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="uptime_sensor",
        value_fn=lambda d: d.get("time", {}).get("uptime"),
    ),
    # --- Software versions (disabled by default) ---
    EeveSensorDescription(
        key="application_version",
        icon="mdi:application",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="application_version_sensor",
        value_fn=lambda d: d.get("version", {}).get("applicationVersion"),
    ),
    EeveSensorDescription(
        key="os_version",
        icon="mdi:linux",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="os_version_sensor",
        value_fn=lambda d: d.get("version", {}).get("osVersion"),
    ),
    EeveSensorDescription(
        key="api_version",
        icon="mdi:api",
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="api_version_sensor",
        value_fn=lambda d: d.get("version", {}).get("apiVersion"),
    ),
    # --- SLAM ---
    EeveSensorDescription(
        key="slam_odometry",
        icon="mdi:crosshairs-gps",
        coordinator_type="system",
        legacy_unique_id_suffix="slam_odometry_sensor",
        value_fn=_slam_state,
        extra_fn=lambda d: {
            "accuracy": d.get("slam_odometry", {}).get("acc"),
            "yaw":      d.get("slam_odometry", {}).get("yaw"),
        },
    ),
    EeveSensorDescription(
        key="distance_to_charger",
        icon="mdi:ev-station",
        native_unit_of_measurement="m",
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="system",
        legacy_unique_id_suffix="distance_to_charger_sensor",
        value_fn=lambda d: d.get("distance_charger", {}).get("distance"),
    ),
    EeveSensorDescription(
        key="distance_to_person",
        icon="mdi:account-alert",
        native_unit_of_measurement="m",
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="system",
        legacy_unique_id_suffix="distance_to_person_sensor",
        value_fn=lambda d: d.get("distance_person", {}).get("distance"),
    ),
    # --- Zones ---
    EeveSensorDescription(
        key="zones_count",
        icon="mdi:map-marker-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        coordinator_type="system",
        legacy_unique_id_suffix="zones_list_sensor",
        value_fn=lambda d: len(d.get("zones", [])),
        extra_fn=lambda d: {"zones": d.get("zones", [])},
    ),
    # --- Map recording ---
    EeveSensorDescription(
        key="map_recording_info",
        icon="mdi:record-circle",
        coordinator_type="system",
        legacy_unique_id_suffix="map_recording_info_sensor",
        value_fn=lambda d: (
            "Recording" if d.get("map_recording", {}).get("isRecording") else "Not Recording"
        ),
    ),
    # --- Disk ---
    EeveSensorDescription(
        key="disk_capacity",
        icon="mdi:harddisk",
        native_unit_of_measurement="MB",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="disk_capacity_sensor",
        value_fn=lambda d: d.get("disk_info", {}).get("capacity"),
    ),
    EeveSensorDescription(
        key="disk_free",
        icon="mdi:harddisk",
        native_unit_of_measurement="MB",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        coordinator_type="system",
        legacy_unique_id_suffix="disk_free_sensor",
        value_fn=lambda d: d.get("disk_info", {}).get("free"),
    ),
)


# ---------------------------------------------------------------------------
# Generic sensor entity
# ---------------------------------------------------------------------------

class EeveSensor(CoordinatorEntity, SensorEntity):
    """A single EEVE sensor described by an EeveSensorDescription."""

    _attr_has_entity_name = True
    entity_description: EeveSensorDescription

    def __init__(
        self,
        coordinator: EeveMowerCoordinator | EeveMowerSystemCoordinator,
        description: EeveSensorDescription,
        ip_address: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.key
        if description.coordinator_type == "system":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._ip_address = ip_address
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

        # Preserve legacy unique-IDs so existing HA entity registrations survive
        # an upgrade.  If a legacy suffix is defined, use it; otherwise fall
        # back to the description key.
        uid_suffix = description.legacy_unique_id_suffix or description.key
        self._attr_unique_id = f"{uid_suffix}_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def native_value(self) -> object:
        try:
            return self.entity_description.value_fn(self.coordinator.data or {})
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error computing native_value for %s: %s", self.entity_description.key, exc)
            return None

    @property
    def extra_state_attributes(self) -> dict:
        if self.entity_description.extra_fn is None:
            return {}
        try:
            return self.entity_description.extra_fn(self.coordinator.data or {}) or {}
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error computing extra_attrs for %s: %s", self.entity_description.key, exc)
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()



class EeveMowingZoneSensor(EeveSensor):
    """Sensor that resolves zone UUID to human-readable name."""

    def __init__(
        self,
        coordinator: EeveMowerCoordinator,
        sys_coordinator: EeveMowerSystemCoordinator,
        description: EeveSensorDescription,
        ip_address: str,
    ) -> None:
        super().__init__(coordinator, description, ip_address)
        self._sys_coordinator = sys_coordinator

    def _build_zone_map(self) -> dict[str, str]:
        """Build zone_id -> customName map from system coordinator zone_settings."""
        zone_map: dict[str, str] = {}
        zone_data = (self._sys_coordinator.data or {}).get("zone_settings", {})
        for feature in zone_data.get("features", []):
            fid = feature.get("id", "")
            props = feature.get("properties", {})
            name = props.get("customName") or props.get("zoneType", fid)
            if fid:
                zone_map[fid] = name
        return zone_map

    @property
    def native_value(self) -> object:
        try:
            zone_id = (self.coordinator.data or {}).get("mowing_info", {}).get("zoneIdToMow")
            if not zone_id:
                return zone_id
            zone_map = self._build_zone_map()
            return zone_map.get(zone_id, zone_id)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Error computing native_value for %s: %s", self.entity_description.key, exc)
            return None


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all sensor entities for this config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    fast_coord: EeveMowerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    sys_coord: EeveMowerSystemCoordinator = hass.data[DOMAIN][entry.entry_id]["system_coordinator"]

    entities: list[EeveSensor] = []
    for desc in FAST_SENSOR_DESCRIPTIONS:
        if desc.key == "current_mowing_zone":
            entities.append(EeveMowingZoneSensor(fast_coord, sys_coord, desc, ip_address))
        else:
            entities.append(EeveSensor(fast_coord, desc, ip_address))
    for desc in SYSTEM_SENSOR_DESCRIPTIONS:
        entities.append(EeveSensor(sys_coord, desc, ip_address))

    async_add_entities(entities)
