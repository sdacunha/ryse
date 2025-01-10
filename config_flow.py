from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

# Hardcoded values
HARDCODED_VALUES = {
    "address": "00:11:22:33:44:55",
    "rx_uuid": "your-hardcoded-rx-uuid",
    "tx_uuid": "your-hardcoded-tx-uuid",
}

class RyseBLEDeviceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RYSE BLE Device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            _LOGGER.debug("User input received (if any): %s", user_input)
            # Combine hardcoded values and any user input if needed
            return self.async_create_entry(
                title="RYSE BLE Device",
                data=HARDCODED_VALUES,
            )

        # If no input is required, simply show the form with a message
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),  # Empty schema (no user input needed)
            description_placeholders={"info": "Using hardcoded address and UUIDs."}
        )
