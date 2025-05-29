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

class RyseBatterySensor(SensorEntity):
    """Representation of a RYSE battery sensor."""

    def __init__(self, device: RyseBLEDevice, entry: ConfigEntry) -> None:
        """Initialize the RYSE battery sensor."""
        self._device = device
        self._entry = entry
        self._attr_name = f"RYSE Battery {entry.data['address']}"
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_available = False
        self._attr_native_value = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"RYSE Smart Shade {self._entry.data['address']}",
            manufacturer="RYSE",
            model="Smart Shade",
        )

    async def async_added_to_hass(self) -> None:
        """Set up the battery monitoring."""
        self._device._battery_callback = self._handle_battery_update
        # Start battery monitoring in the background so setup doesn't block
        self.hass.async_create_task(self._device.start_battery_monitoring(self._handle_battery_update))

    async def _handle_battery_update(self, battery_level: int) -> None:
        """Handle battery level updates."""
        self._attr_native_value = battery_level
        self._attr_available = True
        self.async_write_ha_state() 