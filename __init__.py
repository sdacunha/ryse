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

    device = RyseBLEDevice(
        address=entry.data["address"],
        rx_uuid=entry.data["rx_uuid"],
        tx_uuid=entry.data["tx_uuid"],
    )

    async def handle_pair(call):
        paired = await device.pair()
        if paired:
            device_info = await device.get_device_info()
            _LOGGER.info(f"Device Info: {device_info}")

    async def handle_unpair(call):
        await device.unpair()

    async def handle_read(call):
        data = await device.read_data()
        _LOGGER.info(f"Read Data: {data}")

    async def handle_write(call):
        data = bytes.fromhex(call.data["data"])
        await device.write_data(data)

    hass.services.async_register(DOMAIN, "pair_device", handle_pair)
    hass.services.async_register(DOMAIN, "unpair_device", handle_unpair)
    hass.services.async_register(DOMAIN, "read_info", handle_read)
    hass.services.async_register(DOMAIN, "send_raw_data", handle_write)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "cover")
    )

    return True
