from homeassistant import config_entries
import voluptuous as vol
import logging
from bleak import BleakScanner, BleakClient

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
            device_address = user_input["device_address"]

            try:
                _LOGGER.debug("Attempting to pair with BLE device: %s (%s)", device_name, device_address)
                async with BleakClient(device_address) as client:
                    paired = await client.pair()
                    if not paired:
                        _LOGGER.error("Failed to pair with BLE device: %s (%s)", device_name, device_address)
                        return self.async_abort(reason="pairing_failed")

                _LOGGER.info("Successfully paired with BLE device: %s (%s)", device_name, device_address)

                # Create entry after successful pairing
                return self.async_create_entry(
                    title=f"RYSE BLE Device {device_name}",
                    data={
                        "address": device_address,
                        **HARDCODED_UUIDS,
                    },
                )

            except Exception as e:
                _LOGGER.error("Error during pairing process for BLE device: %s (%s): %s", device_name, device_address, e)
                return self.async_abort(reason="pairing_failed")

        # Scan for BLE devices
        devices = await BleakScanner.discover()
        self.device_options = {
            device.address: f"{device.name} ({device.address})"
            for device in devices
            if device.name and 0x0409 in device.metadata.get("manufacturer_data", {})
        }

        if not self.device_options:
            _LOGGER.warning("No BLE devices found with company identifier 0x0409.")
            return self.async_abort(reason="no_devices_found")

        _LOGGER.info("Filtered devices found: %s", self.device_options)

        # Show device selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(self.device_options),
                }
            ),
            description_placeholders={"info": "Select a RYSE BLE device to pair."},
        )
