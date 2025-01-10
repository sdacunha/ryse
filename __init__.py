import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bluetooth import RyseBLEDevice

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

async def async_setup(hass: HomeAssistant, config: dict):
    _LOGGER.info("Setting up RYSE Device integration")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    device = RyseBLEDevice(entry.data['address'], entry.data['rx_uuid'], entry.data['tx_uuid'])

    async def handle_pair(call):
        await device.pair()
        device_info = await device.get_device_info()
        _LOGGER.info(f"Device Info: {device_info}")

    async def handle_unpair(call):
        await device.unpair()

    async def handle_read(call):
        data = await device.read_data()
        _LOGGER.info(f"Read Data: {data}")

    async def handle_write(call):
        data = bytes.fromhex(call.data['data'])
        await device.write_data(data)

    async def handle_scan_and_pair(call):
        await device.scan_and_pair()

    hass.services.async_register(DOMAIN, "pair_device", handle_pair)
    hass.services.async_register(DOMAIN, "unpair_device", handle_unpair)
    hass.services.async_register(DOMAIN, "read_info", handle_read)
    hass.services.async_register(DOMAIN, "send_raw_data", handle_write)
    hass.services.async_register(DOMAIN, "scan_and_pair", handle_scan_and_pair)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    return True
