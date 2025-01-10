from homeassistant import config_entries
import voluptuous as vol
import logging
from bleak import BleakScanner

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
            return self.async_create_entry(
                title=f"RYSE BLE Device {user_input['device_name']}",
                data={
                    "address": user_input["device_address"],
                    **HARDCODED_UUIDS,
                },
            )

        # Scan for BLE devices
        devices = await BleakScanner.discover()
        device_options = {
            device.address: f"{device.name} ({device.address})"
            for device in devices if device.name
        }

        if not device_options:
            return self.async_abort(reason="no_devices_found")

        _LOGGER.info("Devices found: %s", device_options)

        # Show device selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(device_options),
                }
            ),
            description_placeholders={"info": "Select a BLE device to pair."},
        )
