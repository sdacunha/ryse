from homeassistant import config_entries
import voluptuous as vol
import logging
import asyncio
from homeassistant.components.bluetooth import (
    async_get_scanner,
    async_ble_device_from_address,
    BluetoothServiceInfo,
    async_register_callback,
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    async_get_bluetooth,
)
from bleak import BleakClient

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

    def _update_form(self) -> None:
        """Update the form with current device options."""
        self.hass.async_create_task(
            self.async_set_unique_id(next(iter(self.device_options.keys())))
        )
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(self.device_options),
                }
            ),
            description_placeholders={"info": "Press the PAIR button on your RYSE device and wait for it to appear in the list. Make sure your device is in pairing mode."}
        )

    async def async_step_scan(self, user_input=None):
        """Handle the BLE device scanning step."""
        if user_input is not None:
            # Clean up the callback before proceeding
            if hasattr(self, '_callback') and self._callback:
                self._callback()
                self._callback = None

            # Extract device name and address from the selected option
            selected_device = next(
                (name for addr, name in self.device_options.items() if addr == user_input["device_address"]),
                None,
            )
            if not selected_device:
                return self.async_abort(reason="Invalid selected device!")
            
            device_name = selected_device.split(" (")[0]  # Extract device name before "("
            device_address = user_input["device_address"]

            try:
                _LOGGER.debug("Starting pairing process for device: %s (%s)", device_name, device_address)

                # Get the Bluetooth scanner
                scanner = async_get_scanner(self.hass)
                _LOGGER.debug("Scanner type: %s", type(scanner))
                if not scanner:
                    _LOGGER.error("No Bluetooth scanner found")
                    return self.async_abort(reason="No Bluetooth scanner found")

                # Get the BLE device
                _LOGGER.debug("Attempting to get BLE device for address: %s", device_address)
                ble_device = async_ble_device_from_address(self.hass, device_address)
                _LOGGER.debug("BLE device type: %s", type(ble_device))
                if not ble_device:
                    _LOGGER.error(f"Could not find BLE device with address {device_address}")
                    return self.async_abort(reason="Device not found")

                # Create a BleakClient instance
                _LOGGER.debug("Creating BleakClient for device: %s", device_address)
                client = BleakClient(ble_device)
                
                max_retries = 3
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        _LOGGER.debug("Attempting to connect (attempt %d/%d)", retry_count + 1, max_retries)
                        await client.connect()
                        if client.is_connected:
                            _LOGGER.debug(f"Connected to {device_address}")

                            # Log all services and characteristics
                            _LOGGER.debug("Discovering services and characteristics...")
                            for service in client.services:
                                _LOGGER.debug("Service: %s", service.uuid)
                                for char in service.characteristics:
                                    _LOGGER.debug("  Characteristic: %s", char.uuid)
                                    _LOGGER.debug("    Properties: %s", char.properties)
                                    if "read" in char.properties:
                                        try:
                                            value = await client.read_gatt_char(char.uuid)
                                            _LOGGER.debug("    Value: %s", value.hex() if value else None)
                                        except Exception as e:
                                            _LOGGER.debug("    Failed to read value: %s", e)

                            # Pairing (Only required if your device needs pairing)
                            try:
                                _LOGGER.debug("Attempting to pair with device")
                                paired = await client.pair()
                                _LOGGER.debug("Pair result: %s", paired)
                                if not paired:
                                    _LOGGER.error("Failed to pair with BLE device: %s (%s)", device_name, device_address)
                                    return self.async_abort(reason="Pairing failed!")
                                else:
                                    _LOGGER.debug("Paired successfully")
                                    break  # Exit the retry loop on success
                            except NotImplementedError as e:
                                _LOGGER.warning("Pairing not supported on this platform: %s", e)
                                # Skip pairing and proceed with connection
                                break
                            except Exception as e:
                                _LOGGER.warning(f"Pairing failed: {e}", exc_info=True)
                        else:
                            _LOGGER.error("Failed to connect")
                            return self.async_abort(reason="Connection failed")
                    except Exception as e:
                        _LOGGER.error(f"Connection error (attempt {retry_count + 1}): {e}", exc_info=True)
                        retry_count += 1
                        if retry_count >= max_retries:
                            return self.async_abort(reason="Connection failed after retries")
                        await asyncio.sleep(3)  # Wait before retrying

                _LOGGER.debug("Disconnecting from device")
                await client.disconnect()
                _LOGGER.debug("Successfully paired with BLE device: %s (%s)", device_name, device_address)

                # Create entry after successful pairing
                return self.async_create_entry(
                    title=f"RYSE gear {device_name}",
                    data={
                        "address": device_address,
                        **HARDCODED_UUIDS,
                    },
                )

            except Exception as e:
                _LOGGER.error("Error during pairing process for BLE device: %s (%s): %s", device_name, device_address, e, exc_info=True)
                return self.async_abort(reason="Pairing failed!")

        # Get the Bluetooth scanner
        scanner = async_get_scanner(self.hass)
        if not scanner:
            _LOGGER.error("No Bluetooth scanner found")
            return self.async_abort(reason="No Bluetooth scanner found")

        # Get existing entries to exclude already configured devices
        existing_entries = self._async_current_entries()
        existing_addresses = {entry.data["address"] for entry in existing_entries}

        self.device_options = {}

        # Register callback for device updates
        def device_update(service_info: BluetoothServiceInfo, change: BluetoothChange) -> None:
            """Handle device updates from the Bluetooth proxy."""
            if change == BluetoothChange.ADVERTISEMENT:
                device_name = str(service_info.name) if service_info.name else ""
                device_address = service_info.address

                _LOGGER.debug("Discovered device: %s (%s)", device_name, device_address)
                _LOGGER.debug("Manufacturer data: %s", service_info.manufacturer_data)

                if not device_name or device_address in existing_addresses:
                    return

                # Get manufacturer data from the device
                manufacturer_data = service_info.manufacturer_data
                
                # Log all manufacturer data IDs for debugging
                for mfr_id, data in manufacturer_data.items():
                    _LOGGER.debug("Manufacturer ID: 0x%04x, Data: %s", mfr_id, data.hex() if data else None)
                
                # Try both 0x0409 and 0x409 (they might be represented differently)
                raw_data = manufacturer_data.get(0x0409) or manufacturer_data.get(0x409)
                
                if raw_data is not None:
                    _LOGGER.debug("Found device with RYSE manufacturer data: %s - raw data: %s", 
                                 device_name, raw_data.hex() if raw_data else None)
                    
                    # Check if device is in pairing mode (0x40 flag)
                    if len(raw_data) > 0:
                        _LOGGER.debug("First byte of manufacturer data: %02x", raw_data[0])
                        if raw_data[0] & 0x40:
                            _LOGGER.debug("Device is in pairing mode: %s (%s)", device_name, device_address)
                            self.device_options[device_address] = f"{device_name} ({device_address})"
                            # Schedule form update in the event loop
                            self.hass.loop.call_soon_threadsafe(
                                lambda: self._update_form()
                            )

        # Register the callback with the Bluetooth manager
        self._callback = async_register_callback(
            self.hass,
            device_update,
            BluetoothCallbackMatcher(),
            BluetoothScanningMode.ACTIVE,
        )

        # Start scanning
        _LOGGER.debug("Starting continuous scan for RYSE devices in pairing mode...")
        
        # Show the form with current devices (will be updated by the callback)
        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required("device_address"): vol.In(self.device_options),
                }
            ),
            description_placeholders={"info": "Press the PAIR button on your RYSE device and wait for it to appear in the list. Make sure your device is in pairing mode."}
        )

    async def async_step_abort(self, user_input=None):
        """Handle aborting the config flow."""
        if hasattr(self, '_callback') and self._callback:
            self._callback()
            self._callback = None
        return await super().async_step_abort(user_input)