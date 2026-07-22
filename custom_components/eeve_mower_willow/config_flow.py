import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, CONF_MOWER_NAME, CONF_IP_ADDRESS

class EeveMowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EEVE Mower Willow."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_MOWER_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_MOWER_NAME, default="Wall-E"): cv.string,
                vol.Required(CONF_IP_ADDRESS, default="192.168.1.23"): cv.string,
            }),
        )
