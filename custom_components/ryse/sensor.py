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
        """Return True if the sensor and the cover are available."""
        # Try to get the cover entity for this device
        cover_entity_id = f"cover.{self._entry.data.get('name', self._entry.data['address']).lower().replace(' ', '_')}"
        cover = self.hass.states.get(cover_entity_id)
        if cover is not None and cover.state == "unavailable":
            return False
        now = datetime.now()
        _LOGGER.debug("Battery sensor available check: now=%s, last_update=%s", now, self._last_update)
        if self._last_update is None:
            return False
        return now - self._last_update < timedelta(hours=6)

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
        self._last_update = datetime.now()
        self.async_write_ha_state() 