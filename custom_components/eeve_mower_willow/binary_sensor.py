"""Binary sensor entities for EEVE Mower Willow.

Provides simple on/off states derived from the two shared coordinators:

Fast coordinator (30 s):
  - Is Mowing
  - Is Docked
  - Is Charging
  - Is Returning to Dock
  - Has Error (emergency stop active)

System coordinator (5 min):
  - Is Recording Map
  - Camera Lens Calibrated
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.const import EntityCategory
from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME
from .coordinator import EeveMowerCoordinator, EeveMowerSystemCoordinator

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Description dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class EeveBinarySensorDescription(BinarySensorEntityDescription):
    """Extends BinarySensorEntityDescription with coordinator type and value fn."""

    coordinator_type: str = "fast"
    is_on_fn: Callable[[dict], bool] = lambda d: False


# ---------------------------------------------------------------------------
# Fast coordinator binary sensors (30-second polling)
# ---------------------------------------------------------------------------

FAST_BINARY_DESCRIPTIONS: tuple[EeveBinarySensorDescription, ...] = (
    EeveBinarySensorDescription(
        key="is_mowing",
        name="Is Mowing",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:robot-mower",
        coordinator_type="fast",
        is_on_fn=lambda d: (
            d.get("activities", {}).get("userActivity") == "MowActivity"
            or d.get("activities", {}).get("scheduledActivity")
            in ("MowingPlannerActivity", "MowActivity")
        ),
    ),
    EeveBinarySensorDescription(
        key="is_docked",
        name="Is Docked",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:home-battery",
        coordinator_type="fast",
        is_on_fn=lambda d: any(
            kw in (d.get("docking_info", {}).get("dockingState", "") or "").lower()
            for kw in ("charging", "docked", "inchargingstation", "idle_docked")
        ),
    ),
    EeveBinarySensorDescription(
        key="is_charging",
        name="Is Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon="mdi:battery-charging",
        coordinator_type="fast",
        is_on_fn=lambda d: "charging" in (
            d.get("docking_info", {}).get("chargeStatus", "") or ""
        ).lower(),
    ),
    EeveBinarySensorDescription(
        key="is_returning",
        name="Is Returning to Dock",
        device_class=BinarySensorDeviceClass.MOVING,
        icon="mdi:home-import-outline",
        coordinator_type="fast",
        is_on_fn=lambda d: (
            d.get("activities", {}).get("userActivity") == "DockingActivity"
            or d.get("activities", {}).get("scheduledActivity") == "DockingActivity"
        ),
    ),
    EeveBinarySensorDescription(
        key="has_error",
        name="Has Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
        coordinator_type="fast",
        is_on_fn=lambda d: d.get("emergency_stop", {}).get("description", "none")
        not in ("none", None, ""),
    ),
)

# ---------------------------------------------------------------------------
# System coordinator binary sensors (5-minute polling)
# ---------------------------------------------------------------------------

SYSTEM_BINARY_DESCRIPTIONS: tuple[EeveBinarySensorDescription, ...] = (
    EeveBinarySensorDescription(
        key="is_recording_map",
        name="Is Recording Map",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:record-circle",
        coordinator_type="system",
        is_on_fn=lambda d: bool(d.get("map_recording", {}).get("isRecording", False)),
    ),
    EeveBinarySensorDescription(
        key="camera_lens_calibrated",
        name="Camera Lens Calibrated",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:camera-check",
        coordinator_type="system",
        is_on_fn=lambda d: bool(d.get("camera_calibrated", False)),
    ),
)


# ---------------------------------------------------------------------------
# Generic binary sensor entity
# ---------------------------------------------------------------------------

class EeveBinarySensor(CoordinatorEntity, BinarySensorEntity):

    _attr_has_entity_name = True
    """A single EEVE binary sensor described by an EeveBinarySensorDescription."""

    entity_description: EeveBinarySensorDescription

    def __init__(
        self,
        coordinator: EeveMowerCoordinator | EeveMowerSystemCoordinator,
        description: EeveBinarySensorDescription,
        ip_address: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_translation_key = description.key
        if description.coordinator_type == "system":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._ip_address = ip_address
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
        self._attr_unique_id = (
            f"binary_{description.key}_{ip_address.replace('.', '_')}"
        )

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def is_on(self) -> bool:
        try:
            return bool(self.entity_description.is_on_fn(self.coordinator.data or {}))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug(
                "Error computing is_on for %s: %s", self.entity_description.key, exc
            )
            return False

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all binary sensor entities for this config entry."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    fast_coord: EeveMowerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    sys_coord: EeveMowerSystemCoordinator = (
        hass.data[DOMAIN][entry.entry_id]["system_coordinator"]
    )

    entities: list[EeveBinarySensor] = []
    for desc in FAST_BINARY_DESCRIPTIONS:
        entities.append(EeveBinarySensor(fast_coord, desc, ip_address))
    for desc in SYSTEM_BINARY_DESCRIPTIONS:
        entities.append(EeveBinarySensor(sys_coord, desc, ip_address))

    async_add_entities(entities)
