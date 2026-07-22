"""Select entities for EEVE Mower Willow.

ZoneSelectEntity         – wählt die zu mähende Zone und startet das Mähen.
                           Zonenliste wird beim Start per HTTP geladen UND aus dem
                           System-Coordinator aktualisiert (alle 5 Minuten).

MowingFrequencySelect    – stellt die Mähfrequenz ein.
                           Werte: STOP / LESS / NORMAL / MORE / CONTINUOUS
                           API: POST /settings/mowingPlanner/mowingFrequency
                                Body: JSON-String, z. B. "NORMAL"

ZoneMowingPatternSelect  – Mähmuster pro Zone (RANDOM / LINES / SPIRAL).
                           Liest aus system-coordinator zone_settings;
                           schreibt via GET /settings/zones → modify → POST /settings/zones.
"""
from __future__ import annotations

import logging
import json
import time
import aiohttp
import asyncio
import urllib.request

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_IP_ADDRESS, MANUFACTURER, MODEL, NAME
from .coordinator import EeveMowerCoordinator, EeveMowerSystemCoordinator, async_fetch_zone_settings

_LOGGER = logging.getLogger(__name__)


async def _post_zones_urllib(url: str, zone_data: dict) -> int:
    """POST zone data using urllib (bypasses aiohttp connection issues)."""
    import json as _json
    payload = _json.dumps(zone_data).encode("utf-8")
    def _do_post():
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "accept": "application/json",
                "Connection": "close",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status
    return await asyncio.get_event_loop().run_in_executor(None, _do_post)


async def _set_all_grass_zones(hass, ip_address, apply_fn) -> int | None:
    """GET /settings/zones, apply apply_fn(zoneProperties) to every GRASSZONE, POST once."""
    url = f"http://{ip_address}:8080/settings/zones"
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, headers={"accept": "application/json"},
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                _LOGGER.error("GET /settings/zones failed: HTTP %s", resp.status)
                return None
            zone_data = await resp.json()
    except aiohttp.ClientError as exc:
        _LOGGER.error("GET /settings/zones failed: %s", exc)
        return None
    count = 0
    for feature in zone_data.get("features", []):
        props = feature.get("properties", {})
        if props.get("zoneType") != "GRASSZONE":
            continue
        apply_fn(props.setdefault("zoneProperties", {}))
        count += 1
    if count == 0:
        _LOGGER.error("No GRASSZONE features found in /settings/zones")
        return None
    try:
        return await _post_zones_urllib(url, zone_data)
    except Exception as exc:
        _LOGGER.error("POST /settings/zones failed: %s", exc)
        return None


OPTION_ALL_ZONES = "All Zones"

MOWING_FREQUENCY_OPTIONS = ["STOP", "LESS", "NORMAL", "MORE", "CONTINUOUS"]

MOWING_PATTERN_OPTIONS = ["RANDOM", "LINES", "SPIRAL"]

# Obstacle sensitivity modes (API values → displayed as-is in HA)
OBSTACLE_SENSITIVITY_OPTIONS = ["CHICKEN_MODE", "CAUTIOUS_CAT", "OFF_ROAD_REBEL", "TANK_MODE"]

EMOTION_OPTIONS = [
    "HardEmergencyStop", "EmergencyStop", "Docked", "FollowPersons", "WaitForPersons",
    "NoPersonFound", "SupervisedMappingFailed", "Docking", "QrScanning", "QrScanned",
    "WifiConnected", "WifiFailed", "BackendConnected", "UserLinked", "BatteryEmpty",
    "BatteryLow", "BatteryMedium", "BatteryHigh", "BatteryFull", "RemoteControl",
]

PERSON_SCANNING_BEHAVIOUR_OPTIONS = ["off", "cautious", "normal", "aggressive"]

SQUARE_METER_PER_HOUR_MAP: dict[str, int] = {
    "Auto": -1,
    "Slow (30 m²/h)": 30,
    "Normal (45 m²/h)": 45,
    "Fast (90 m²/h)": 90,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EEVE Mower select entities."""
    ip_address = entry.data[CONF_IP_ADDRESS]
    fast_coord: EeveMowerCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    system_coord: EeveMowerSystemCoordinator = hass.data[DOMAIN][entry.entry_id]["system_coordinator"]

    # --- global select entities (always present) ----------------------------
    entities: list[SelectEntity] = [
        ZoneSelectEntity(fast_coord, system_coord, ip_address),
        MowingFrequencySelect(ip_address),
        ObstacleSensitivitySelect(ip_address),
        GlobalMowingPatternSelect(ip_address),
        EmotionSelect(ip_address),
        PersonScanningBehaviourSelect(ip_address),
        SquareMeterPerHourSelect(ip_address),
        AllZonesMowingPatternSelect(system_coord, ip_address),
        AllZonesMowingFrequencySelect(system_coord, ip_address),
        AllZonesObstacleSensitivitySelect(system_coord, ip_address),
    ]

    # --- per-zone select entities (one per GRASSZONE) ---
    zone_list = await async_fetch_zone_settings(ip_address)
    for zone_id, zone_name, zone_props in zone_list:
        # Mowing pattern per zone
        initial_pattern = (
            zone_props.get("mowingPlanner", {}).get("mowingPattern", "RANDOM")
        )
        entities.append(
            ZoneMowingPatternSelect(
                system_coord, ip_address, zone_id, zone_name, initial_pattern
            )
        )

        # Mowing frequency per zone (NEW)
        initial_frequency = (
            zone_props.get("mowingPlanner", {}).get("mowingFrequency", "NORMAL")
        )
        entities.append(
            ZoneMowingFrequencySelect(
                system_coord, ip_address, zone_id, zone_name, initial_frequency
            )
        )

        # Obstacle sensitivity per zone (NEW)
        initial_sensitivity = (
            zone_props.get("mowingPlanner", {}).get("obstacleSensitivity", "OFF_ROAD_REBEL")
        )
        entities.append(
            ZoneObstacleSensitivitySelect(
                system_coord, ip_address, zone_id, zone_name, initial_sensitivity
            )
        )

    async_add_entities(entities, update_before_add=False)


# ---------------------------------------------------------------------------
# Zone select
# ---------------------------------------------------------------------------

class ZoneSelectEntity(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mowing_zone"
    """Wählt eine Mähzone und startet das Mähen.

    Strategie:
    - async_added_to_hass() lädt die Zonen per direktem HTTP-Request
      (sofort, unabhängig vom Coordinator-Takt)
    - System-Coordinator liefert alle 5 Minuten aktuelle Zonenliste
    - kein CoordinatorEntity (würde async_update überschreiben)
    """

    _attr_icon = "mdi:map-marker-multiple"
    should_poll = False  # Wir nutzen Coordinator + einmaligen HTTP-Call

    def __init__(
        self,
        fast_coordinator: EeveMowerCoordinator,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
    ) -> None:
        self._fast_coordinator = fast_coordinator
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_map: dict[str, str] = {}   # Anzeigename → Zone-ID
        self._current_option: str = OPTION_ALL_ZONES
        self._attr_unique_id = f"zone_select_{ip_address.replace('.', '_')}"
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
    def options(self) -> list[str]:
        return [OPTION_ALL_ZONES] + list(self._zone_map.keys())

    @property
    def current_option(self) -> str:
        if self._current_option not in self.options:
            return OPTION_ALL_ZONES
        return self._current_option

    # ------------------------------------------------------------------
    # Hilfsmethode: Zonen aus einem API-Ergebnis (dict oder list) parsen
    # ------------------------------------------------------------------

    def _parse_zones(self, data: object) -> dict[str, str]:
        """Zonenliste aus dem API-Ergebnis in {Anzeigename: zone_id} umwandeln."""
        result: dict[str, str] = {}
        if isinstance(data, dict):
            # Format: {"GRASSZONE_id": "Grass Zone 1", ...}
            for zone_id, zone_name in data.items():
                if zone_id and zone_name:
                    result[str(zone_name)] = str(zone_id)
        elif isinstance(data, list):
            # Fallback: [{"id": ..., "name": ...}, ...]
            for zone in data:
                if not isinstance(zone, dict):
                    continue
                name = (
                    zone.get("name")
                    or zone.get("zoneName")
                    or str(zone.get("id", ""))
                )
                zone_id = zone.get("id") or zone.get("zoneId")
                if name and zone_id is not None:
                    result[str(name)] = str(zone_id)
        return result

    # ------------------------------------------------------------------
    # Initialisierung: Zonen direkt per HTTP laden (schnell & zuverlässig)
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Zonen per HTTP laden + Coordinator-Listener registrieren."""
        await super().async_added_to_hass()

        # 1. Direkt per HTTP laden — sofort ohne auf Coordinator warten
        await self._fetch_zones_http()

        # 2. System-Coordinator Listener: hält Zonen alle 5 Min aktuell
        self.async_on_remove(
            self._system_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

        # 3. Falls Coordinator bereits Daten hat, sofort übernehmen
        if self._system_coordinator.data:
            self._apply_coordinator_zones(self._system_coordinator.data)

        self.async_write_ha_state()

    async def _fetch_zones_http(self) -> None:
        """Zonen direkt per HTTP holen (unabhängig vom Coordinator)."""
        url = f"http://{self._ip_address}:8080/api/zones/list"
        headers = {"accept": "application/json"}
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_map = self._parse_zones(data)
                    self._zone_map = new_map
                    _LOGGER.info("Mowing zones loaded: %s", list(new_map.keys()))
                else:
                    _LOGGER.warning("Zones endpoint returned HTTP %s", resp.status)
        except Exception as exc:
            _LOGGER.warning("Could not load mowing zones: %s", exc)

    def _apply_coordinator_zones(self, coordinator_data: dict) -> None:
        """Zonen aus Coordinator-Daten übernehmen (wenn neuer als HTTP-Cache)."""
        zones_raw = coordinator_data.get("zones")
        if zones_raw is None:
            return
        new_map = self._parse_zones(zones_raw)
        if new_map:  # Nur überschreiben wenn nicht leer
            self._zone_map = new_map
            _LOGGER.debug("Zones updated from coordinator: %s", list(new_map.keys()))
        if self._current_option not in self.options:
            self._current_option = OPTION_ALL_ZONES

    @callback
    def _handle_coordinator_update(self) -> None:
        """Wird aufgerufen wenn System-Coordinator neue Daten hat."""
        if self._system_coordinator.data:
            self._apply_coordinator_zones(self._system_coordinator.data)
        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Zone auswählen → Mähen starten
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        """Wählt eine Zone und startet das Mähen in dieser Zone."""
        headers = {"accept": "*/*"}

        if option == OPTION_ALL_ZONES:
            url = f"http://{self._ip_address}:8080/api/navigation/startmowing"
            params: dict = {"maxMowingTime": 0}
        else:
            zone_id = self._zone_map.get(option)
            if zone_id is None:
                _LOGGER.error("Unknown zone: %s", option)
                return
            url = f"http://{self._ip_address}:8080/api/navigation/startmowing"
            params = {"zoneId": zone_id, "maxMowingTime": 0}

        session = async_get_clientsession(self.hass)
        try:
            async with session.put(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info(
                        "Mowing started: zone '%s' (id=%s)",
                        option,
                        params.get("zoneId", "all"),
                    )
                    self._current_option = option
                    self.async_write_ha_state()
                    await self._fast_coordinator.async_request_refresh()
                else:
                    _LOGGER.error(
                        "Start mowing zone '%s' failed: HTTP %s",
                        option,
                        resp.status,
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Start mowing zone '%s' failed: %s", option, exc)


# ---------------------------------------------------------------------------
# Mowing Frequency select
# ---------------------------------------------------------------------------

class MowingFrequencySelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mowing_frequency"
    """Stellt die Mähfrequenz des Mähers ein.

    Verfügbare Werte: STOP | LESS | NORMAL | MORE | CONTINUOUS

    GET  http://<ip>:8080/settings/mowingPlanner/mowingFrequency
         → JSON-String, z. B. "NORMAL"

    POST http://<ip>:8080/settings/mowingPlanner/mowingFrequency
         Body: JSON-String, z. B. "LESS"   (Content-Type: application/json)
    """

    _attr_icon = "mdi:calendar-sync"
    _attr_options = MOWING_FREQUENCY_OPTIONS

    _ENDPOINT = "/settings/mowingPlanner/mowingFrequency"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = "NORMAL"
        self._attr_unique_id = f"mowing_frequency_{ip_address.replace('.', '_')}"
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
    def options(self) -> list[str]:
        return MOWING_FREQUENCY_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    # ------------------------------------------------------------------
    # Aktuelle Frequenz lesen
    # ------------------------------------------------------------------

    async def async_update(self) -> None:
        """Aktuelle Mähfrequenz vom Mäher lesen."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        headers = {"accept": "application/json"}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    # Antwort ist ein reiner JSON-String, z. B. "NORMAL"
                    value = await resp.json()
                    if isinstance(value, str) and value in MOWING_FREQUENCY_OPTIONS:
                        self._current_option = value
                        _LOGGER.debug("Mowing frequency: %s", value)
                    else:
                        _LOGGER.debug("Unknown frequency value: %s", value)
                else:
                    _LOGGER.debug(
                        "Mowing frequency endpoint: HTTP %s", resp.status
                    )
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read mowing frequency: %s", exc)

    # ------------------------------------------------------------------
    # Frequenz setzen
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        """Sendet die gewählte Mähfrequenz an den Mäher."""
        if option not in MOWING_FREQUENCY_OPTIONS:
            _LOGGER.error("Invalid mowing frequency: %s", option)
            return

        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
        }

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                url,
                headers=headers,
                data=json.dumps(option),   # z. B.  "LESS"  (6 Bytes)
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    self._current_option = option
                    self.async_write_ha_state()
                    _LOGGER.info("Mowing frequency set: %s", option)
                else:
                    _LOGGER.error(
                        "Set mowing frequency failed: HTTP %s", resp.status
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set mowing frequency failed: %s", exc)


# ---------------------------------------------------------------------------
# Per-zone mowing pattern select
# ---------------------------------------------------------------------------

class ZoneMowingPatternSelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "zone_mowing_pattern"
    """Mowing pattern for a specific zone (RANDOM / LINES / SPIRAL).

    Reads:  system-coordinator ``zone_settings`` key (refreshed every 5 min).
    Writes: GET /settings/zones → modify mowingPattern → POST /settings/zones.
    """

    _attr_icon = "mdi:map-marker-path"
    should_poll = False

    def __init__(
        self,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
        zone_id: str,
        zone_name: str,
        initial_pattern: str = "RANDOM",
    ) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._skip_coordinator_until = 0.0
        self._current_option = (
            initial_pattern if initial_pattern in MOWING_PATTERN_OPTIONS else "RANDOM"
        )
        safe = zone_id.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"zone_mowing_pattern_{ip_address.replace('.', '_')}_{safe}"
        )
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
        self._attr_translation_placeholders = {"zone_name": zone_name}

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def options(self) -> list[str]:
        return MOWING_PATTERN_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    # ------------------------------------------------------------------
    # Coordinator listener
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        """Extract this zone's mowingPattern from the cached GeoJSON."""
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            if feature.get("id") != self._zone_id:          # id is at feature level
                continue
            props = feature.get("properties", {})
            pattern = (
                props.get("zoneProperties", {})
                .get("mowingPlanner", {})
                .get("mowingPattern")
            )
            if pattern and pattern in MOWING_PATTERN_OPTIONS:
                self._current_option = pattern
            break

    # ------------------------------------------------------------------
    # Write: GET → modify → PUT
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        """Set the mowing pattern for this zone on the mower."""
        if option not in MOWING_PATTERN_OPTIONS:
            _LOGGER.error("Invalid mowing pattern: %s", option)
            return

        url = f"http://{self._ip_address}:8080/settings/zones"
        json_headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }

        session = async_get_clientsession(self.hass)
        # 1. Read current full zone GeoJSON
        try:
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        "GET /settings/zones failed: HTTP %s", resp.status
                    )
                    return
                zone_data = await resp.json()
        except aiohttp.ClientError as exc:
            _LOGGER.error("GET /settings/zones failed: %s", exc)
            return

        # 2. Find and update this zone's mowingPattern
        modified = False
        for feature in zone_data.get("features", []):
            if feature.get("id") != self._zone_id:      # id is at feature level
                continue
            props = feature.get("properties", {})
            zone_props = props.setdefault("zoneProperties", {})
            planner = zone_props.setdefault("mowingPlanner", {})
            planner["mowingPattern"] = option
            modified = True
            break

        if not modified:
            _LOGGER.error(
                "Zone %s not found in /settings/zones response", self._zone_id
            )
            return

        # 3. Write back
        try:
            status = await _post_zones_urllib(url, zone_data)
            if status == 200:
                self._current_option = option
                self.async_write_ha_state()
                self._skip_coordinator_until = time.monotonic() + 15
                _LOGGER.info(
                    "Zone '%s' mowing pattern → %s",
                    self._zone_name,
                    option,
                )
                await self._system_coordinator.async_request_refresh()
            else:
                _LOGGER.error(
                    "POST /settings/zones failed: HTTP %s", status
                )
        except Exception as exc:
            _LOGGER.error("POST /settings/zones failed: %s", exc)


# ---------------------------------------------------------------------------
# Obstacle sensitivity (global — Hindernisempfindlichkeit)
# ---------------------------------------------------------------------------

class ObstacleSensitivitySelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "obstacle_sensitivity"
    """Global obstacle sensitivity setting.

    Modes (API value → German app label):
      CHICKEN_MODE  → Hühnermodus        (very sensitive, avoids all obstacles)
      CAUTIOUS_CAT  → Vorsichtige Katze  (moderate sensitivity)
      OFF_ROAD_REBEL→ Gelände-Rebell     (less sensitive, handles small obstacles)
      TANK_MODE     → Panzermodus        (not sensitive, charges through)

    GET  /settings/mowingObstacleSensitivity  → JSON string or null
    POST /settings/mowingObstacleSensitivity  → Body: JSON string, e.g. "OFF_ROAD_REBEL"
    """

    _attr_icon = "mdi:shield-alert-outline"
    _attr_options = OBSTACLE_SENSITIVITY_OPTIONS

    _ENDPOINT = "/settings/mowingObstacleSensitivity"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = "OFF_ROAD_REBEL"
        self._attr_unique_id = f"obstacle_sensitivity_{ip_address.replace('.', '_')}"
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
    def options(self) -> list[str]:
        return OBSTACLE_SENSITIVITY_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_update(self) -> None:
        """Read current obstacle sensitivity from the mower."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, str) and value in OBSTACLE_SENSITIVITY_OPTIONS:
                        self._current_option = value
                    # null means not set — keep default
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read obstacle sensitivity: %s", exc)

    async def async_select_option(self, option: str) -> None:
        """Set the obstacle sensitivity on the mower."""
        if option not in OBSTACLE_SENSITIVITY_OPTIONS:
            _LOGGER.error("Invalid obstacle sensitivity: %s", option)
            return

        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                url,
                headers=headers,
                data=json.dumps(option),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    self._current_option = option
                    self.async_write_ha_state()
                    _LOGGER.info("Obstacle sensitivity set to %s", option)
                else:
                    _LOGGER.error(
                        "Set obstacle sensitivity failed: HTTP %s", resp.status
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set obstacle sensitivity failed: %s", exc)


# ---------------------------------------------------------------------------
# Global mowing pattern select  (gilt für alle Zonen ohne eigene Einstellung)
# ---------------------------------------------------------------------------

class GlobalMowingPatternSelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "global_mowing_pattern"
    """Global default mowing pattern (RANDOM / LINES / SPIRAL).

    Ergänzt die per-Zone-Einstellung: wenn eine Zone kein eigenes Muster hat,
    wird dieses globale Muster verwendet.

    GET  /settings/mowingPlanner/mowingPattern  → JSON string
    POST /settings/mowingPlanner/mowingPattern  → Body: JSON string
    """

    _attr_icon = "mdi:map-marker-path"
    _attr_options = MOWING_PATTERN_OPTIONS

    _ENDPOINT = "/settings/mowingPlanner/mowingPattern"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = "RANDOM"
        self._attr_unique_id = f"global_mowing_pattern_{ip_address.replace('.', '_')}"
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
    def options(self) -> list[str]:
        return MOWING_PATTERN_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_update(self) -> None:
        """Read current global mowing pattern from the mower."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, str) and value in MOWING_PATTERN_OPTIONS:
                        self._current_option = value
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read global mowing pattern: %s", exc)

    async def async_select_option(self, option: str) -> None:
        """Set the global mowing pattern on the mower."""
        if option not in MOWING_PATTERN_OPTIONS:
            _LOGGER.error("Invalid mowing pattern: %s", option)
            return
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.post(
                url,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json",
                },
                data=json.dumps(option),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    self._current_option = option
                    self.async_write_ha_state()
                    _LOGGER.info("Global mowing pattern set to %s", option)
                else:
                    _LOGGER.error(
                        "Set global mowing pattern failed: HTTP %s", resp.status
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Set global mowing pattern failed: %s", exc)


# ---------------------------------------------------------------------------
# Per-zone mowing frequency select (NEW)
# ---------------------------------------------------------------------------

class ZoneMowingFrequencySelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "zone_mowing_frequency"
    """Mowing frequency for a specific zone (STOP / LESS / NORMAL / MORE / CONTINUOUS).

    Reads:  system-coordinator ``zone_settings`` key (refreshed every 5 min).
    Writes: GET /settings/zones → modify mowingFrequency → POST /settings/zones.
    """

    _attr_icon = "mdi:calendar-sync"
    should_poll = False

    def __init__(
        self,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
        zone_id: str,
        zone_name: str,
        initial_frequency: str = "NORMAL",
    ) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._skip_coordinator_until = 0.0
        self._current_option = (
            initial_frequency if initial_frequency in MOWING_FREQUENCY_OPTIONS else "NORMAL"
        )
        safe = zone_id.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"zone_mowing_frequency_{ip_address.replace('.', '_')}_{safe}"
        )
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
        self._attr_translation_placeholders = {"zone_name": zone_name}

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def options(self) -> list[str]:
        return MOWING_FREQUENCY_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    # ------------------------------------------------------------------
    # Coordinator listener
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        """Extract this zone's mowingFrequency from the cached GeoJSON."""
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            frequency = (
                props.get("zoneProperties", {})
                .get("mowingPlanner", {})
                .get("mowingFrequency")
            )
            if frequency and frequency in MOWING_FREQUENCY_OPTIONS:
                self._current_option = frequency
            break

    # ------------------------------------------------------------------
    # Write: GET → modify → PUT
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        """Set the mowing frequency for this zone on the mower."""
        if option not in MOWING_FREQUENCY_OPTIONS:
            _LOGGER.error("Invalid mowing frequency: %s", option)
            return

        url = f"http://{self._ip_address}:8080/settings/zones"
        json_headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }

        session = async_get_clientsession(self.hass)
        # 1. Read current full zone GeoJSON
        try:
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        "GET /settings/zones failed: HTTP %s", resp.status
                    )
                    return
                zone_data = await resp.json()
        except aiohttp.ClientError as exc:
            _LOGGER.error("GET /settings/zones failed: %s", exc)
            return

        # 2. Find and update this zone's mowingFrequency
        modified = False
        for feature in zone_data.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            zone_props = props.setdefault("zoneProperties", {})
            planner = zone_props.setdefault("mowingPlanner", {})
            planner["mowingFrequency"] = option
            modified = True
            break

        if not modified:
            _LOGGER.error(
                "Zone %s not found in /settings/zones response", self._zone_id
            )
            return

        # 3. Write back
        try:
            status = await _post_zones_urllib(url, zone_data)
            if status == 200:
                self._current_option = option
                self.async_write_ha_state()
                self._skip_coordinator_until = time.monotonic() + 15
                _LOGGER.info(
                    "Zone '%s' mowing frequency → %s",
                    self._zone_name,
                    option,
                )
                await self._system_coordinator.async_request_refresh()
            else:
                _LOGGER.error(
                    "POST /settings/zones failed: HTTP %s", status
                )
        except Exception as exc:
            _LOGGER.error("POST /settings/zones failed: %s", exc)


# ---------------------------------------------------------------------------
# Per-zone obstacle sensitivity select (NEW)
# ---------------------------------------------------------------------------

class ZoneObstacleSensitivitySelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "zone_obstacle_sensitivity"
    """Obstacle sensitivity for a specific zone (CHICKEN_MODE / CAUTIOUS_CAT / OFF_ROAD_REBEL / TANK_MODE).

    Reads:  system-coordinator ``zone_settings`` key (refreshed every 5 min).
    Writes: GET /settings/zones → modify obstacleSensitivity → POST /settings/zones.
    """

    _attr_icon = "mdi:shield-alert"
    should_poll = False

    def __init__(
        self,
        system_coordinator: EeveMowerSystemCoordinator,
        ip_address: str,
        zone_id: str,
        zone_name: str,
        initial_sensitivity: str = "OFF_ROAD_REBEL",
    ) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._skip_coordinator_until = 0.0
        self._current_option = (
            initial_sensitivity if initial_sensitivity in OBSTACLE_SENSITIVITY_OPTIONS else "OFF_ROAD_REBEL"
        )
        safe = zone_id.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"zone_obstacle_sensitivity_{ip_address.replace('.', '_')}_{safe}"
        )
        self._device_id = f"eeve_mower_{ip_address.replace('.', '_')}"
        self._attr_translation_placeholders = {"zone_name": zone_name}

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
        }

    @property
    def options(self) -> list[str]:
        return OBSTACLE_SENSITIVITY_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    # ------------------------------------------------------------------
    # Coordinator listener
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        """Extract this zone's obstacleSensitivity from the cached GeoJSON."""
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            sensitivity = (
                props.get("zoneProperties", {})
                .get("mowingPlanner", {})
                .get("obstacleSensitivity")
            )
            if sensitivity and sensitivity in OBSTACLE_SENSITIVITY_OPTIONS:
                self._current_option = sensitivity
            break

    # ------------------------------------------------------------------
    # Write: GET → modify → PUT
    # ------------------------------------------------------------------

    async def async_select_option(self, option: str) -> None:
        """Set the obstacle sensitivity for this zone on the mower."""
        if option not in OBSTACLE_SENSITIVITY_OPTIONS:
            _LOGGER.error("Invalid obstacle sensitivity: %s", option)
            return

        url = f"http://{self._ip_address}:8080/settings/zones"
        json_headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }

        session = async_get_clientsession(self.hass)
        # 1. Read current full zone GeoJSON
        try:
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        "GET /settings/zones failed: HTTP %s", resp.status
                    )
                    return
                zone_data = await resp.json()
        except aiohttp.ClientError as exc:
            _LOGGER.error("GET /settings/zones failed: %s", exc)
            return

        # 2. Find and update this zone's obstacleSensitivity
        modified = False
        for feature in zone_data.get("features", []):
            if feature.get("id") != self._zone_id:
                continue
            props = feature.get("properties", {})
            zone_props = props.setdefault("zoneProperties", {})
            planner = zone_props.setdefault("mowingPlanner", {})
            planner["obstacleSensitivity"] = option
            modified = True
            break

        if not modified:
            _LOGGER.error(
                "Zone %s not found in /settings/zones response", self._zone_id
            )
            return

        # 3. Write back
        try:
            status = await _post_zones_urllib(url, zone_data)
            if status == 200:
                self._current_option = option
                self.async_write_ha_state()
                self._skip_coordinator_until = time.monotonic() + 15
                _LOGGER.info(
                    "Zone '%s' obstacle sensitivity → %s",
                    self._zone_name,
                    option,
                )
                await self._system_coordinator.async_request_refresh()
            else:
                _LOGGER.error(
                    "POST /settings/zones failed: HTTP %s", status
                )
        except Exception as exc:
            _LOGGER.error("POST /settings/zones failed: %s", exc)


# ---------------------------------------------------------------------------
# Emotion select (write-only)
# ---------------------------------------------------------------------------

class EmotionSelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "show_emotion"
    """Triggers a named emotion/animation on the mower display.

    Write-only: PUT /api/maintenance/showEmotion?emotionName=<value>
    No state is read back; current_option reflects the last selection.
    """

    _attr_icon = "mdi:emoticon-happy"
    _attr_options = EMOTION_OPTIONS

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = EMOTION_OPTIONS[0]
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"show_emotion_{safe_ip}"
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
    def options(self) -> list[str]:
        return EMOTION_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_select_option(self, option: str) -> None:
        """Trigger the selected emotion on the mower."""
        if option not in EMOTION_OPTIONS:
            _LOGGER.error("Invalid emotion: %s", option)
            return

        url = f"http://{self._ip_address}:8080/api/maintenance/showEmotion"
        try:
            session = async_get_clientsession(self.hass)
            async with session.put(
                url,
                headers={"accept": "*/*"},
                params={"emotionName": option},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    self._current_option = option
                    self.async_write_ha_state()
                    _LOGGER.info("Show emotion: %s", option)
                else:
                    _LOGGER.error(
                        "Show emotion '%s' failed: HTTP %s", option, resp.status
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.error("Show emotion '%s' failed: %s", option, exc)


# ---------------------------------------------------------------------------
# Person scanning behaviour select
# ---------------------------------------------------------------------------

class PersonScanningBehaviourSelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "person_scanning_behaviour"
    """Sets the person scanning behaviour for auto-annotation.

    GET /settings/autoAnnotation/personScanningBehaviour  -> JSON string
    PUT /settings/autoAnnotation/personScanningBehaviour  -> Body: JSON string
    """

    _attr_icon = "mdi:account-search"
    _attr_options = PERSON_SCANNING_BEHAVIOUR_OPTIONS

    _ENDPOINT = "/settings/autoAnnotation/personScanningBehaviour"

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = "normal"
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"person_scanning_behaviour_{safe_ip}"
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
    def options(self) -> list[str]:
        return PERSON_SCANNING_BEHAVIOUR_OPTIONS

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_update(self) -> None:
        """Read the current person scanning behaviour from the mower."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, str) and value in PERSON_SCANNING_BEHAVIOUR_OPTIONS:
                        self._current_option = value
                    else:
                        _LOGGER.debug(
                            "Unknown personScanningBehaviour value: %s", value
                        )
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read personScanningBehaviour: %s", exc)

    async def async_select_option(self, option: str) -> None:
        """Set the person scanning behaviour on the mower."""
        if option not in PERSON_SCANNING_BEHAVIOUR_OPTIONS:
            _LOGGER.error("Invalid person scanning behaviour: %s", option)
            return

        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            payload = json.dumps(option).encode("utf-8")

            def _do_post():
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "accept": "application/json",
                        "Connection": "close",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status

            status = await asyncio.get_event_loop().run_in_executor(None, _do_post)
            if status == 200:
                self._current_option = option
                self.async_write_ha_state()
                _LOGGER.info("Person scanning behaviour set to %s", option)
            else:
                _LOGGER.error(
                    "Set personScanningBehaviour failed: HTTP %s", status
                )
        except Exception as exc:
            _LOGGER.error("Set personScanningBehaviour failed: %s", exc)


# ---------------------------------------------------------------------------
# Square meter per hour (mowing speed) select
# ---------------------------------------------------------------------------

class SquareMeterPerHourSelect(SelectEntity):

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "mowing_speed"
    """Sets the mowing speed in square metres per hour.

    Options mapping (display label -> API integer):
        "Auto"             -> -1
        "Slow (30 m²/h)"   -> 30
        "Normal (45 m²/h)" -> 45
        "Fast (90 m²/h)"   -> 90

    GET /settings/mowActivity/squareMeterPerHour  -> JSON integer
    PUT /settings/mowActivity/squareMeterPerHour  -> Body: JSON integer
    """

    _attr_icon = "mdi:speedometer"

    _ENDPOINT = "/settings/mowActivity/squareMeterPerHour"
    _VALUE_TO_LABEL: dict[int, str] = {v: k for k, v in SQUARE_METER_PER_HOUR_MAP.items()}

    def __init__(self, ip_address: str) -> None:
        self._ip_address = ip_address
        self._current_option: str = "Auto"
        safe_ip = ip_address.replace(".", "_")
        self._attr_unique_id = f"square_meter_per_hour_{safe_ip}"
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
    def options(self) -> list[str]:
        return list(SQUARE_METER_PER_HOUR_MAP.keys())

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_update(self) -> None:
        """Read the current mowing speed from the mower."""
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={"accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    value = await resp.json()
                    if isinstance(value, int) and value in self._VALUE_TO_LABEL:
                        self._current_option = self._VALUE_TO_LABEL[value]
                    else:
                        _LOGGER.debug(
                            "Unknown squareMeterPerHour value: %s", value
                        )
        except (aiohttp.ClientError, Exception) as exc:
            _LOGGER.debug("Could not read squareMeterPerHour: %s", exc)

    async def async_select_option(self, option: str) -> None:
        """Set the mowing speed on the mower."""
        if option not in SQUARE_METER_PER_HOUR_MAP:
            _LOGGER.error("Invalid mowing speed option: %s", option)
            return

        api_value = SQUARE_METER_PER_HOUR_MAP[option]
        url = f"http://{self._ip_address}:8080{self._ENDPOINT}"
        try:
            payload = json.dumps(api_value).encode("utf-8")

            def _do_post():
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "accept": "application/json",
                        "Connection": "close",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status

            status = await asyncio.get_event_loop().run_in_executor(None, _do_post)
            if status == 200:
                self._current_option = option
                self.async_write_ha_state()
                _LOGGER.info(
                    "Mowing speed set to %s (%s m²/h)", option, api_value
                )
            else:
                _LOGGER.error(
                    "Set squareMeterPerHour failed: HTTP %s", status
                )
        except Exception as exc:
            _LOGGER.error("Set squareMeterPerHour failed: %s", exc)


# ---------------------------------------------------------------------------
# All-zones aggregate selects (apply one value to every GRASSZONE at once)
# ---------------------------------------------------------------------------

class _AllZonesSelectBase(SelectEntity):
    """Base for selects that write one value to all GRASSZONEs."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    should_poll = False
    _OPTIONS: list[str] = []
    _PLANNER_KEY: str = ""

    def __init__(self, system_coordinator: EeveMowerSystemCoordinator, ip_address: str) -> None:
        self._system_coordinator = system_coordinator
        self._ip_address = ip_address
        self._skip_coordinator_until = 0.0
        self._current_option = self._OPTIONS[0]
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
    def options(self) -> list[str]:
        return list(self._OPTIONS)

    @property
    def current_option(self) -> str:
        return self._current_option

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._system_coordinator.async_add_listener(self._handle_coordinator_update)
        )
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        if time.monotonic() < self._skip_coordinator_until:
            return
        if self._system_coordinator.data:
            self._apply_coordinator_data(self._system_coordinator.data)
        self.async_write_ha_state()

    def _apply_coordinator_data(self, data: dict) -> None:
        zone_settings = data.get("zone_settings")
        if not isinstance(zone_settings, dict):
            return
        for feature in zone_settings.get("features", []):
            props = feature.get("properties", {})
            if props.get("zoneType") != "GRASSZONE":
                continue
            val = props.get("zoneProperties", {}).get("mowingPlanner", {}).get(self._PLANNER_KEY)
            if val in self._OPTIONS:
                self._current_option = val
            break

    async def async_select_option(self, option: str) -> None:
        if option not in self._OPTIONS:
            _LOGGER.error("Invalid option for %s: %s", self._PLANNER_KEY, option)
            return
        key = self._PLANNER_KEY
        def _apply(zp):
            zp.setdefault("mowingPlanner", {})[key] = option
        status = await _set_all_grass_zones(self.hass, self._ip_address, _apply)
        if status == 200:
            self._current_option = option
            self.async_write_ha_state()
            self._skip_coordinator_until = time.monotonic() + 15
            _LOGGER.info("All zones %s -> %s", key, option)
            await self._system_coordinator.async_request_refresh()
        else:
            _LOGGER.error("Set all-zones %s failed (status %s)", key, status)


class AllZonesMowingPatternSelect(_AllZonesSelectBase):
    _attr_translation_key = "all_zones_mowing_pattern"
    _attr_icon = "mdi:vector-line"
    _OPTIONS = MOWING_PATTERN_OPTIONS
    _PLANNER_KEY = "mowingPattern"

    def __init__(self, system_coordinator, ip_address):
        super().__init__(system_coordinator, ip_address)
        self._attr_unique_id = f"all_zones_mowing_pattern_{ip_address.replace('.', '_')}"


class AllZonesMowingFrequencySelect(_AllZonesSelectBase):
    _attr_translation_key = "all_zones_mowing_frequency"
    _attr_icon = "mdi:calendar-refresh"
    _OPTIONS = MOWING_FREQUENCY_OPTIONS
    _PLANNER_KEY = "mowingFrequency"

    def __init__(self, system_coordinator, ip_address):
        super().__init__(system_coordinator, ip_address)
        self._attr_unique_id = f"all_zones_mowing_frequency_{ip_address.replace('.', '_')}"


class AllZonesObstacleSensitivitySelect(_AllZonesSelectBase):
    _attr_translation_key = "all_zones_obstacle_sensitivity"
    _attr_icon = "mdi:motion-sensor"
    _OPTIONS = OBSTACLE_SENSITIVITY_OPTIONS
    _PLANNER_KEY = "obstacleSensitivity"

    def __init__(self, system_coordinator, ip_address):
        super().__init__(system_coordinator, ip_address)
        self._attr_unique_id = f"all_zones_obstacle_sensitivity_{ip_address.replace('.', '_')}"
