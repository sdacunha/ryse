"""The RYSE BLE Device integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bluetooth import RyseBLEDevice

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ryse"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the RYSE component."""
    _LOGGER.info("Setting up RYSE Device integration")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RYSE from a config entry."""
    _LOGGER.info("Setting up RYSE entry: %s", entry.data)
    
    # Create device instance
    device = RyseBLEDevice(
        hass,
        entry.data["address"],
        entry.data["rx_uuid"],
        entry.data["tx_uuid"]
    )
    _LOGGER.info("[init] Created RyseBLEDevice (id: %s) for address: %s", id(device), entry.data["address"])
    
    # Store device in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["cover", "sensor"])
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading RYSE entry: %s", entry.data)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["cover", "sensor"])
    
    if unload_ok:
        # Clean up device
        device = hass.data[DOMAIN].pop(entry.entry_id)
        await device.unpair()
    
    return unload_ok
