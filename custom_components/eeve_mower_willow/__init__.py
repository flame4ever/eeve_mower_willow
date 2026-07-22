"""EEVE Mower Willow Integration for Home Assistant."""
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries, core
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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

SERVICE_DRIVE = "drive"

DRIVE_SCHEMA = vol.Schema(
    {
        vol.Required("action"): vol.In(
            ["forward", "backwards", "spin", "stop"]
        ),
        vol.Optional("speed", default=0.2): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=1.0)
        ),
        vol.Optional("distance", default=0.3): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=5.0)
        ),
        vol.Optional("turn_radius", default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=-10.0, max=10.0)
        ),
        vol.Optional("rotation", default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=-360.0, max=360.0)
        ),
        vol.Optional("entry_id"): cv.string,
    }
)


def _resolve_ip(hass: core.HomeAssistant, data: dict) -> str | None:
    """Resolve the mower IP: explicit entry_id, else the first EEVE config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    if data.get("entry_id"):
        for e in entries:
            if e.entry_id == data["entry_id"]:
                return e.data.get(CONF_IP_ADDRESS)
    return entries[0].data.get(CONF_IP_ADDRESS)


def _register_drive_service(hass: core.HomeAssistant) -> None:
    """Register the eeve_mower.drive service (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_DRIVE):
        return

    async def _handle_drive(call: core.ServiceCall) -> None:
        ip = _resolve_ip(hass, call.data)
        if not ip:
            _LOGGER.error("drive service: no EEVE mower configured")
            return
        action = call.data["action"]
        speed = call.data["speed"]
        host = f"http://{ip}:8080"
        # Firmware 6.8.0 endpoint quirks:
        #   forward   -> PUT  /api/navigation/forward
        #   backwards -> GET  /navigation/backwards   (the /api PUT variant is 404)
        #   spin      -> GET  /navigation/spinaround  (lowercase; /api & camelCase are 404)
        #   stop      -> PUT  /api/navigation/stop
        if action == "stop":
            method, url, params = "PUT", f"{host}/api/navigation/stop", {}
        elif action == "forward":
            method = "PUT"
            url = f"{host}/api/navigation/forward"
            # Curved driving uses turnRadius (signed): + = right, - = left,
            # smaller magnitude = tighter curve. This works reliably even when
            # streamed, unlike the rotation parameter.
            params = {
                "speed": speed,
                "distance": abs(call.data["distance"]),
                "turnRadius": call.data["turn_radius"],
            }
        elif action == "backwards":
            method = "GET"
            url = f"{host}/navigation/backwards"
            params = {
                "speed": speed,
                "distance": abs(call.data["distance"]),
                "turnRadius": call.data["turn_radius"],
            }
        else:  # spin (rotate in place)
            method = "GET"
            url = f"{host}/navigation/spinaround"
            params = {"speed": speed, "rotation": call.data["rotation"]}

        session = async_get_clientsession(hass)
        try:
            async with session.request(
                method,
                url,
                params=params,
                headers={"accept": "*/*"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("drive %s -> HTTP %s", action, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("drive %s failed: %s", action, exc)

    hass.services.async_register(
        DOMAIN, SERVICE_DRIVE, _handle_drive, schema=DRIVE_SCHEMA
    )
    _LOGGER.debug("Registered %s.%s service", DOMAIN, SERVICE_DRIVE)


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
        "ip": ip_address,
    }

    _LOGGER.info("Setting up %s (IP: %s)", DOMAIN, ip_address)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_drive_service(hass)

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
        # Remove the service when the last mower is unloaded
        if not hass.config_entries.async_entries(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_DRIVE)
    return unload_ok
