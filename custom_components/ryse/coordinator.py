from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import ActiveBluetoothDataUpdateCoordinator
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import STATE_UNAVAILABLE
from datetime import datetime, timedelta
import asyncio
import logging
import inspect
from .ryse import RyseDevice
from .const import HARDCODED_UUIDS

_LOGGER = logging.getLogger(__name__)

class RyseCoordinator(ActiveBluetoothDataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, address: str, device: RyseDevice, name: str):
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            address=address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_update,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=True,
        )
        self.device = device
        self._name = name
        self._position = None
        self._battery = None
        self._last_adv = None
        self._available = False
        self._ready_event = asyncio.Event()
        self._was_unavailable = True
        self._unavailable_cancel = bluetooth.async_track_unavailable(
            hass, self._handle_unavailable, address, connectable=True
        )
        self._adv_cancel = bluetooth.async_register_callback(
            hass, self._handle_adv, {"address": address}, bluetooth.BluetoothScanningMode.ACTIVE
        )

    @callback
    def _handle_adv(self, service_info, change):
        # Always update BLE device reference from latest adv
        if hasattr(service_info, 'device') and service_info.device:
            self.device.set_ble_device(service_info.device)
        adv = self.device.parse_advertisement(service_info)
        if adv.get('position') is not None:
            self._position = adv['position']
            self._ready_event.set()  # Mark as ready if we get a valid adv
        if adv.get('battery') is not None:
            self._battery = adv['battery']
            # Call battery callbacks with the new battery value
            for callback in self.device._battery_callbacks:
                if inspect.iscoroutinefunction(callback):
                    self.hass.async_create_task(callback(adv['battery']))
                else:
                    callback(adv['battery'])
            # Call advertisement callbacks
            for callback in self.device._adv_callbacks:
                if inspect.iscoroutinefunction(callback):
                    self.hass.async_create_task(callback())
                else:
                    callback()
        self._last_adv = datetime.now()
        self._available = True
        if self._was_unavailable:
            _LOGGER.info(f"Device {self._name} is online")
            self._was_unavailable = False
        self.async_update_listeners()

    @callback
    def _handle_unavailable(self, service_info):
        _LOGGER.info(f"[Coordinator] Device {self._name} became unavailable")
        self._available = False
        self._was_unavailable = True
        self.async_update_listeners()

    @callback
    def _needs_poll(self, service_info, seconds_since_last_poll):
        # Only poll if hass is running, we need to poll, and we have a connectable BLE device
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        return (
            self.hass.state == self.hass.CoreState.running and
            (self._position is None or self._battery is None or (seconds_since_last_poll or 0) > 3600)
            and bool(ble_device)
        )

    async def _async_update(self, service_info):
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if not ble_device:
            self._available = False
            self._was_unavailable = True
            self.async_update_listeners()
            return
        self.device.set_ble_device(ble_device)
        if not await self.device.connect():
            self._available = False
            self._was_unavailable = True
            self.async_update_listeners()
            return
        try:
            data = await self.device.read_gatt(HARDCODED_UUIDS["rx_uuid"])
            # Parse GATT data for position and battery
            if len(data) >= 3:
                self._position = data[1]
                self._battery = data[2]
                self._available = True
                if self._was_unavailable:
                    _LOGGER.info(f"Device {self._name} is online (via GATT poll)")
                    self._was_unavailable = False
        except Exception as e:
            _LOGGER.error(f"[Coordinator] GATT poll failed: {e}")
            self._available = False
            self._was_unavailable = True
        self.async_update_listeners()

    async def async_wait_ready(self, timeout=30):
        try:
            async with asyncio.timeout(timeout):
                await self._ready_event.wait()
                return True
        except TimeoutError:
            return False

    @property
    def position(self):
        return self._position

    @property
    def battery(self):
        return self._battery

    @property
    def available(self):
        return self._available

    async def async_update_battery(self, battery_level: int | None) -> None:
        """Update the battery level and notify listeners."""
        self._battery = battery_level
        self.async_update_listeners()

    @property
    def name(self):
        return self._name

    async def _ensure_connected(self) -> bool:
        """Ensure the device is connected before performing operations."""
        if not self.device.client or not self.device.client.is_connected:
            ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
            if not ble_device:
                self._available = False
                self._was_unavailable = True
                self.async_update_listeners()
                return False
            self.device.set_ble_device(ble_device)
            if not await self.device.connect():
                self._available = False
                self._was_unavailable = True
                self.async_update_listeners()
                return False
        return True

    async def async_set_position(self, position: int) -> None:
        """Set the cover position."""
        if await self._ensure_connected():
            await self.device.set_position(position)

    async def async_open_cover(self) -> None:
        """Open the cover."""
        if await self._ensure_connected():
            await self.device.open()

    async def async_close_cover(self) -> None:
        """Close the cover."""
        if await self._ensure_connected():
            await self.device.close() 