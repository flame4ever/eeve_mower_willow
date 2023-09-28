import logging
from homeassistant import config_entries, core

from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: core.HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):
    hass.data[DOMAIN][entry.entry_id] = {}
    _LOGGER.info(f"Setting up {DOMAIN} with {entry.data}")

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "switch")
    )

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "camera")
    )
    return True

async def async_unload_entry(hass: core.HomeAssistant, entry: config_entries.ConfigEntry):
    await hass.config_entries.async_forward_entry_unload(entry, "switch")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
