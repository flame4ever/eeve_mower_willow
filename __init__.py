import logging
from homeassistant import config_entries, core

from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [ "switch", "camera", "sensor", "button" ]

async def async_setup(hass: core.HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):
    hass.data[DOMAIN][entry.entry_id] = {}
    _LOGGER.info(f"Setting up {DOMAIN} with {entry.data}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok