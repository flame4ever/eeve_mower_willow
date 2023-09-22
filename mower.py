import requests
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from .const import DOMAIN  # Fügen Sie CONF_IP_ADDRESS hinzu

SERVICE_START_MOWING = "start_mowing"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IP_ADDRESS): cv.string,
    }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    ip_address = config[CONF_IP_ADDRESS]
    add_entities([MowerControlSwitch(ip_address)])

class MowerControlSwitch(SwitchEntity):
    def __init__(self, ip_address):
        self._ip_address = ip_address
        self._state = False

    @property
    def name(self):
        return "Mower Control"

    @property
    def is_on(self):
        return self._state

    def turn_on(self, **kwargs):
        # Send the HTTP request to start mowing
        url = f"http://{self._ip_address}:8080/api/navigation/startmowing?maxMowingTime=0"
        headers = {"accept": "*/*"}
        response = requests.put(url, headers=headers)
        
        if response.status_code == 200:
            self._state = True

    def turn_off(self, **kwargs):
        # Send the HTTP request to start mowing
        url = f"http://{self._ip_address}:8080/api/navigation/startdocking"
        headers = {"accept": "*/*"}
        response = requests.put(url, headers=headers)
        if response.status_code == 200:
            self._state = False  # Setzen Sie den Zustand auf False, wenn das Ausschalten erfolgreich ist

    def update(self):
        # Sie können hier Code hinzufügen, um den Zustand bei Bedarf zu aktualisieren
        pass
