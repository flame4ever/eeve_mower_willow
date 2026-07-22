"""Button entities for EEVE Mower Willow.

Manual navigation buttons read their speed from the ManualDriveSpeed number
entity (number.manual_drive_speed) so that the user can adjust the speed
once and all movement buttons use it automatically.
"""
from __future__ import annotations

import logging
import aiohttp

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_IP_ADDRESS,
    MANUFACTURER,
    MODEL,
    NAME,
)

_LOGGER = logging.getLogger(__name__)

# Default values for navigation buttons
_DEFAULT_SPEED = 0.2
_DEFAULT_DISTANCE = 0.8
_DEFAULT_ROTATION = 90          # degrees
_DEFAULT_VOLUME = 80            # percent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower button entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    entities = [
        RebootControlButton(hass, ip_address),
        StartManualDrivingButton(hass, ip_address),
        StopManualDrivingButton(hass, ip_address),
        StopButton(hass, ip_address),
        StartDockingButton(hass, ip_address),
        StopDockingButton(hass, ip_address),
        HardEmergencyStopButton(hass, ip_address),
        ReleaseEmergencyStopButton(hass, ip_address),
        ForwardControlButton(hass, ip_address),
        BackwardControlButton(hass, ip_address),
        TurnLeftButton(hass, ip_address),
        TurnRightButton(hass, ip_address),
        PlaySoundButton(hass, ip_address),
        StopSoundButton(hass, ip_address),
        ClearRainSensorButton(hass, ip_address),
        ShutdownButton(hass, ip_address),
        MapBuildButton(hass, ip_address),
        MapExploreStartButton(hass, ip_address),
        MapExploreStopButton(hass, ip_address),
        MapExploreFinishButton(hass, ip_address),
        MapExploreAbortButton(hass, ip_address),
        RetryDockingButton(hass, ip_address),
        ToolplannerResumeButton(hass, ip_address),
        HeatmapResetButton(hass, ip_address),
        CameraLensResetButton(hass, ip_address),
        MapAutoalignButton(hass, ip_address),
    ]
    async_add_entities(entities)


class _MowerButton(ButtonEntity):

    _attr_has_entity_name = True
    """Base class for all mower buttons."""

    def __init__(self, hass: HomeAssistant, ip_address: str) -> None:
        """Initialize the button."""
        self._hass = hass
        self._ip_address = ip_address
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"

    @property
    def device_info(self) -> dict:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    def _get_speed(self) -> float:
        """Read the manual drive speed from the number entity."""
        state = self._hass.states.get("number.manual_drive_speed")
        if state and state.state not in (None, "unknown", "unavailable"):
            try:
                return float(state.state)
            except (ValueError, TypeError):
                pass
        return _DEFAULT_SPEED

    def _get_volume(self) -> int:
        """Read the audio volume from the number entity."""
        state = self._hass.states.get("number.audio_volume")
        if state and state.state not in (None, "unknown", "unavailable"):
            try:
                return int(float(state.state))
            except (ValueError, TypeError):
                pass
        return _DEFAULT_VOLUME

    async def _put(self, path: str, params: dict | None = None) -> int:
        """Issue a PUT request to the mower API and return the HTTP status."""
        url = f"http://{self._ip_address}:8080{path}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    params=params or {},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    _LOGGER.info("%s → HTTP %s", path, resp.status)
                    return resp.status
            except aiohttp.ClientError as exc:
                _LOGGER.error("Request to %s failed: %s", path, exc)
                return 0


# ---------------------------------------------------------------------------
# System buttons
# ---------------------------------------------------------------------------

class RebootControlButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reboot"
    """Reboot the mower."""

    @property
    def unique_id(self) -> str:
        return f"reboot_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:restart"

    async def async_press(self) -> None:
        _LOGGER.info("Rebooting mower %s", self._ip_address)
        await self._put("/api/maintenance/reboot")


class StartManualDrivingButton(_MowerButton):
    _attr_translation_key = "start_manual_driving"
    """Activate manual driving mode."""

    @property
    def unique_id(self) -> str:
        return f"start_manual_driving_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:steering"

    async def async_press(self) -> None:
        _LOGGER.info("Starting manual driving on mower %s", self._ip_address)
        await self._put("/api/navigation/startmanualdriving")


class StopButton(_MowerButton):
    _attr_translation_key = "stop"
    """Stop / pause the mower immediately."""

    @property
    def unique_id(self) -> str:
        return f"stop_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:stop-circle"

    async def async_press(self) -> None:
        _LOGGER.info("Stopping mower %s", self._ip_address)
        await self._put("/api/navigation/stop")


# ---------------------------------------------------------------------------
# Navigation buttons — speed comes from the ManualDriveSpeed number entity
# ---------------------------------------------------------------------------

class ForwardControlButton(_MowerButton):
    _attr_translation_key = "move_forward"
    """Move the mower forward."""

    @property
    def unique_id(self) -> str:
        return f"forward_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:arrow-up"

    async def async_press(self) -> None:
        speed = self._get_speed()
        _LOGGER.info("Moving mower %s forward at %.2f m/s", self._ip_address, speed)
        await self._put(
            "/api/navigation/forward",
            params={"speed": speed, "distance": _DEFAULT_DISTANCE},
        )


class BackwardControlButton(_MowerButton):
    _attr_translation_key = "move_backward"
    """Move the mower backward."""

    @property
    def unique_id(self) -> str:
        return f"backward_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:arrow-down"

    async def async_press(self) -> None:
        speed = self._get_speed()
        _LOGGER.info("Moving mower %s backward at %.2f m/s", self._ip_address, speed)
        await self._put(
            "/api/navigation/backwards",
            params={"speed": speed, "distance": _DEFAULT_DISTANCE},
        )


class TurnLeftButton(_MowerButton):
    _attr_translation_key = "turn_left"
    """Turn the mower 90° to the left using spinAround with negative rotation."""

    @property
    def unique_id(self) -> str:
        return f"turn_left_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:arrow-left"

    async def async_press(self) -> None:
        _LOGGER.info("Turning mower %s left (%d°)", self._ip_address, _DEFAULT_ROTATION)
        await self._put(
            "/api/navigation/spinAround",
            params={"speed": self._get_speed(), "rotation": -_DEFAULT_ROTATION},
        )


class TurnRightButton(_MowerButton):
    _attr_translation_key = "turn_right"
    """Turn the mower 90° to the right using spinAround with positive rotation."""

    @property
    def unique_id(self) -> str:
        return f"turn_right_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:arrow-right"

    async def async_press(self) -> None:
        _LOGGER.info("Turning mower %s right (%d°)", self._ip_address, _DEFAULT_ROTATION)
        await self._put(
            "/api/navigation/spinAround",
            params={"speed": self._get_speed(), "rotation": _DEFAULT_ROTATION},
        )


# ---------------------------------------------------------------------------
# Emergency stop buttons
# ---------------------------------------------------------------------------

class HardEmergencyStopButton(_MowerButton):
    _attr_translation_key = "hard_emergency_stop"
    """Perform an immediate hard emergency stop."""

    @property
    def unique_id(self) -> str:
        return f"hard_emergency_stop_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:stop-circle-outline"

    async def async_press(self) -> None:
        _LOGGER.warning("HARD EMERGENCY STOP on mower %s", self._ip_address)
        await self._put("/api/navigation/hardEmergencyStop")


class ReleaseEmergencyStopButton(_MowerButton):
    _attr_translation_key = "release_emergency_stop"
    """Release the emergency stop and resume normal operation."""

    @property
    def unique_id(self) -> str:
        return f"release_emergency_stop_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:play-circle"

    async def async_press(self) -> None:
        _LOGGER.info("Releasing emergency stop on mower %s", self._ip_address)
        await self._put("/api/navigation/releaseEmergencyStop")


# ---------------------------------------------------------------------------
# Audio buttons
# ---------------------------------------------------------------------------

class PlaySoundButton(_MowerButton):
    _attr_translation_key = "play_sound"
    """Play a sound (R2D2.wav) on the mower."""

    @property
    def unique_id(self) -> str:
        return f"play_sound_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:volume-high"

    async def async_press(self) -> None:
        volume = self._get_volume()
        _LOGGER.info("Playing sound on mower %s at volume %d%%", self._ip_address, volume)
        await self._put(
            "/api/maintenance/sound/play",
            params={"fileName": "R2D2.wav", "volume": volume},
        )


class StopSoundButton(_MowerButton):
    _attr_translation_key = "stop_sound"
    """Stop any currently playing sound."""

    @property
    def unique_id(self) -> str:
        return f"stop_sound_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:volume-off"

    async def async_press(self) -> None:
        _LOGGER.info("Stopping sound on mower %s", self._ip_address)
        await self._put("/api/maintenance/sound/stop")


# ---------------------------------------------------------------------------
# Navigation: Stop Mowing / Docking / Manual Driving
# ---------------------------------------------------------------------------

class StartDockingButton(_MowerButton):
    _attr_translation_key = "start_docking"
    """Send the mower back to the docking station."""

    @property
    def unique_id(self) -> str:
        return f"start_docking_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:home-import-outline"

    async def async_press(self) -> None:
        _LOGGER.info("Starting docking on mower %s", self._ip_address)
        await self._put("/api/navigation/startdocking")


class StopDockingButton(_MowerButton):
    _attr_translation_key = "stop_docking"
    """Cancel the docking process."""

    @property
    def unique_id(self) -> str:
        return f"stop_docking_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:home-remove-outline"

    async def async_press(self) -> None:
        _LOGGER.info("Stopping docking on mower %s", self._ip_address)
        await self._put("/api/navigation/stopdocking")


class StopManualDrivingButton(_MowerButton):
    _attr_translation_key = "stop_manual_driving"
    """Deactivate manual driving mode."""

    @property
    def unique_id(self) -> str:
        return f"stop_manual_driving_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:steering-off"

    async def async_press(self) -> None:
        _LOGGER.info("Stopping manual driving on mower %s", self._ip_address)
        await self._put("/api/navigation/stopmanualdriving")


# ---------------------------------------------------------------------------
# Maintenance: Rain sensor, shutdown
# ---------------------------------------------------------------------------

class ClearRainSensorButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "clear_rain_sensor"
    """Clear the rain sensor state."""

    @property
    def unique_id(self) -> str:
        return f"clear_rain_sensor_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:weather-sunny"

    async def async_press(self) -> None:
        _LOGGER.info("Clearing rain sensor on mower %s", self._ip_address)
        await self._put("/api/maintenance/clearRainSensor")


class ShutdownButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "shutdown"
    """Shut down the mower completely."""

    @property
    def unique_id(self) -> str:
        return f"shutdown_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:power"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disabled by default to prevent accidental shutdown."""
        return False

    async def async_press(self) -> None:
        _LOGGER.warning("Shutting down mower %s", self._ip_address)
        await self._put("/api/maintenance/shutdown")


# ---------------------------------------------------------------------------
# Map operations
# ---------------------------------------------------------------------------

class MapBuildButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "build_map"
    """Trigger a map rebuild from recorded data."""

    @property
    def unique_id(self) -> str:
        return f"map_build_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-plus"

    async def async_press(self) -> None:
        _LOGGER.info("Building map on mower %s", self._ip_address)
        await self._put("/api/maps/build")


class MapExploreStartButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "start_map_exploration"
    """Start automatic map exploration."""

    @property
    def unique_id(self) -> str:
        return f"map_explore_start_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-search"

    async def async_press(self) -> None:
        _LOGGER.info("Starting map exploration on mower %s", self._ip_address)
        await self._put(
            "/api/slam/mapExplore/start",
            params={"mode": "auto", "exploreTime": -1},
        )


class MapExploreStopButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "stop_map_exploration"
    """Stop the current map exploration."""

    @property
    def unique_id(self) -> str:
        return f"map_explore_stop_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-marker-off"

    async def async_press(self) -> None:
        _LOGGER.info("Stopping map exploration on mower %s", self._ip_address)
        await self._put(
            "/api/slam/mapExplore/stop",
            params={"mode": "auto"},
        )


class MapExploreFinishButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "finish_map_exploration"
    """Finish map exploration and save results."""

    @property
    def unique_id(self) -> str:
        return f"map_explore_finish_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-check"

    async def async_press(self) -> None:
        _LOGGER.info("Finishing map exploration on mower %s", self._ip_address)
        await self._put("/api/slam/mapExplore/finish")


class MapExploreAbortButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "abort_map_exploration"
    """Abort map exploration and discard results."""

    @property
    def unique_id(self) -> str:
        return f"map_explore_abort_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-marker-remove"

    async def async_press(self) -> None:
        _LOGGER.warning("Aborting map exploration on mower %s", self._ip_address)
        await self._put("/api/slam/mapExplore/abort")


# ---------------------------------------------------------------------------
# Navigation: Retry docking, Toolplanner, Heatmap, Camera calibration, Map autoalign
# ---------------------------------------------------------------------------

class RetryDockingButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "retry_docking"
    """Retry docking using ExitAndRetry start state."""

    @property
    def unique_id(self) -> str:
        return f"retry_docking_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:ev-station"

    async def async_press(self) -> None:
        _LOGGER.info("Retrying docking on mower %s", self._ip_address)
        await self._put("/navigation/dockingFrom", params={"startState": "ExitAndRetry"})


class ToolplannerResumeButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "resume_toolplanner"
    """Resume the toolplanner after a pause."""

    @property
    def unique_id(self) -> str:
        return f"toolplanner_resume_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:play-circle-outline"

    async def async_press(self) -> None:
        _LOGGER.info("Resuming toolplanner on mower %s", self._ip_address)
        await self._put("/api/toolplanner/resume")


class HeatmapResetButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_heatmap"
    """Reset the SLAM heatmap grid."""

    @property
    def unique_id(self) -> str:
        return f"heatmap_reset_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-marker-off"

    async def async_press(self) -> None:
        _LOGGER.info("Resetting heatmap on mower %s", self._ip_address)
        await self._put("/slam/gridmaps/heatmap/reset")


class CameraLensResetButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_camera_calibration"
    """Reset camera lens calibration (causes a reboot)."""

    @property
    def unique_id(self) -> str:
        return f"camera_lens_reset_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:camera-retake"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disabled by default — this action causes a mower reboot."""
        return False

    async def async_press(self) -> None:
        _LOGGER.warning("Resetting camera lens calibration on mower %s (will reboot)", self._ip_address)
        await self._put("/api/calibration/camera/lens/reset")


class MapAutoalignButton(_MowerButton):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "auto_align_maps"
    """Trigger automatic map alignment."""

    @property
    def unique_id(self) -> str:
        return f"map_autoalign_button_{self._ip_address.replace('.', '_')}"


    @property
    def icon(self) -> str:
        return "mdi:map-check"

    async def async_press(self) -> None:
        _LOGGER.info("Auto-aligning maps on mower %s", self._ip_address)
        await self._put("/api/maps/autoalign")
