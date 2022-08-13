"""Example integration using DataUpdateCoordinator."""

from datetime import timedelta
import logging

import async_timeout

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback, HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEVICE_CLASS_POWER,
    POWER_KILO_WATT,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, ATTR_DATA_REALKPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant,
                            config_entry: ConfigEntry,
                            async_add_entities,
                        ):
    """
    async_setup_entry function  will accept a config entry instance 
    and create the sensors for the component
    This function looks nearly identical to the async_setup_platform function 
     which is used for setting up the sensors from configuration.yaml.
    The only difference is we retrieve the config data from the config entry instance."""
    # assuming API object stored here by __init__.py
    fusion_api = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = MyCoordinator(hass, fusion_api)

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        FusionSolarPowerEntity(coordinator, name=key) for key in coordinator.data
    )


class MyCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, my_api):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="My fusionsolar sensor",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30), #TODO change
        )
        self.my_api = my_api

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        # try:
        # Note: asyncio.TimeoutError and aiohttp.ClientError are already
        # handled by the data update coordinator.
        return await self.hass.async_add_executor_job(
            self.my_api.get_last_plant_stats, plant_id
        )
        # async with async_timeout.timeout(10):
        #     return await self.my_api.get_power_status()

        # except ApiAuthError as err:
        #     # Raising ConfigEntryAuthFailed will cancel future updates
        #     # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #     raise ConfigEntryAuthFailed from err
        # except ApiError as err:
        #     raise UpdateFailed(f"Error communicating with API: {err}")



class FusionSolarPowerEntity(CoordinatorEntity, SensorEntity):
    """Base class for all FusionSolarPower entities.
    
    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available
      """
    def __init__(
        self,
        coordinator,
        name
    ):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self._state = None
        self._name = name

    @property
    def device_class(self):
        return DEVICE_CLASS_POWER

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self):
        if self.coordinator.data[self.name] is not None:
            return float(self.coordinator.data[self.name])
        else:
            return None

    @property
    def unique_id(self) -> str:
        return self.name

    @property
    def unit_of_measurement(self):
        return POWER_KILO_WATT