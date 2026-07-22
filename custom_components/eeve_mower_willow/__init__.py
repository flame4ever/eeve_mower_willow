"""EEVE Mower Willow Integration for Home Assistant."""
import logging
from homeassistant import config_entries, core

from .const import DOMAIN, CONF_IP_ADDRESS
from .coordinator import EeveMowerCoordinator, EeveMowerSystemCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    "lawn_mower",    # Native HA mower entity (start / dock / pause)
    "sensor",        # All numeric and text sensors
    "binary_sensor", # Boolean states (is_mowing, is_charging, has_error, ...)
    "button",        # Reboot, manual drive, sound buttons
    "camera",        # Front camera stream
    "select",        # Zone selection, mowing pattern, frequency, obstacle sensitivity
    "number",        # Max mowing time, drive speed, volume, thresholds
    "switch",        # Weekday mowing schedule (Mon-Sun)
    "text",          # Mower name
]


async def async_setup(hass: core.HomeAssistant, config: dict) -> bool:
    """Set up the EEVE Mower Willow component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Set up EEVE Mower Willow from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    ip_address = entry.data[CONF_IP_ADDRESS]

    fast_coordinator = EeveMowerCoordinator(hass, entry, ip_address)
    system_coordinator = EeveMowerSystemCoordinator(hass, entry, ip_address)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": fast_coordinator,
        "system_coordinator": system_coordinator,
    }

    _LOGGER.info("Setting up %s (IP: %s)", DOMAIN, ip_address)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.async_create_task(fast_coordinator.async_request_refresh())
    hass.async_create_task(system_coordinator.async_request_refresh())

    return True


async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
