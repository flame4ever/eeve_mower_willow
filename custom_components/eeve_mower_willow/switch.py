"""Switch entities for EEVE Mower Willow.

MowDaySwitch (x7)  - Wochentag-Maehplanung (Montag-Sonntag).
                     GET/POST /settings/mowingPlanner/mowOn{Day}
                     Antwort/Body: JSON boolean (true / false)

Damit laesst sich der taegliche Maehplan direkt aus HA oder Automationen steuern,
z. B. an Regentagen abschalten oder vor Partys am Wochenende deaktivieren.
"""
from __future__ import annotations

import asyncio
import logging
from time import monotonic

import aiohttp

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME

_LOGGER = logging.getLogger(__name__)

# (HA-Anzeigename, API-Schluessel im Pfad)
_DAYS = [
    ("Monday",    "mowOnMonday"),
    ("Tuesday",   "mowOnTuesday"),
    ("Wednesday", "mowOnWednesday"),
    ("Thursday",  "mowOnThursday"),
    ("Friday",    "mowOnFriday"),
    ("Saturday",  "mowOnSaturday"),
    ("Sunday",    "mowOnSunday"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower switch entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    entities = [
        MowDaySwitch(ip_address, display_name, api_key)
        for display_name, api_key in _DAYS
    ]
    entities.append(BeaconsSwitch(ip_address))
    entities.append(AutoAnnotationSwitch(ip_address))
    entities.append(ManualDrivingSwitch(ip_address))
    entities.append(MowingMotorSwitch(ip_address))
    entities.append(DockingSwitch(ip_address))
    entities.append(EmergencyStopSwitch(ip_address))
    entities.append(SoundSwitch(hass, ip_address))
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Manual driving mode switch
# ---------------------------------------------------------------------------

class ManualDrivingSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_translation_key = "manual_driving"
    """Enables/disables manual driving mode (required for the joystick and the
    cutting motor).

    on  -> PUT /api/navigation/startmanualdriving
    off -> PUT /api/navigation/stopmanualdriving
    state read back from GET /api/activities/info -> userActivity == "manualdriving"
    Turning it off makes the mower leave manual mode (it may return to the dock).
    """

    _attr_icon = "mdi:steering"
    _GRACE = 4.0

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        self._last_cmd: float = 0.0
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"manual_driving_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """Read whether the mower is currently in manual driving mode."""
        if (monotonic() - self._last_cmd) < self._GRACE:
            return
        url = f"http://{self._ip_address}:8080/api/activities/info"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        activity = data.get("userActivity", "") if isinstance(data, dict) else ""
                        self._state = activity == "manualdriving"
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read manual driving state: %s", exc)

    async def _put(self, path: str) -> bool:
        url = f"http://{self._ip_address}:8080{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    _LOGGER.error("Manual driving %s failed: HTTP %s", path, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Manual driving %s failed: %s", path, exc)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        if await self._put("/api/navigation/startmanualdriving"):
            self._state = True
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Manual driving -> ON")

    async def async_turn_off(self, **kwargs) -> None:
        if await self._put("/api/navigation/stopmanualdriving"):
            self._state = False
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Manual driving -> OFF")


# ---------------------------------------------------------------------------
# Mowing (cutting) motor switch
# ---------------------------------------------------------------------------

class MowingMotorSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_translation_key = "mowing_motor"
    """Turns the cutting (mowing) motor on/off, like the web UI "Start/Stop mower".

    The cutting motor only spins while manual driving mode is active, so turning
    the switch on first enables manual driving, then spins the motor up:
      on  -> PUT /api/navigation/startmanualdriving  then  GET /navigation/startmower?throttle=1.0
      off -> GET /navigation/stopmower   (stays in manual mode)
    The state is read back from GET /api/system/mowerInfo -> rpm (>0 = running).
    Because the motor needs ~2 s to spin up and ~1.5 s to spin down, readback is
    suppressed for a short grace period after a manual toggle so the switch does
    not flip back mid-ramp.
    """

    _attr_icon = "mdi:mower"
    # Ignore rpm readback for this many seconds after a manual on/off command,
    # to bridge the motor spin-up (~2 s) / spin-down (~1.5 s) time.
    _GRACE = 6.0

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        self._last_cmd: float = 0.0
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"mowing_motor_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """Read the cutting-motor RPM; >0 means the motor is spinning."""
        # During the grace period after a toggle, trust the optimistic state.
        if (monotonic() - self._last_cmd) < self._GRACE:
            return
        url = f"http://{self._ip_address}:8080/api/system/mowerInfo"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        rpm = data.get("rpm", 0) if isinstance(data, dict) else 0
                        self._state = bool(rpm and float(rpm) > 0)
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read mower motor rpm: %s", exc)

    async def _call(self, method: str, path: str) -> bool:
        """Issue a request to the mower and return True on HTTP 200."""
        url = f"http://{self._ip_address}:8080{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    _LOGGER.error("Mower motor %s %s failed: HTTP %s", method, path, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Mower motor %s %s failed: %s", method, path, exc)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        # The cutting motor only spins in manual driving mode, so enable it
        # first. The mower needs a short moment to enter manual mode before it
        # accepts startmower — without the pause the motor stays at 0 rpm.
        await self._call("PUT", "/api/navigation/startmanualdriving")
        await asyncio.sleep(0.8)
        if await self._call("GET", "/navigation/startmower?throttle=1.0"):
            self._state = True
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Cutting motor -> ON")

    async def async_turn_off(self, **kwargs) -> None:
        if await self._call("GET", "/navigation/stopmower"):
            self._state = False
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Cutting motor -> OFF")


# ---------------------------------------------------------------------------
# Docking switch
# ---------------------------------------------------------------------------

class DockingSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_translation_key = "docking"
    """Sends the mower to the dock / cancels docking.

    on  -> PUT /api/navigation/startdocking
    off -> PUT /api/navigation/stopdocking
    state read back from GET /api/system/dockingInfo:
      on while a docking maneuver runs (dockingState != "Idle") or while charging.
    """

    _attr_icon = "mdi:home-import-outline"
    _GRACE = 4.0

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        self._last_cmd: float = 0.0
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"docking_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """On while docking is in progress or the mower is charging."""
        if (monotonic() - self._last_cmd) < self._GRACE:
            return
        url = f"http://{self._ip_address}:8080/api/system/dockingInfo"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, dict):
                            docking = data.get("dockingState", "Idle") not in ("Idle", "", None)
                            charging = (
                                float(data.get("chargingCurrent", 0) or 0) > 0
                                or float(data.get("chargingPower", 0) or 0) > 0
                            )
                            self._state = docking or charging
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read docking state: %s", exc)

    async def _put(self, path: str) -> bool:
        url = f"http://{self._ip_address}:8080{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    _LOGGER.error("Docking %s failed: HTTP %s", path, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Docking %s failed: %s", path, exc)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        if await self._put("/api/navigation/startdocking"):
            self._state = True
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Docking -> START")

    async def async_turn_off(self, **kwargs) -> None:
        if await self._put("/api/navigation/stopdocking"):
            self._state = False
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Docking -> STOP")


# ---------------------------------------------------------------------------
# Emergency stop switch
# ---------------------------------------------------------------------------

class EmergencyStopSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_translation_key = "emergency_stop"
    """Hard emergency stop (on) / release (off).

    on  -> PUT /api/navigation/hardEmergencyStop
    off -> PUT /api/navigation/releaseEmergencyStop
    state read back from GET /api/system/emergencyStop -> description != "none".
    """

    _attr_icon = "mdi:alert-octagon"
    _GRACE = 3.0

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        self._last_cmd: float = 0.0
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"emergency_stop_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """On while an emergency stop is active (description != 'none')."""
        if (monotonic() - self._last_cmd) < self._GRACE:
            return
        url = f"http://{self._ip_address}:8080/api/system/emergencyStop"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        desc = data.get("description") if isinstance(data, dict) else None
                        # "none" (string) or empty/[] means no active stop.
                        self._state = bool(desc) and desc not in ("none", "None", [], "[]")
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read emergency stop state: %s", exc)

    async def _put(self, path: str) -> bool:
        url = f"http://{self._ip_address}:8080{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    headers={"accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    _LOGGER.error("Emergency stop %s failed: HTTP %s", path, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Emergency stop %s failed: %s", path, exc)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        if await self._put("/api/navigation/hardEmergencyStop"):
            self._state = True
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.warning("Emergency stop -> ACTIVE")

    async def async_turn_off(self, **kwargs) -> None:
        if await self._put("/api/navigation/releaseEmergencyStop"):
            self._state = False
            self._last_cmd = monotonic()
            self.async_write_ha_state()
            _LOGGER.info("Emergency stop -> RELEASED")


# ---------------------------------------------------------------------------
# Sound switch (optimistic — the mower exposes no "is playing" state)
# ---------------------------------------------------------------------------

class SoundSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_translation_key = "sound"
    """Plays a sound (on) / stops it (off).

    Firmware 6.8.0 serves these as GET without the /api prefix (the PUT /api
    variant resets the connection):
      on  -> GET /maintenance/sound/play?fileName=R2D2.wav&volume=<audio_volume>
      off -> GET /maintenance/sound/stop
    The mower exposes no playback state, so this switch is optimistic
    (assumed_state) and simply reflects the last command.
    """

    _attr_icon = "mdi:volume-high"
    _attr_assumed_state = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, ip_address: str) -> None:
        self._hass = hass
        self._ip_address = ip_address
        self._state: bool = False
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"sound_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    def _get_volume(self) -> int:
        """Read the playback volume from the mower's Volume number entity.

        Resolved via the entity registry (unique_id ``audio_volume_<ip>``) so it
        keeps working even if the entity_id has been renamed.
        """
        registry = er.async_get(self._hass)
        safe_ip = self._ip_address.replace(".", "_")
        entity_id = registry.async_get_entity_id(
            "number", DOMAIN, f"audio_volume_{safe_ip}"
        )
        if entity_id:
            state = self._hass.states.get(entity_id)
            if state and state.state not in (None, "unknown", "unavailable"):
                try:
                    return int(float(state.state))
                except (ValueError, TypeError):
                    pass
        return 80

    async def _get(self, path: str, params: dict | None = None) -> bool:
        url = f"http://{self._ip_address}:8080{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "*/*"},
                    params=params or {},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return True
                    _LOGGER.error("Sound %s failed: HTTP %s", path, resp.status)
        except aiohttp.ClientError as exc:
            _LOGGER.error("Sound %s failed: %s", path, exc)
        return False

    async def async_turn_on(self, **kwargs) -> None:
        if await self._get(
            "/maintenance/sound/play",
            params={"fileName": "R2D2.wav", "volume": self._get_volume()},
        ):
            self._state = True
            self.async_write_ha_state()
            _LOGGER.info("Sound -> PLAY")

    async def async_turn_off(self, **kwargs) -> None:
        if await self._get("/maintenance/sound/stop"):
            self._state = False
            self.async_write_ha_state()
            _LOGGER.info("Sound -> STOP")


class MowDaySwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    """Ein Schalter pro Wochentag, der den Maeher an diesem Tag aktiviert/deaktiviert.

    GET  /settings/mowingPlanner/mowOn{Day}  -> JSON boolean
    POST /settings/mowingPlanner/mowOn{Day}  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:calendar-check"

    def __init__(self, ip_address: str, display_name: str, api_key: str) -> None:
        self._ip_address = ip_address
        self._display_name = display_name
        self._api_key = api_key
        self._state: bool = True
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"mow_{api_key.lower()}_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"
        self._attr_translation_key = f"mow_on_{display_name.lower()}"

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
        return self._state

    async def async_update(self) -> None:
        """Read the current mowing day setting from the mower."""
        url = f"http://{self._ip_address}:8080/settings/mowingPlanner/{self._api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read mow day %s: %s", self._display_name, exc)

    async def _set_day(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/mowingPlanner/{self._api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("Mow on %s -> %s", self._display_name, enabled)
                    else:
                        _LOGGER.error(
                            "Set mow day %s failed: HTTP %s",
                            self._display_name,
                            resp.status,
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set mow day %s failed: %s", self._display_name, exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_day(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_day(False)


# ---------------------------------------------------------------------------
# Beacons switch
# ---------------------------------------------------------------------------

class BeaconsSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "starlight_beacons"
    """Toggles the StarLight LED beacon on/off.

    GET  /settings/beacons/enabled  -> JSON boolean
    POST /settings/beacons/enabled  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:lightbulb-group"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"beacons_enabled_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """Read the current beacon state from the mower."""
        url = f"http://{self._ip_address}:8080/settings/beacons/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read beacons enabled: %s", exc)

    async def _set_beacons(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/beacons/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("StarLight Beacons -> %s", enabled)
                    else:
                        _LOGGER.error(
                            "Set beacons enabled failed: HTTP %s", resp.status
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set beacons enabled failed: %s", exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_beacons(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_beacons(False)


# ---------------------------------------------------------------------------
# Auto annotation switch
# ---------------------------------------------------------------------------

class AutoAnnotationSwitch(SwitchEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "auto_annotation"
    """Toggles AI auto-annotation of obstacles on/off.

    GET  /settings/autoAnnotation/enabled  -> JSON boolean
    POST /settings/autoAnnotation/enabled  -> Body: JSON boolean (true/false)
    """

    _attr_icon = "mdi:robot"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._state: bool = False
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"auto_annotation_enabled_{safe_ip}"
        self._device_id = f"eeve_mower_{safe_ip}"

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
        return self._state

    async def async_update(self) -> None:
        """Read the current auto-annotation state from the mower."""
        url = f"http://{self._ip_address}:8080/settings/autoAnnotation/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        value = await resp.json()
                        if isinstance(value, bool):
                            self._state = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read auto annotation enabled: %s", exc)

    async def _set_auto_annotation(self, enabled: bool) -> None:
        """POST the new boolean value to the mower."""
        url = f"http://{self._ip_address}:8080/settings/autoAnnotation/enabled"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=enabled,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        self._state = enabled
                        self.async_write_ha_state()
                        _LOGGER.info("Auto Annotation -> %s", enabled)
                    else:
                        _LOGGER.error(
                            "Set auto annotation enabled failed: HTTP %s", resp.status
                        )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set auto annotation enabled failed: %s", exc)

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_auto_annotation(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_auto_annotation(False)
