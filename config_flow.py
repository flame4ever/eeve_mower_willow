import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries

from .const import DOMAIN  # Stellen Sie sicher, dass Sie die richtige Domain verwenden

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Ihre Integration."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step when the user configures the integration."""
        if user_input is not None:
            # Validate and store the configuration options
            CONF_MOWER_NAME = user_input["CONF_MOWER_NAME"]
            CONF_IP_ADDRESS = user_input["CONF_IP_ADDRESS"]

            # Save the configuration data
            return self.async_create_entry(
                title=CONF_MOWER_NAME,
                data={"CONF_IP_ADDRESS": CONF_IP_ADDRESS},
            )

        # Show the user a form to input their configuration options
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("CONF_MOWER_NAME", description={"suggested_value": "My Mower Name"}): cv.string,
                    vol.Required("CONF_IP_ADDRESS", description={"suggested_value": "My Mower IP e.g. 192.168.1.23"}): cv.string,
                }
            ),
        )

