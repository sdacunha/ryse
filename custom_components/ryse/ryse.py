import logging
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

    async def connect(self, timeout=15, max_attempts=3):
        for attempt in range(max_attempts):
            try:
                if self.client and self.client.is_connected:
                    self._is_connected = True
                    return True
                if not self.ble_device:
                    raise ConnectionError("No BLEDevice available for connection")
                self.client = BleakClient(self.ble_device)
                await self.client.connect(timeout=timeout)
                if self.client.is_connected:
                    self._is_connected = True
                    return True
            except Exception as e:
                _LOGGER.error(f"Pair attempt {attempt+1} failed: {e}")
        _LOGGER.error("All pair attempts failed.")
        self._is_connected = False
        for callback in self._unavailable_callbacks:
            callback()
        return False

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            self.client = None
            self._is_connected = False
            for callback in self._unavailable_callbacks:
                callback()

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