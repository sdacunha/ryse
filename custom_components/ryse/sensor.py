"""The RYSE Battery Sensor."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from datetime import datetime, timedelta
from homeassistant.helpers.restore_state import RestoreEntity
import re
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .bluetooth import RyseBLEDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RYSE battery sensor."""
    device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RyseBatterySensor(device, entry)])

class RyseBatterySensor(SensorEntity, RestoreEntity):
    """Representation of a RYSE battery sensor."""

    def __init__(self, device: RyseBLEDevice, entry: ConfigEntry) -> None:
        """Initialize the RYSE battery sensor."""
        self._device = device
        self._entry = entry
        name = entry.data.get("name", entry.data['address'])
        self._attr_name = f"{name} Battery"
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._last_update = None  # Track last update time

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        name = self._entry.data.get("name", self._entry.data['address'])
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.address)},
            name=name,
            manufacturer="RYSE Inc.",
            model="GR-0103",
        )

    @property
    def available(self) -> bool:
        """Return True if the sensor and the cover are available, with robust edge case handling."""
        device_reg = dr.async_get(self.hass)
        entity_reg = er.async_get(self.hass)
        device = device_reg.async_get_device(identifiers={(DOMAIN, self._device.address)})
        cover_found = False
        cover_state_val = None
        if device:
            device_id = device.id
            for entity in entity_reg.entities.values():
                if entity.device_id == device_id and entity.domain == "cover":
                    cover_found = True
                    cover_state = self.hass.states.get(entity.entity_id)
                    if cover_state is not None:
                        cover_state_val = cover_state.state
                        if cover_state.state == "unavailable":
                            _LOGGER.debug(f"Battery unavailable: cover entity {entity.entity_id} is unavailable.")
                            return False
        if not cover_found:
            _LOGGER.debug(f"No cover entity found for device {self._device.address}; battery sensor remains available until timeout.")
            if self._last_update is not None and (datetime.now() - self._last_update > timedelta(hours=6)):
                _LOGGER.warning(f"Cover entity for device {self._device.address} has been missing for over 6 hours. Marking battery sensor unavailable.")
                return False
        now = datetime.now()
        if self._last_update is None:
            _LOGGER.debug(f"Battery unavailable: no last update. cover_found={cover_found}, cover_state={cover_state_val}")
            return False
        available = now - self._last_update < timedelta(hours=6)
        if not available:
            _LOGGER.debug(f"Battery unavailable: last update too old. last_update={self._last_update}, now={now}")
        return available

    async def async_added_to_hass(self) -> None:
        """Set up the battery monitoring."""
        _LOGGER.info("[BatterySensor] Registering battery callback for sensor entity (device id: %s)", id(self._device))
        self._device.add_battery_callback(self._handle_battery_update)
        # Use latest battery value from advertisement if available
        if self._device._latest_battery is not None:
            _LOGGER.info("[BatterySensor] Immediate battery update from latest advertisement: %s", self._device._latest_battery)
            await self._handle_battery_update(self._device._latest_battery)
        elif self._device._battery_level is not None:
            _LOGGER.info("[BatterySensor] Immediate battery update on add: %s", self._device._battery_level)
            await self._handle_battery_update(self._device._battery_level)
        else:
            # Restore last known state
            last_state = await self.async_get_last_state()
            if last_state and last_state.state not in (None, "unknown", "unavailable"):
                _LOGGER.info("[BatterySensor] Restoring last known battery value: %s", last_state.state)
                self._attr_native_value = int(last_state.state)
                self._last_update = datetime.now()
                self.async_write_ha_state()

    async def _handle_battery_update(self, battery_level: int) -> None:
        """Handle battery level updates."""
        _LOGGER.debug("Battery sensor callback: received battery level %s", battery_level)
        self._attr_native_value = battery_level
        self._last_update = datetime.now()  # Set before writing state
        _LOGGER.debug("Battery sensor _last_update set to %s", self._last_update)
        self.async_write_ha_state() 