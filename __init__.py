import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bluetooth import RyseBLEDevice

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

async def async_setup(hass: HomeAssistant, config: dict):
    _LOGGER.debug("Setting up RYSE Device integration")
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
            _LOGGER.debug(f"Getting Device Info")

    async def handle_unpair(call):
        await device.unpair()

    async def handle_read(call):
        data = await device.read_data()
        if data:
            _LOGGER.debug(f"Reading Data")

    async def handle_write(call):
        data = bytes.fromhex(call.data["data"])
        await device.write_data(data)

    hass.services.async_register(DOMAIN, "pair_device", handle_pair)
    hass.services.async_register(DOMAIN, "unpair_device", handle_unpair)
    hass.services.async_register(DOMAIN, "read_info", handle_read)
    hass.services.async_register(DOMAIN, "send_raw_data", handle_write)

    await hass.config_entries.async_forward_entry_setups(entry, ["cover"])

    return True
