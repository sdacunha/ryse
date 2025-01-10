from homeassistant.components.sensor import SensorEntity
from .bluetooth import RyseBLEDevice

async def async_setup_entry(hass, entry, async_add_entities):
    device = RyseBLEDevice(entry.data['address'], entry.data['rx_uuid'], entry.data['tx_uuid'])
    async_add_entities([BLEDeviceSensor(device)])

class BLEDeviceSensor(SensorEntity):
    def __init__(self, device):
        self._device = device
        self._attr_name = f"BLE Device Sensor {device.address}"
        self._attr_unique_id = f"ble_device_sensor_{device.address}"
        self._state = None

    async def async_update(self):
        if await self._device.pair():
            data = await self._device.read_data()
            self._state = data
            await self._device.unpair()
