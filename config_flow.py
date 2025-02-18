from homeassistant import config_entries
import voluptuous as vol
import logging
from bleak import BleakScanner, BleakClient

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"
PAIRING_MODE_FLAG = 0x01  # LE Limited Discoverable Mode (standard pairing mode)

# Hardcoded UUIDs
HARDCODED_UUIDS = {
    "rx_uuid": "a72f2801-b0bd-498b-b4cd-4a3901388238",
    "tx_uuid": "a72f2802-b0bd-498b-b4cd-4a3901388238",
}

class RyseBLEDeviceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RYSE BLE Device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return await self.async_step_scan()

        # Show confirmation popup
        return self.async_show_form(
            step_id="user",
            description_placeholders={"info": "Press OK to start scanning for RYSE BLE devices."},
            data_schema=vol.Schema({}),  # Empty schema means no input field
            last_step=False,
        )

    async def async_step_scan(self, user_input=None):
        """Handle the BLE device scanning step."""
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
                    title=f"RYSE gear {device_name}",
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

        # Debug: Log all discovered devices
        for device in devices:
            _LOGGER.debug("(2) Device Name: %s - Device Address: %s - Advertisement Data: %s", device.name, device.address, device.details)

        self.device_options = {}

        for device in devices:
            if not device.name:
                continue  # Ignore unnamed devices

            advertisement_data = device.details
            # Access ManufacturerData from the nested props dictionary
            props = advertisement_data.get("props", {})
            manufacturer_data = props.get("ManufacturerData", {})

            # Check for manufacturer ID 0x0409 (1033 in decimal)
            if 1033 in manufacturer_data:
                raw_data = manufacturer_data[1033]  # Extract the bytearray for manufacturer ID 1033
                _LOGGER.debug("Device Name: %s - Device Address: %s - raw_data: %s", device.name, device.address, raw_data.hex())

                # Check if the pairing mode flag (0x40) is in the first byte
                if len(raw_data) > 0 and (raw_data[0] & 0x40):
                    self.device_options[device.address] = f"{device.name} ({device.address})"

        if not self.device_options:
            _LOGGER.warning("No BLE devices found in pairing mode (0x40).")
            return self.async_abort(reason="no_devices_found")

        _LOGGER.info("Filtered devices found: %s", self.device_options)

        # Show device selection form
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(self.device_options),
                }
            ),
            description_placeholders={"info": "Select a RYSE BLE device to pair."}
        )