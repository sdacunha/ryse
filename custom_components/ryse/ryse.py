import logging
import asyncio
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from .const import HARDCODED_UUIDS

_LOGGER = logging.getLogger(__name__)

# Use the RX and TX UUIDs for operations
POSITION_CHAR_UUID = HARDCODED_UUIDS["rx_uuid"]
COMMAND_CHAR_UUID = HARDCODED_UUIDS["tx_uuid"]

class RyseDevice:
    def __init__(self, address: str):
        self.address = address
        self.ble_device: BLEDevice | None = None
        self.client: BleakClient | None = None
        self._battery_callbacks = []
        self._unavailable_callbacks = []
        self._adv_callbacks = []
        self._latest_battery = None
        self._battery_level = None
        self._is_connected = False
        self._connection_lock = asyncio.Lock()
        self._connecting = False

    def add_battery_callback(self, callback):
        """Add a callback for battery updates."""
        self._battery_callbacks.append(callback)

    def add_unavailable_callback(self, callback):
        """Add a callback for device unavailability."""
        self._unavailable_callbacks.append(callback)

    def add_adv_callback(self, callback):
        """Add a callback for advertisement updates."""
        self._adv_callbacks.append(callback)

    def get_battery_level(self) -> int | None:
        """Get the latest battery level."""
        return self._battery_level

    def set_ble_device(self, ble_device: BLEDevice | None) -> None:
        self.ble_device = ble_device

    def update_ble_device_from_adv(self, service_info):
        if hasattr(service_info, 'device') and service_info.device:
            self.set_ble_device(service_info.device)

    async def connect(self, timeout=10, max_attempts=3):
        """Connect with exponential backoff retry logic and connection state tracking."""
        async with self._connection_lock:
            # Already connected
            if self.client and self.client.is_connected:
                self._is_connected = True
                self._connecting = False
                _LOGGER.debug(f"[{self.address}] Already connected")
                return True

            # Prevent concurrent connection attempts
            if self._connecting:
                _LOGGER.debug(f"[{self.address}] Connection already in progress")
                return False

            self._connecting = True

            if not self.ble_device:
                _LOGGER.error(f"[{self.address}] No BLEDevice available for connection")
                self._connecting = False
                raise ConnectionError("No BLEDevice available for connection")

            # Shorter timeouts for faster response (especially for battery-powered devices in sleep mode)
            # Try quick first (5s), then normal (10s), then extended (15s)
            timeouts = [5, 10, 15]
            backoff_delays = [0, 0.3, 0.5]  # Faster retries: immediate, 300ms, 500ms

            for attempt in range(max_attempts):
                try:
                    attempt_timeout = timeouts[attempt] if attempt < len(timeouts) else timeout

                    # Backoff delay before retry (except first attempt)
                    if backoff_delays[attempt] > 0:
                        _LOGGER.debug(f"[{self.address}] Waiting {backoff_delays[attempt]}s before retry {attempt+1}")
                        await asyncio.sleep(backoff_delays[attempt])

                    _LOGGER.info(f"[{self.address}] Connection attempt {attempt+1}/{max_attempts} (timeout: {attempt_timeout}s)")

                    self.client = BleakClient(self.ble_device)
                    await self.client.connect(timeout=attempt_timeout)

                    if self.client.is_connected:
                        self._is_connected = True
                        self._connecting = False
                        _LOGGER.info(f"[{self.address}] Successfully connected on attempt {attempt+1}")
                        return True

                except asyncio.TimeoutError:
                    _LOGGER.warning(f"[{self.address}] Connection attempt {attempt+1} timed out after {attempt_timeout}s")
                except Exception as e:
                    _LOGGER.error(f"[{self.address}] Connection attempt {attempt+1} failed: {type(e).__name__}: {e}")

            # All attempts failed
            _LOGGER.error(f"[{self.address}] All {max_attempts} connection attempts failed")
            self._is_connected = False
            self._connecting = False
            for callback in self._unavailable_callbacks:
                callback()
            return False

    async def disconnect(self):
        """Disconnect from the device with proper state tracking."""
        async with self._connection_lock:
            if self.client and self.client.is_connected:
                _LOGGER.debug(f"[{self.address}] Disconnecting")
                await self.client.disconnect()
                self.client = None
                self._is_connected = False
                self._connecting = False
                for callback in self._unavailable_callbacks:
                    callback()
            else:
                _LOGGER.debug(f"[{self.address}] Already disconnected")

    async def set_position(self, position: int):
        if not (0 <= position <= 100):
            raise ValueError("position must be between 0 and 100")
        data_bytes = bytes([0xF5, 0x03, 0x01, 0x01, position])
        checksum = sum(data_bytes[2:]) % 256
        packet = data_bytes + bytes([checksum])
        await self.write_gatt(COMMAND_CHAR_UUID, packet)

    async def open(self):
        await self.set_position(0)

    async def close(self):
        await self.set_position(100)

    async def get_battery(self) -> int | None:
        data = await self.read_gatt(POSITION_CHAR_UUID)
        if data and len(data) >= 3:
            self._battery_level = data[2]
            self._latest_battery = data[2]
            for callback in self._battery_callbacks:
                await callback(data[2])
            return data[2]
        return None

    async def get_position(self) -> int | None:
        data = await self.read_gatt(POSITION_CHAR_UUID)
        if data and len(data) >= 2:
            return data[1]
        return None

    async def read_gatt(self, char_uuid: str) -> bytes | None:
        if not self.client or not self.client.is_connected:
            raise ConnectionError("Not connected to device")
        return await self.client.read_gatt_char(char_uuid)

    async def write_gatt(self, char_uuid: str, data: bytes):
        if not self.client or not self.client.is_connected:
            raise ConnectionError("Not connected to device")
        await self.client.write_gatt_char(char_uuid, data)

    @staticmethod
    def parse_advertisement(service_info) -> dict:
        result = {}
        for mfr_id, data in getattr(service_info, 'manufacturer_data', {}).items():
            if len(data) >= 3:
                result['position'] = data[1]
                result['battery'] = data[2]
        return result

    def poll_needed(self, seconds_since_last_poll):
        """Determine if a poll is needed. Poll every 5 minutes as fallback (rely on advertisements primarily)."""
        if seconds_since_last_poll is None:
            return True
        # Changed from 60s to 300s (5 minutes) to rely more on advertisements
        # Only poll as fallback when device stops advertising
        return seconds_since_last_poll > 300 