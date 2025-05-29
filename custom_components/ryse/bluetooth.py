import asyncio
import logging
from datetime import datetime, timedelta
from homeassistant.components.bluetooth import (
    async_register_callback,
    async_track_unavailable,
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothServiceInfo,
    async_get_scanner,
    async_ble_device_from_address,
    BluetoothScanningMode,
    async_get_bluetooth,
)
from bleak import BleakClient, BleakError

_LOGGER = logging.getLogger(__name__)

class RyseBLEDevice:
    def __init__(self, hass, address=None, rx_uuid=None, tx_uuid=None):
        self.hass = hass
        self.address = address
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.client = None
        self._unavailable_tracker = None
        self._callback = None
        self._battery_callback = None
        self._battery_level = None
        # RYSE battery service UUID (this is a placeholder - we need to find the correct one)
        self.battery_uuid = None  # We'll discover this during connection
        self._battery_update_interval = 3600  # Default to 1 hour
        self._is_connected = False
        self._last_connection_attempt = None
        self._connection_lock = asyncio.Lock()
        self._connection_cooldown = 5  # seconds between connection attempts
        self._shutdown = False

    async def pair(self) -> bool:
        """Pair with the device."""
        if self._shutdown:
            return False

        async with self._connection_lock:
            # Check if we're in cooldown period
            if self._last_connection_attempt:
                time_since_last = (datetime.now() - self._last_connection_attempt).total_seconds()
                if time_since_last < self._connection_cooldown:
                    _LOGGER.debug("Connection attempt throttled, waiting %d seconds", 
                                self._connection_cooldown - time_since_last)
                    return False

            self._last_connection_attempt = datetime.now()

            try:
                _LOGGER.debug("Attempting to connect to device %s", self.address)
                
                # Get the Bluetooth scanner
                scanner = async_get_scanner(self.hass)
                if not scanner:
                    raise BleakError("No Bluetooth scanner found")

                # Register callback for device updates
                if not self._callback:
                    self._callback = async_register_callback(
                        self.hass,
                        self._device_update,
                        BluetoothCallbackMatcher(address=self.address),
                        BluetoothScanningMode.PASSIVE,
                    )

                # Track device unavailability
                if not self._unavailable_tracker:
                    self._unavailable_tracker = async_track_unavailable(
                        self.hass,
                        self._device_unavailable,
                        self.address,
                    )

                # Wait for device discovery
                _LOGGER.debug("Waiting for device discovery...")
                ble_device = None
                for _ in range(10):  # Try for 10 seconds
                    if self._shutdown:
                        return False
                    ble_device = async_ble_device_from_address(self.hass, self.address)
                    if ble_device:
                        _LOGGER.debug("Device found: %s", ble_device)
                        break
                    await asyncio.sleep(1)

                if ble_device:
                    # Create a BleakClient instance with discovered device
                    self.client = BleakClient(
                        ble_device,
                        disconnected_callback=lambda client: asyncio.create_task(self._handle_disconnect(client))
                    )
                else:
                    _LOGGER.warning("Device not found after waiting, attempting direct connection")
                    # Try direct connection as fallback
                    self.client = BleakClient(
                        self.address,
                        disconnected_callback=lambda client: asyncio.create_task(self._handle_disconnect(client))
                    )

                # Connect with a longer timeout
                _LOGGER.debug("Attempting to connect...")
                await self.client.connect(timeout=30.0)
                if not self.client.is_connected:
                    raise BleakError("Failed to connect to device")

                _LOGGER.debug("Connected to device %s", self.address)
                self._is_connected = True

                # Discover services and characteristics
                _LOGGER.debug("Discovering services and characteristics...")
                for service in self.client.services:
                    _LOGGER.debug("Service: %s", service.uuid)
                    for char in service.characteristics:
                        _LOGGER.debug("  Characteristic: %s", char.uuid)
                        _LOGGER.debug("    Properties: %s", char.properties)
                        
                        # Look for battery service and characteristic
                        if service.uuid == "0000180f-0000-1000-8000-00805f9b34fb":  # Battery Service UUID
                            _LOGGER.debug("Found battery service")
                            if char.uuid == "00002a19-0000-1000-8000-00805f9b34fb":  # Battery Level Characteristic UUID
                                _LOGGER.debug("Found battery level characteristic")
                                self.battery_uuid = char.uuid
                                try:
                                    value = await self.client.read_gatt_char(char.uuid)
                                    battery_level = int.from_bytes(value, byteorder='little')
                                    _LOGGER.debug("Initial battery level: %d%%", battery_level)
                                    self._battery_level = battery_level
                                    if self._battery_callback:
                                        asyncio.create_task(self._battery_callback(battery_level))
                                except Exception as e:
                                    _LOGGER.error("Failed to read initial battery level: %s", e)
                        
                        # Try to read other readable characteristics
                        elif "read" in char.properties:
                            try:
                                value = await self.client.read_gatt_char(char.uuid)
                                _LOGGER.debug("    Value: %s", value.hex() if value else None)
                            except Exception as e:
                                _LOGGER.debug("    Failed to read value: %s", e)

                return True

            except Exception as e:
                _LOGGER.error("Error connecting to device %s: %s", self.address, e, exc_info=True)
                if self.client and self.client.is_connected:
                    await self.client.disconnect()
                self._is_connected = False
                return False

    async def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle device disconnection."""
        if self._shutdown:
            return

        _LOGGER.debug("Device %s disconnected", self.address)
        self._is_connected = False
        
        # Create a task for reconnection to avoid blocking
        if not self._shutdown:
            try:
                # Add a small delay before reconnection attempt
                await asyncio.sleep(self._connection_cooldown)
                if not self._shutdown:
                    _LOGGER.debug("Attempting to reconnect to device %s", self.address)
                    await self.pair()
            except Exception as e:
                _LOGGER.error("Failed to reconnect to device %s: %s", self.address, e)

    async def _ensure_connected(self) -> bool:
        """Ensure we have an active connection to the device."""
        if self._shutdown:
            return False

        if not self._is_connected or not self.client or not self.client.is_connected:
            return await self.pair()
        return True

    def _device_update(self, service_info: BluetoothServiceInfo, change: BluetoothChange) -> None:
        """Handle device updates from the Bluetooth proxy."""
        if self._shutdown:
            return

        if change == BluetoothChange.ADVERTISEMENT:
            _LOGGER.debug("[ADV] Advertisement received: %s", service_info)
            # Log all manufacturer data
            for mfr_id, data in service_info.manufacturer_data.items():
                _LOGGER.debug("[ADV] Manufacturer ID: 0x%04x, Data: %s", mfr_id, data.hex() if data else None)
                # Extract battery percentage from third byte if available
                if len(data) >= 3:
                    battery = data[2]
                    _LOGGER.debug("[ADV] Battery percentage from advertisement: %d%%", battery)
                    self._battery_level = battery
                    if self._battery_callback:
                        asyncio.create_task(self._battery_callback(battery))
                if len(data) >= 2:
                    position = data[1]
                    _LOGGER.debug("[ADV] Position from advertisement: %d%%", position)
                    self._position = position
                    if hasattr(self, "update_callback") and self.update_callback:
                        asyncio.create_task(self.update_callback(position))
                else:
                    _LOGGER.warning("[ADV] Manufacturer data too short to extract battery: %s", data.hex())
            
            # Check manufacturer data for RYSE device
            manufacturer_data = service_info.manufacturer_data
            _LOGGER.debug("Manufacturer data: %s", manufacturer_data)
            
            # Try both 0x0409 and 0x409 (they might be represented differently)
            raw_data = manufacturer_data.get(0x0409) or manufacturer_data.get(0x409)
            
            if raw_data is not None:
                _LOGGER.debug("Found RYSE manufacturer data: %s", raw_data.hex())
                
                # Check if device is in pairing mode (0x40 flag)
                if len(raw_data) > 0:
                    _LOGGER.debug("First byte of manufacturer data: %02x", raw_data[0])
                    if raw_data[0] & 0x40:
                        _LOGGER.debug("Device is in pairing mode")
                        # Try to connect when device is in pairing mode
                        asyncio.create_task(self.pair())
                    
                # Handle RYSE data packets
                if len(raw_data) >= 5 and raw_data[0] == 0xF5:
                    _LOGGER.debug("Received RYSE data packet: %s", raw_data.hex())
                    
                    # Handle position data (similar to notification handler)
                    if raw_data[2] == 0x01 and raw_data[3] == 0x07:
                        new_position = raw_data[4]  # Extract the position byte
                        _LOGGER.debug("Received position data in advertisement: %s", new_position)
                        
                        # Notify cover.py about the position update
                        if hasattr(self, "update_callback"):
                            asyncio.create_task(self.update_callback(new_position))

    def _device_unavailable(self, service_info: BluetoothServiceInfo) -> None:
        """Handle device becoming unavailable."""
        if self._shutdown:
            return

        _LOGGER.debug(f"Device {self.address} became unavailable")
        if self.client and self.client.is_connected:
            asyncio.create_task(self.unpair())

    async def _notification_handler(self, sender, data):
        """Callback function for handling received BLE notifications."""
        if self._shutdown:
            return

        _LOGGER.debug(f"Received notification: {data.hex()} | bytes: {list(data)}")
        if len(data) >= 5 and data[0] == 0xF5 and data[2] == 0x01 and data[3] == 0x18:
            #ignore REPORT USER TARGET data
            return
        _LOGGER.debug(f"Received notification")
        if len(data) >= 5 and data[0] == 0xF5 and data[2] == 0x01 and data[3] == 0x07:
            new_position = data[4]  # Extract the position byte
            _LOGGER.debug(f"Received valid notification, updating position: {new_position}")

            # Notify cover.py about the position update
            if hasattr(self, "update_callback"):
                await self.update_callback(new_position)

    async def get_device_info(self):
        if self._shutdown:
            return None

        if self.client:
            try:
                manufacturer_data = self.client.services
                _LOGGER.debug(f"Getting Manufacturer Data")
                return manufacturer_data
            except Exception as e:
                _LOGGER.error(f"Failed to get device info: {e}")
        return None

    async def unpair(self):
        """Unpair from the device and clean up resources."""
        self._shutdown = True
        
        if self.client:
            try:
                await self.client.disconnect()
                _LOGGER.debug("Device disconnected")
            except Exception as e:
                _LOGGER.error("Error disconnecting device: %s", e)
            self.client = None
        
        # Clean up Bluetooth tracking
        if self._callback:
            self._callback()
            self._callback = None
        if self._unavailable_tracker:
            self._unavailable_tracker()
            self._unavailable_tracker = None

    async def read_data(self):
        if self._shutdown:
            return None

        if self.client:
            data = await self.client.read_gatt_char(self.rx_uuid)
            if len(data) < 5 or data[0] != 0xF5 or data[2] != 0x01 or data[3] != 0x18:
                #ignore REPORT USER TARGET data
                _LOGGER.debug(f"Received Position Report Data")
                return data
            return None

    async def write_data(self, data):
        if self._shutdown:
            return

        if self.client:
            await self.client.write_gatt_char(self.tx_uuid, data)
            _LOGGER.debug(f"Sending data to tx uuid")

    async def scan_and_pair(self):
        if self._shutdown:
            return False

        _LOGGER.debug("Scanning for BLE devices...")
        scanner = async_get_scanner(self.hass)
        if not scanner:
            _LOGGER.error("No Bluetooth scanner found")
            return False

        devices = await scanner.discover()
        for device in devices:
            _LOGGER.debug(f"Found device: {device.name} ({device.address})")
            if device.name and "target-device-name" in device.name.lower():
                _LOGGER.debug(f"Attempting to pair with {device.name} ({device.address})")
                self.address = device.address
                return await self.pair()
        _LOGGER.warning("No suitable devices found to pair")
        return False

    async def get_battery_level(self):
        """Read the battery level from the device (deprecated, now uses advertisements only)."""
        _LOGGER.debug("get_battery_level called, but battery is now only updated from advertisements.")
        return self._battery_level

    async def start_battery_monitoring(self, callback, update_interval=3600):
        """Start monitoring battery level (deprecated, now uses advertisements only)."""
        _LOGGER.debug("start_battery_monitoring called, but battery is now only updated from advertisements.")
        self._battery_callback = callback
        # Immediately call back with the current value if available
        if self._battery_level is not None:
            await self._battery_callback(self._battery_level)