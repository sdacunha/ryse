from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from .bluetooth import RyseBLEDevice
import logging

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    device = RyseBLEDevice(entry.data['address'], entry.data['rx_uuid'], entry.data['tx_uuid'])
    async_add_entities([SmartShadeCover(device)])

class SmartShadeCover(CoverEntity):
    def __init__(self, device):
        self._device = device
        self._attr_name = f"Smart Shade {device.address}"
        self._attr_unique_id = f"smart_shade_{device.address}"
        self._state = None
        self._current_position = None

    async def async_open_cover(self, **kwargs):
        """Open the shade."""
        await self._device.write_data(bytes([0x01]))  # Example: 0x01 could represent "open"
        self._state = "open"

    async def async_close_cover(self, **kwargs):
        """Close the shade."""
        await self._device.write_data(bytes([0x02]))  # Example: 0x02 could represent "close"
        self._state = "closed"

    async def async_set_cover_position(self, **kwargs):
        """Set the shade to a specific position."""
        position = kwargs.get("position", 0)
        await self._device.write_data(bytes([0x03, position]))  # Example: 0x03 for "set position"
        self._current_position = position
        self._state = "open" if position > 0 else "closed"

    async def async_update(self):
        """Fetch the current state and position from the device."""
        if not self._device.client or not self._device.client.is_connected:
            paired = await self._device.pair()
            if not paired:
                _LOGGER.warning("Failed to pair with device. Skipping update.")
                return

        try:
            data = await self._device.read_data()
            if data:
                self._current_position = data[0]  # Assuming the position is the first byte of `data`
                self._state = "open" if self._current_position > 0 else "closed"
        except Exception as e:
            _LOGGER.error(f"Error reading device data: {e}")

    @property
    def is_closed(self):
        return self._state == "closed"

    @property
    def current_cover_position(self):
        return self._current_position

    @property
    def supported_features(self):
        return (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.SET_POSITION
        )

