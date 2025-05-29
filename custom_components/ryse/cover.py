from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from custom_components.ryse.bluetooth import RyseBLEDevice
import logging
from .const import DOMAIN
from datetime import datetime, timedelta
from homeassistant.helpers.restore_state import RestoreEntity
import asyncio

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartShadeCover(device)])

def build_position_packet(pos: int) -> bytes:
    """Convert MAC address to reversed hex array, prepend a prefix with a position last byte, and append a checksum."""

    # Ensure position is a valid byte (0-100)
    if not (0 <= pos <= 100):
        raise ValueError("position must be between 0 and 100")

    data_bytes = bytes([0xF5, 0x03, 0x01, 0x01, pos])

    # Compute checksum (sum of bytes from the 3rd byte onward, modulo 256)
    checksum = sum(data_bytes[2:]) % 256

    # Append checksum
    return data_bytes + bytes([checksum])

def build_get_position_packet() -> bytes:
    """Build raw data to send to the RYSE ble device to retrieve current position"""

    data_bytes = bytes([0xF5, 0x02, 0x01, 0x03])

    # Compute checksum (sum of bytes from the 3rd byte onward, modulo 256)
    checksum = sum(data_bytes[2:]) % 256

    # Append checksum
    return data_bytes + bytes([checksum])

class SmartShadeCover(CoverEntity, RestoreEntity):
    def __init__(self, device):
        self._device = device
        self._attr_name = f"Smart Shade {device.address}"
        self._attr_unique_id = f"smart_shade_{device.address}"
        self._state = None
        self._current_position = None
        self._battery_level = None
        self._is_closing = False
        self._is_opening = False
        self._last_command_time = 0
        self._command_cooldown = 1.0  # 1 second cooldown between commands
        self._restored = False
        self._last_state_update = None
        self._initialized = False
        self._initial_read_done = False

        # Register the callbacks
        self._device.update_callback = self._update_position
        self._device.add_battery_callback(self._update_battery)

    async def _update_position(self, position):
        """Update cover position when receiving notification."""
        if 0 <= position <= 100:
            self._current_position = 100 - position
            self._state = "open" if position < 100 else "closed"
            self._is_closing = False
            self._is_opening = False
            self._last_state_update = datetime.now()
            self._initialized = True
            _LOGGER.debug(f"Updated cover position: {position}")
        self.async_write_ha_state()

    async def _update_battery(self, battery_level):
        """Update battery level when received from device."""
        self._battery_level = battery_level
        self._initialized = True
        self.async_write_ha_state()

    @property
    def battery_level(self):
        """Return the battery level of the device."""
        return self._battery_level

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # First try to restore from last state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            _LOGGER.info("[Cover] Restoring last known state: %s", last_state.state)
            self._state = last_state.state
            if "current_position" in last_state.attributes:
                self._current_position = int(last_state.attributes["current_position"])
            self._restored = True
            self._initialized = True
            self.async_write_ha_state()

        # Then update from latest advertisement if available
        if self._device._latest_position is not None:
            _LOGGER.info("[Cover] Immediate position update from latest advertisement: %s", self._device._latest_position)
            await self._update_position(self._device._latest_position)
        else:
            # Only attempt a GATT read if no recent advertisement, with timeout
            _LOGGER.info("[Cover] No recent advertisement, attempting GATT read for initial state (timeout 10s)")
            try:
                await asyncio.wait_for(self._read_initial_state(), timeout=10)
            except asyncio.TimeoutError:
                _LOGGER.warning("[Cover] Timed out waiting for GATT read for initial state (10s)")

    async def _read_initial_state(self):
        """Read initial state from device via GATT."""
        if self._initial_read_done:
            return

        try:
            if not self._device.client or not self._device.client.is_connected:
                if not await self._device.pair():
                    _LOGGER.warning("Failed to connect to device for initial state read")
                    return

            _LOGGER.debug("Reading initial position from device")
            bytesinfo = build_get_position_packet()
            await self._device.write_data(bytesinfo)
            self._initial_read_done = True
        except Exception as e:
            _LOGGER.error(f"Error reading initial state: {e}")
        finally:
            # If we still don't have a state, assume closed
            if self._current_position is None:
                _LOGGER.info("[Cover] No position known after GATT read, assuming closed state")
                self._state = "closed"
                self._current_position = 0
                self._initialized = True
                self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if the entity has been initialized."""
        if not self._initialized:
            _LOGGER.debug("[Cover] Entity not yet initialized")
            return False
            
        # If we have a state update, check if it's recent
        if self._last_state_update:
            time_since_update = datetime.now() - self._last_state_update
            if time_since_update > timedelta(minutes=30):
                _LOGGER.debug("[Cover] Last state update was %s ago", time_since_update)
                return False
                
        # If we have a state and position, we're available
        if self._state is not None and self._current_position is not None:
            return True
            
        _LOGGER.debug("[Cover] No valid state or position")
        return False

    async def async_open_cover(self, **kwargs):
        """Open the shade."""
        import time
        current_time = time.time()
        
        # Check if we're already opening or if we're in cooldown
        if self._is_opening or (current_time - self._last_command_time) < self._command_cooldown:
            _LOGGER.debug("Skipping open command - already opening or in cooldown")
            return
            
        self._last_command_time = current_time
        self._is_opening = True
        self._is_closing = False
        self._state = "opening"
        self.async_write_ha_state()
        
        try:
            pdata = build_position_packet(0x00)
            await self._device.write_data(pdata)
            _LOGGER.debug("Binary packet to change position to open")
        except Exception as e:
            _LOGGER.error(f"Error sending open command: {e}")
            self._is_opening = False
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        """Close the shade."""
        import time
        current_time = time.time()
        
        # Check if we're already closing or if we're in cooldown
        if self._is_closing or (current_time - self._last_command_time) < self._command_cooldown:
            _LOGGER.debug("Skipping close command - already closing or in cooldown")
            return
            
        self._last_command_time = current_time
        self._is_closing = True
        self._is_opening = False
        self._state = "closing"
        self.async_write_ha_state()
        
        try:
            pdata = build_position_packet(0x64)
            await self._device.write_data(pdata)
            _LOGGER.debug("Binary packet to change position to close")
        except Exception as e:
            _LOGGER.error(f"Error sending close command: {e}")
            self._is_closing = False
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs):
        """Set the shade to a specific position."""
        import time
        current_time = time.time()
        
        # Check if we're in cooldown
        if (current_time - self._last_command_time) < self._command_cooldown:
            _LOGGER.debug("Skipping position command - in cooldown")
            return
            
        self._last_command_time = current_time
        position = 100 - kwargs.get("position", 0)
        
        if position == 100:
            self._is_closing = True
            self._is_opening = False
            self._state = "closing"
        elif position == 0:
            self._is_opening = True
            self._is_closing = False
            self._state = "opening"
        else:
            self._is_closing = False
            self._is_opening = False
            self._state = "open"
            
        self.async_write_ha_state()
        
        try:
            pdata = build_position_packet(position)
            await self._device.write_data(pdata)
            _LOGGER.debug(f"Binary packet to change position to {position}")
        except Exception as e:
            _LOGGER.error(f"Error sending position command: {e}")
            self._is_closing = False
            self._is_opening = False
            self.async_write_ha_state()

    @property
    def is_closed(self):
        if self._current_position is None:
            return None  # Let HA show as unknown
        return self._state == "closed"

    @property
    def current_cover_position(self) -> int | None:
        if self._current_position is None:
            return None
        if not (0 <= self._current_position <= 100):
            _LOGGER.warning(f"Invalid position value detected: {self._current_position}")
            return None
        return int(self._current_position)

    @property
    def supported_features(self):
        return (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.SET_POSITION
        )

