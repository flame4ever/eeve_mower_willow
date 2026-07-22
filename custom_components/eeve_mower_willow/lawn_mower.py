"""Lawn mower entity for EEVE Mower Willow."""
from __future__ import annotations

import logging
import aiohttp

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME
from .coordinator import EeveMowerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower lawn mower entity."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    coordinator: EeveMowerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EeveMowerLawnMower(coordinator, ip_address)])


class EeveMowerLawnMower(CoordinatorEntity, LawnMowerEntity):
    """EEVE Mower Willow represented as a Home Assistant lawn mower entity."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
    )
    _attr_icon = "mdi:robot-mower"

    def __init__(self, coordinator: EeveMowerCoordinator, ip_address: str) -> None:
        super().__init__(coordinator)
        self._ip_address = ip_address
        self._attr_unique_id = f"lawn_mower_{ip_address.replace('.', '_')}"
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def activity(self) -> LawnMowerActivity:
        """Derive the mower activity from coordinator data.

        Priority:
        1. Emergency stop → ERROR
        2. Active tool from toolplanner (most reliable)
        3. activities/info fields as fallback
        4. docking_info for docked/charging state
        5. Default → PAUSED
        """
        if not self.coordinator.data:
            return LawnMowerActivity.ERROR

        # 1. Emergency stop → error state
        emergency = self.coordinator.data.get("emergency_stop", {})
        if emergency.get("description", "none") not in ("none", None, ""):
            return LawnMowerActivity.ERROR

        # 2. Check toolplanner active tools (preferred — most granular)
        tools = self.coordinator.data.get("toolplanner", {}).get("tools", [])
        for tool in tools:
            if not tool.get("active"):
                continue
            tool_name = tool.get("name", "")
            if tool_name in ("mowing", "MowingPlannerTool"):
                return LawnMowerActivity.MOWING
            if tool_name == "docking":
                return LawnMowerActivity.RETURNING

        # 3. Fall back to activities/info fields
        activities = self.coordinator.data.get("activities", {})
        user_activity = activities.get("userActivity", "")
        sched_activity = activities.get("scheduledActivity", "")

        if user_activity == "MowActivity" or sched_activity in (
            "MowingPlannerActivity",
            "MowActivity",
        ):
            return LawnMowerActivity.MOWING

        if user_activity == "DockingActivity" or sched_activity == "DockingActivity":
            return LawnMowerActivity.RETURNING

        # 4. Check docking info for docked / charging state
        docking_info = self.coordinator.data.get("docking_info", {})
        docking_state = (docking_info.get("dockingState") or "").lower()
        charge_status = (docking_info.get("chargeStatus") or "").lower()

        docked_keywords = ("charging", "docked", "inchargingstation", "idle_docked")
        if any(kw in docking_state for kw in docked_keywords):
            return LawnMowerActivity.DOCKED
        if any(kw in charge_status for kw in ("charging", "full")):
            return LawnMowerActivity.DOCKED

        # 5. Also check toolplanner for "in charging station" blocked state
        for tool in tools:
            if tool.get("name") == "docking":
                blocked_by = tool.get("manual", {}).get("blockedBy", [])
                if any(b.get("name") == "inChargingStation" for b in blocked_by):
                    return LawnMowerActivity.DOCKED

        return LawnMowerActivity.PAUSED

    @property
    def extra_state_attributes(self) -> dict:
        """Return rich state attributes for dashboards and automations."""
        if not self.coordinator.data:
            return {}

        battery = self.coordinator.data.get("battery", {})
        mowing_info = self.coordinator.data.get("mowing_info", {})
        mowing_time = mowing_info.get("mowingTime", {})
        today_times = mowing_time.get("today", [0, 0])
        docking_info = self.coordinator.data.get("docking_info", {})
        activities = self.coordinator.data.get("activities", {})
        tools = self.coordinator.data.get("toolplanner", {}).get("tools", [])
        active_tools = [t["name"] for t in tools if t.get("active")]
        emergency = self.coordinator.data.get("emergency_stop", {})

        return {
            "battery_percentage":       battery.get("percentage"),
            "available_mowing_time":    battery.get("availableMowingTime"),
            "mowing_time_today_min":    round(today_times[1] / 60, 1) if len(today_times) > 1 else None,
            "active_time_today_min":    round(today_times[0] / 60, 1) if today_times else None,
            "mowing_time_total_h":      round(mowing_time.get("total", 0) / 3600, 1),
            "current_session_s":        mowing_time.get("current"),
            "zone_id_to_mow":           mowing_info.get("zoneIdToMow"),
            "today_end_time":           mowing_info.get("todayEndTime"),
            "docking_state":            docking_info.get("dockingState"),
            "charge_status":            docking_info.get("chargeStatus"),
            "charging_power_w":         docking_info.get("chargingPower"),
            "user_activity":            activities.get("userActivity"),
            "scheduled_activity":       activities.get("scheduledActivity"),
            "active_tools":             active_tools,
            "emergency_stop":           emergency.get("description", "none"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_start_mowing(self) -> None:
        """Start mowing (all zones, unlimited time)."""
        _LOGGER.info("Starting mowing for mower %s", self._ip_address)
        url = f"http://{self._ip_address}:8080/api/navigation/startmowing"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    params={"maxMowingTime": 0},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _LOGGER.info("Start mowing response: %s", resp.status)
            except aiohttp.ClientError as exc:
                _LOGGER.error("Failed to start mowing: %s", exc)
        await self.coordinator.async_request_refresh()

    async def async_dock(self) -> None:
        """Send mower back to the dock."""
        _LOGGER.info("Docking mower %s", self._ip_address)
        url = f"http://{self._ip_address}:8080/api/navigation/startdocking"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _LOGGER.info("Dock response: %s", resp.status)
            except aiohttp.ClientError as exc:
                _LOGGER.error("Failed to dock mower: %s", exc)
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause / stop the mower in place."""
        _LOGGER.info("Pausing mower %s", self._ip_address)
        url = f"http://{self._ip_address}:8080/api/navigation/stop"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _LOGGER.info("Pause response: %s", resp.status)
            except aiohttp.ClientError as exc:
                _LOGGER.error("Failed to pause mower: %s", exc)
        await self.coordinator.async_request_refresh()
