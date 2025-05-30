from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from custom_components.ryse.bluetooth import RyseBLEDevice
import logging
from .const import DOMAIN
from datetime import datetime, timedelta
from homeassistant.helpers.restore_state import RestoreEntity
import asyncio
from homeassistant.helpers.entity import DeviceInfo
import re
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartShadeCover(device, entry)])

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
    def __init__(self, device, entry):
        self._device = device
        self._entry = entry
        name = entry.data.get("name", f"SmartShade {device.address}")
        self._attr_name = name
        sanitized = re.sub(r'[^a-z0-9_]+', '', re.sub(r'\W+', '_', name.lower()))
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
        # Register callbacks
        self._device.update_callback = self._update_position
        self._device.add_battery_callback(self._update_battery)
        self._device.add_unavailable_callback(self._handle_device_unavailable)

    async def _update_position(self, position):
        """Update cover position when receiving notification (advertisement)."""
        if 0 <= position <= 100:
            self._current_position = 100 - position
            self._state = "open" if position < 100 else "closed"
            self._is_closing = False
            self._is_opening = False
            self._last_state_update = datetime.now()
            self._initialized = True
            _LOGGER.debug(f"[Cover] _update_position: _initialized set to {self._initialized}, _last_state_update set to {self._last_state_update}")
        self.async_write_ha_state()

    async def _update_battery(self, battery_level):
        """Update battery level when received from device."""
        self._battery_level = battery_level
        self._initialized = True
        _LOGGER.debug(f"[Cover] _update_battery: _initialized set to {self._initialized}")
        self.async_write_ha_state()

    def _handle_device_unavailable(self):
        _LOGGER.warning("[Cover] Device became unavailable, marking entity as unavailable.")
        self._state = "unavailable"
        self._initialized = False
        self._last_state_update = None
        self.async_write_ha_state()

    @property
    def battery_level(self):
        """Return the battery level of the device."""
        return self._battery_level

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._initialized = False
        self._last_state_update = None
        _LOGGER.debug(f"[Cover] async_added_to_hass: _initialized set to {self._initialized}, _last_state_update set to {self._last_state_update}")
        self._state = "unavailable"
        self.async_write_ha_state()
        _LOGGER.debug(f"[Cover] Registering state tracking for {self.entity_id}")
        self._device.add_unavailable_callback(self._handle_device_unavailable)
        self._device.setup_entity_state_tracking(self.entity_id, [self])
        self._restored_state = None
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            _LOGGER.debug("[Cover] Storing last known state for later: %s", last_state.state)
            self._restored_state = last_state
        _LOGGER.debug(f"[Cover] async_added_to_hass: _device._latest_position = {self._device._latest_position}")
        if self._device._latest_position is not None:
            self.hass.async_create_task(self._update_position(self._device._latest_position))
        else:
            # No advertisement seen yet, try GATT poll
            try:
                _LOGGER.debug("[Cover] No advertisement at startup, attempting GATT poll for availability.")
                await self._read_initial_state()
            except Exception as e:
                _LOGGER.error(f"[Cover] GATT poll at startup failed: {e}")
            if self._device._latest_position is None:
                self._state = "unavailable"
                self.async_write_ha_state()
        # Start periodic GATT poll/check
        async def _gatt_poll(now):
            if self._last_state_update is None or (datetime.now() - self._last_state_update > timedelta(minutes=10)):
                _LOGGER.debug(f"[Cover] GATT poll: last update is stale, attempting GATT read before marking unavailable.")
                try:
                    await self._read_initial_state()
                    if self._last_state_update is None or (datetime.now() - self._last_state_update > timedelta(minutes=10)):
                        _LOGGER.debug(f"[Cover] GATT poll: still stale after GATT read, marking unavailable.")
                        self.mark_unavailable()
                    else:
                        _LOGGER.debug(f"[Cover] GATT poll: state refreshed, not marking unavailable.")
                except Exception as e:
                    _LOGGER.error(f"[Cover] GATT poll failed: {e}")
                    self.mark_unavailable()
        self._gatt_poll_unsub = async_track_time_interval(self.hass, _gatt_poll, timedelta(minutes=10))

    async def async_will_remove_from_hass(self):
        if hasattr(self, '_gatt_poll_unsub') and self._gatt_poll_unsub:
            self._gatt_poll_unsub()
            self._gatt_poll_unsub = None
        await super().async_will_remove_from_hass()

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
                _LOGGER.debug("[Cover] No position known after GATT read, assuming closed state")
                self._state = "closed"
                self._current_position = 0
                self._initialized = True
                self.async_write_ha_state()

    @property
    def available(self) -> bool:
        result = False
        if not self._initialized:
            result = False
        elif self._last_state_update and (datetime.now() - self._last_state_update < timedelta(minutes=10)):
            result = True
        _LOGGER.debug(f"[Cover] available property: _initialized={self._initialized}, _last_state_update={self._last_state_update}, returns {result}")
        return result

    async def async_open_cover(self, **kwargs):
        """Open the shade."""
        import time
        current_time = time.time()
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
            self.mark_unavailable()
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs):
        """Close the shade."""
        import time
        current_time = time.time()
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
            self.mark_unavailable()
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs):
        """Set the shade to a specific position."""
        import time
        current_time = time.time()
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
            self.mark_unavailable()
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

    @property
    def device_info(self) -> DeviceInfo:
        name = self._entry.data.get("name", f"SmartShade {self._device.address}")
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.address)},
            name=name,
            manufacturer="RYSE Inc.",
            model="Ryse SmartShade",
            configuration_url="https://github.com/sdacunha/ryse"
        )

    def mark_unavailable(self):
        """Mark the cover as unavailable and update state."""
        _LOGGER.debug(f"[Cover] mark_unavailable called for {self.entity_id}")
        self._state = "unavailable"
        self._initialized = False
        self._last_state_update = None
        _LOGGER.debug(f"[Cover] mark_unavailable: _initialized set to {self._initialized}, _last_state_update set to {self._last_state_update}")
        self.async_write_ha_state()

    def mark_available(self):
        """Mark the cover as available (unknown until a fresh value is received) and update state."""
        _LOGGER.debug(f"[Cover] mark_available called for {self.entity_id}")
        self._state = "unknown"
        self.async_write_ha_state()

