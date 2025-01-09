from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

# Define the schema for the user input
CONFIG_SCHEMA = vol.Schema({
    vol.Required("address"): str,
    vol.Required("rx_uuid"): str,
    vol.Required("tx_uuid"): str,
})


class RyseBLEDeviceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RYSE BLE Device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)
            # Perform basic validation
            if not user_input["address"] or not user_input["rx_uuid"] or not user_input["tx_uuid"]:
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title="RYSE BLE Device", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=CONFIG_SCHEMA,
            errors=errors
        )
