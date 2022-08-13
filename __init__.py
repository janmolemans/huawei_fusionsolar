"""The Huawei Fusionsolar integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import  Platform
from homeassistant.core import HomeAssistant
from .const import CONF_USERNAME, CONF_PASSWORD, CONF_REGION


from .const import DOMAIN
from .FusionSolarPy.src.fusion_solar_py.client import FusionSolarClient


# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Huawei Fusionsolar from a config entry."""
    # Store an instance of the "connecting" class (=API object) that does the work of speaking
    # with your actual devices.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = FusionSolarClient(entry.data[CONF_USERNAME],
                                                                        entry.data[CONF_PASSWORD], 
                                                                        entry.data[CONF_REGION])

    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
