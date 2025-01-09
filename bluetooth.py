import asyncio
from bleak import BleakClient, BleakScanner
import logging

_LOGGER = logging.getLogger(__name__)

class RyseBLEDevice:
    def __init__(self, address, rx_uuid, tx_uuid):
        self.address = address
        self.rx_uuid = rx_uuid
        self.tx_uuid = tx_uuid
        self.client = None

    async def pair(self):
        _LOGGER.info(f"Pairing with device {self.address}")
        self.client = BleakClient(self.address)
        await self.client.connect()
        return self.client.is_connected

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
