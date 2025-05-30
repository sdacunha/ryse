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
)
from bleak import BleakClient, BleakError
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

class RyseBLEDevice:
    def __init__(self, hass, address=None, rx_uuid=None, tx_uuid=None):
        self.hass = hass
        self.address = address
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.client = None
        self._callback = None
        self._battery_callbacks = []
        self._unavailable_callbacks = []
        self._available_callbacks = []
        self._state_listener_unsub = None
        self._unavailable_tracker = None
        self._is_connected = False
        self._last_connection_attempt = None
        self._connection_lock = asyncio.Lock()
        self._connection_cooldown = 5  # seconds between connection attempts
        self._shutdown = False
        self._latest_battery = None
        self._latest_position = None
        # Always register the advertisement callback at init
        self._callback = async_register_callback(
            self.hass,
            self._device_update,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
        )
        # Register a global debug callback for all advertisements
        def _debug_adv_callback(service_info, change):
            _LOGGER.debug(f"[DEBUG] Advertisement seen: {service_info}")
        async_register_callback(
            self.hass,
            _debug_adv_callback,
            BluetoothCallbackMatcher(),  # Match all
            BluetoothScanningMode.PASSIVE,
        )
        # Register an unavailable callback
        self._unavailable_tracker = async_track_unavailable(
            self.hass,
            self._device_unavailable,
            self.address,
        )

    async def pair(self) -> bool:
        """Pair with the device."""
        if self._shutdown:
            return False

        async with self._connection_lock:
            if self._is_connected and self.client and self.client.is_connected:
                return True

            try:
                _LOGGER.debug("Attempting to connect to device %s", self.address)
                
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
                        try:
                            asyncio.create_task(cb(battery))
                        except Exception as e:
                            _LOGGER.error("[RyseBLEDevice] Error in battery callback: %s", e)
                if len(data) >= 2:
                    position = data[1]
                    self._latest_position = position
                    _LOGGER.debug("[ADV] Position from advertisement: %d%%", position)
                    if hasattr(self, "update_callback") and self.update_callback:
                        try:
                            asyncio.create_task(self.update_callback(position))
                        except Exception as e:
                            _LOGGER.error("[RyseBLEDevice] Error in position callback: %s", e)

    def add_unavailable_callback(self, callback):
        _LOGGER.debug("[RyseBLEDevice] Adding unavailable callback: %s", callback)
        self._unavailable_callbacks.append(callback)

    def add_available_callback(self, callback):
        _LOGGER.debug("[RyseBLEDevice] Adding available callback: %s", callback)
        self._available_callbacks.append(callback)

    def _device_unavailable(self, service_info: BluetoothServiceInfo) -> None:
        """Handle device becoming unavailable."""
        if self._shutdown:
            return

        _LOGGER.debug("[RyseBLEDevice] _device_unavailable called for %s", self.address)
        _LOGGER.debug("[RyseBLEDevice] Device %s became unavailable", self.address)
        for cb in self._unavailable_callbacks:
            try:
                cb()
            except Exception as e:
                _LOGGER.error("[RyseBLEDevice] Error in unavailable callback: %s", e)
        if self.client and self.client.is_connected:
            asyncio.create_task(self.unpair())

    async def unpair(self):
        """Unpair from the device and clean up resources."""
        self._shutdown = True
        
        if self.client:
            try:
                await self.client.disconnect()
                _LOGGER.debug("[RyseBLEDevice] Device disconnected")
            except Exception as e:
                _LOGGER.error("[RyseBLEDevice] Error disconnecting device: %s", e)
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

    def _handle_device_unavailable(self):
        _LOGGER.warning("[Cover] Device became unavailable, marking entity as unavailable.")
        self._state = "unavailable"
        self._initialized = False
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._initialized = False  # Always start as not initialized
        self._last_state_update = None
        self._restored_state = None
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            _LOGGER.debug("[Cover] Storing last known state for later: %s", last_state.state)
            self._restored_state = last_state
        # Always start as unavailable until a fresh value is received
        self._state = "unavailable"
        self._initialized = False
        self.async_write_ha_state()
        self.setup_entity_state_tracking("sensor.my_ble_device", [])

    def setup_entity_state_tracking(self, entity_id, entities):
        """
        Set up state tracking for the given entity_id. When the entity becomes unavailable, mark all entities as unavailable.
        When it becomes available, mark all entities as available.
        entities: list of entity objects (e.g., cover and sensor)
        """
        if self._state_listener_unsub:
            self._state_listener_unsub()
        @callback
        def _state_listener(event):
            new_state = event.data["new_state"]
            if new_state and new_state.state == STATE_UNAVAILABLE:
                _LOGGER.debug(f"Entity {entity_id} became unavailable")
                for entity in entities:
                    if hasattr(entity, "mark_unavailable"):
                        entity.mark_unavailable()
            elif new_state and new_state.state != STATE_UNAVAILABLE:
                _LOGGER.debug(f"Entity {entity_id} became available: {new_state.state}")
                for entity in entities:
                    if hasattr(entity, "mark_available"):
                        entity.mark_available()
        self._state_listener_unsub = async_track_state_change_event(
            self.hass, {entity_id}, _state_listener
        )

    def cleanup(self):
        if self._state_listener_unsub:
            self._state_listener_unsub()
            self._state_listener_unsub = None
        if self._callback:
            self._callback()
            self._callback = None
        if self._unavailable_tracker:
            self._unavailable_tracker()
            self._unavailable_tracker = None

    async def _update_position(self, position):
        self._initialized = True
        self._last_state_update = datetime.now()
        self.async_write_ha_state()