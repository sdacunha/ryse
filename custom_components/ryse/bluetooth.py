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
        self._battery_callbacks = []
        self._battery_level = None
        self._is_connected = False
        self._last_connection_attempt = None
        self._connection_lock = asyncio.Lock()
        self._connection_cooldown = 5  # seconds between connection attempts
        self._shutdown = False
        self._latest_battery = None
        self._latest_position = None

    async def pair(self) -> bool:
        """Pair with the device."""
        if self._shutdown:
            return False

        async with self._connection_lock:
            if self._is_connected and self.client and self.client.is_connected:
                return True

            try:
                _LOGGER.debug("Attempting to connect to device %s", self.address)
                
                # Register callback for device updates if not already registered
                if not self._callback:
                    self._callback = async_register_callback(
                        self.hass,
                        self._device_update,
                        BluetoothCallbackMatcher(address=self.address),
                        BluetoothScanningMode.PASSIVE,
                    )

                # Track device unavailability if not already tracking
                if not self._unavailable_tracker:
                    self._unavailable_tracker = async_track_unavailable(
                        self.hass,
                        self._device_unavailable,
                        self.address,
                    )
                
                # Try to get the device from the scanner first
                ble_device = async_ble_device_from_address(self.hass, self.address)
                if ble_device:
                    _LOGGER.debug("Device found: %s", ble_device)
                    self.client = BleakClient(
                        ble_device,
                        disconnected_callback=lambda client: asyncio.create_task(self._handle_disconnect(client))
                    )
                else:
                    _LOGGER.warning("Device not found, attempting direct connection")
                    self.client = BleakClient(
                        self.address,
                        disconnected_callback=lambda client: asyncio.create_task(self._handle_disconnect(client))
                    )

                await self.client.connect(timeout=30.0)
                if not self.client.is_connected:
                    raise BleakError("Failed to connect to device")

                _LOGGER.debug("Connected to device %s", self.address)
                self._is_connected = True
                return True

            except Exception as e:
                _LOGGER.error("Error connecting to device %s: %s", self.address, e)
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
        
        if not self._shutdown:
            try:
                await asyncio.sleep(self._connection_cooldown)
                if not self._shutdown:
                    _LOGGER.debug("Attempting to reconnect to device %s", self.address)
                    await self.pair()
            except Exception as e:
                _LOGGER.error("Failed to reconnect to device %s: %s", self.address, e)

    def _device_update(self, service_info: BluetoothServiceInfo, change: BluetoothChange) -> None:
        """Handle device updates from the Bluetooth proxy."""
        if self._shutdown:
            return

        if change == BluetoothChange.ADVERTISEMENT:
            _LOGGER.debug("[ADV] Advertisement received: %s", service_info)
            # Extract data from manufacturer data
            for mfr_id, data in service_info.manufacturer_data.items():
                _LOGGER.debug("[ADV] Manufacturer ID: 0x%04x, Data: %s", mfr_id, data.hex() if data else None)
                if len(data) >= 3:
                    battery = data[2]
                    self._latest_battery = battery
                    _LOGGER.debug("[ADV] Battery percentage from advertisement: %d%%", battery)
                    self._battery_level = battery
                    for cb in self._battery_callbacks:
                        asyncio.create_task(cb(battery))
                if len(data) >= 2:
                    position = data[1]
                    self._latest_position = position
                    _LOGGER.debug("[ADV] Position from advertisement: %d%%", position)
                    if hasattr(self, "update_callback") and self.update_callback:
                        asyncio.create_task(self.update_callback(position))

    def _device_unavailable(self, service_info: BluetoothServiceInfo) -> None:
        """Handle device becoming unavailable."""
        if self._shutdown:
            return

        _LOGGER.debug(f"Device {self.address} became unavailable")
        if self.client and self.client.is_connected:
            asyncio.create_task(self.unpair())

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
        
        if self._callback:
            self._callback()
            self._callback = None
        if self._unavailable_tracker:
            self._unavailable_tracker()
            self._unavailable_tracker = None

    async def write_data(self, data):
        """Write data to the device."""
        if self._shutdown:
            return

        if not self._is_connected or not self.client or not self.client.is_connected:
            if not await self.pair():
                _LOGGER.error("Failed to connect to device for write operation")
                return

        try:
            await self.client.write_gatt_char(self.tx_uuid, data)
            _LOGGER.debug(f"Sending data to tx uuid")
        except Exception as e:
            _LOGGER.error(f"Error writing data: {e}")
            self._is_connected = False

    def add_battery_callback(self, callback):
        """Add a callback for battery updates."""
        _LOGGER.debug("[RyseBLEDevice] Adding battery callback: %s (device id: %s)", callback, id(self))
        self._battery_callbacks.append(callback)

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