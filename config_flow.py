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
            # Extract device name and address from the selected option
            selected_device = next(
                (name for addr, name in self.device_options.items() if addr == user_input["device_address"]),
                None,
            )
            if not selected_device:
                return self.async_abort(reason="invalid_device_selected")
            
            device_name = selected_device.split(" (")[0]  # Extract device name before "("

            return self.async_create_entry(
                title=f"RYSE BLE Device {device_name}",
                data={
                    "address": user_input["device_address"],
                    **HARDCODED_UUIDS,
                },
            )

        # Scan for BLE devices
        devices = await BleakScanner.discover()
        self.device_options = {
            device.address: f"{device.name} ({device.address})"
            for device in devices if device.name
        }

        if not self.device_options:
            return self.async_abort(reason="no_devices_found")

        _LOGGER.info("Devices found: %s", self.device_options)

        # Show device selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(self.device_options),
                }
            ),
            description_placeholders={"info": "Select a BLE device to pair."},
        )
