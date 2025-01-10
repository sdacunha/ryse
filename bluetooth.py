import asyncio
from bleak import BleakClient, BleakScanner
import logging

_LOGGER = logging.getLogger(__name__)

class RyseBLEDevice:
    def __init__(self, address=None, rx_uuid=None, tx_uuid=None):
        self.address = address
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.client = None

    async def pair(self):
        if not self.address:
            _LOGGER.error("No device address provided for pairing.")
            return False
        _LOGGER.info(f"Pairing with device {self.address}")
        self.client = BleakClient(self.address)
        try:
            await self.client.connect()
            if self.client.is_connected:
                _LOGGER.info(f"Successfully paired with {self.address}")
                return True
        except Exception as e:
            _LOGGER.error(f"Error pairing with device: {e}")
        return False

    async def get_device_info(self):
        if self.client:
            try:
                manufacturer_data = self.client.services
                _LOGGER.info(f"Manufacturer Data: {manufacturer_data}")
                return manufacturer_data
            except Exception as e:
                _LOGGER.error(f"Failed to get device info: {e}")
        return None

    async def unpair(self):
        if self.client:
            await self.client.disconnect()
            _LOGGER.info("Device disconnected")
            self.client = None

    async def read_data(self):
        if self.client:
            data = await self.client.read_gatt_char(self.rx_uuid)
            _LOGGER.info(f"Received: {data}")
            return data

    async def write_data(self, data):
        if self.client:
            await self.client.write_gatt_char(self.tx_uuid, data)
            _LOGGER.info(f"Sent: {data}")

    async def scan_and_pair(self):
        _LOGGER.info("Scanning for BLE devices...")
        devices = await BleakScanner.discover()
        for device in devices:
            _LOGGER.info(f"Found device: {device.name} ({device.address})")
            if device.name and "target-device-name" in device.name.lower():
                _LOGGER.info(f"Attempting to pair with {device.name} ({device.address})")
                self.address = device.address
                return await self.pair()
        _LOGGER.warning("No suitable devices found to pair")
        return False
