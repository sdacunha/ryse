from homeassistant import config_entries
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

# Hardcoded UUIDs
HARDCODED_UUIDS = {
    "rx_uuid": "a72f2802-b0bd-498b-b4cd-4a3901388238",
    "tx_uuid": "a72f2801-b0bd-498b-b4cd-4a3901388238",
}

class RyseBLEDeviceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RYSE BLE Device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            _LOGGER.debug("User input received (if any): %s", user_input)
            # Use hardcoded UUIDs (address will be determined during pairing)
            return self.async_create_entry(
                title="RYSE BLE Device",
                data=HARDCODED_UUIDS,
            )

        # Show form with informational message
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),  # Empty schema since no input is needed
            description_placeholders={
                "info": "This integration will scan for BLE devices and pair automatically. UUIDs for RX/TX are predefined."
            },
        )
