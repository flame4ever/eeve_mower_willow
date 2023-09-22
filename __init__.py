"""The EEVE Mower Willow integration."""
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN  # Stellen Sie sicher, dass Sie die richtige Domain verwenden

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration using YAML configuration."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration using config entry."""
    CONF_IP_ADDRESS = entry.data["CONF_IP_ADDRESS"]
    CONF_MOWER_NAME = entry.title

    # Jetzt können Sie CONF_IP_ADDRESS und CONF_MOWER_NAME in Ihrer Integration verwenden
    # Zum Beispiel, um Schalter-Entitäten, Sensoren oder andere Integrationen zu erstellen

    # Rückgabe von True, um eine erfolgreiche Einrichtung anzuzeigen
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Cleanup when an entry is removed."""
    # Führen Sie alle notwendigen Aufräumarbeiten durch, wenn ein Konfigurationseintrag entfernt wird
    # Rückgabe von True, um eine erfolgreiche Entfernung anzuzeigen
    return True
