"""Example integration using DataUpdateCoordinator."""

import datetime
from zoneinfo import ZoneInfo

import logging

import async_timeout

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import callback, HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    FREQUENCY_HERTZ,
    PERCENTAGE,
    POWER_VOLT_AMPERE_REACTIVE,
    POWER_KILO_WATT,
    POWER_WATT,
    TEMP_CELSIUS,
    TIME_MINUTES,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, ATTR_DATA_REALKPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
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
    devices = await hass.async_add_executor_job(fusion_api.get_devices)

    entities = []
    for device in devices:
        coordinator = DeviceCoordinator(hass, device)
        await coordinator.async_config_entry_first_refresh()  # TODO check where this needs to come
        for metric in coordinator.data.values():
            description = metric_to_description(metric)
            if description is not None:
                entities.append(FusionSolarEntity(coordinator, description))
    async_add_entities(entities)
    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    # await coordinator.async_config_entry_first_refresh()

    # async_add_entities(
    #     FusionSolarPowerEntity(coordinator, name=key) for key in coordinator.data
    # )


def metric_to_description(metric):
    device_class = None
    native_unit_of_measurement = None
    entity_category = None
    state_class = None

    if (
        metric.name.lower()
        in [
            j
            for i in range(3, 25)
            for j in (
                f"MPPT {i} DC cumulative energy".lower(),
                f"PV{i} input current".lower(),
                f"PV{i} input voltage".lower(),
            )
        ]
    ) or ("Device feature code" in metric.name):
        return None

    if metric.unit == "kW":
        device_class = SensorDeviceClass.POWER
        native_unit_of_measurement = POWER_KILO_WATT
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "W":
        device_class = SensorDeviceClass.POWER
        native_unit_of_measurement = POWER_WATT
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "kWh":
        device_class = SensorDeviceClass.ENERGY
        native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        state_class = SensorStateClass.TOTAL_INCREASING
    elif metric.unit == "V":
        device_class = SensorDeviceClass.VOLTAGE
        native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "A":
        device_class = SensorDeviceClass.CURRENT
        native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "%":
        if "Battery" in metric.name:
            device_class = SensorDeviceClass.BATTERY
            native_unit_of_measurement = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
        elif metric.name == "Inverter efficiency":
            native_unit_of_measurement = PERCENTAGE
            state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "℃":  # u"\u2103"
        device_class = SensorDeviceClass.TEMPERATURE
        native_unit_of_measurement = TEMP_CELSIUS
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "Hz":
        device_class = SensorDeviceClass.FREQUENCY
        native_unit_of_measurement = FREQUENCY_HERTZ
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "min":
        device_class = SensorDeviceClass.DURATION
        native_unit_of_measurement = TIME_MINUTES
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "Var":
        device_class = SensorDeviceClass.REACTIVE_POWER
        native_unit_of_measurement = POWER_VOLT_AMPERE_REACTIVE
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "kVar":
        device_class = SensorDeviceClass.REACTIVE_POWER
        native_unit_of_measurement = "kVar"
        state_class = SensorStateClass.MEASUREMENT
    elif metric.unit == "":
        # native_unit_of_measurement = metric.unit
        if metric.name == "Power factor":
            device_class = SensorDeviceClass.POWER_FACTOR
            state_class = SensorStateClass.MEASUREMENT
        elif metric.name in ("Inverter startup time", "Inverter shutdown time"):
            device_class = SensorDeviceClass.TIMESTAMP
            entity_category = EntityCategory.DIAGNOSTIC
        elif "status" in metric.name.lower():
            entity_category = EntityCategory.DIAGNOSTIC
    else:
        _LOGGER.warn(f"no match found for {metric.name}, {metric.unit}")

    return SensorEntityDescription(
        key=f"{metric.parent}-{metric.name}",
        name=metric.name,
        native_unit_of_measurement=native_unit_of_measurement,
        device_class=device_class,
        state_class=state_class,
        entity_category=entity_category,
    )


class DeviceCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, device):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=device.name,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=datetime.timedelta(seconds=300),  # TODO change
        )
        self.device = device

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        # try:
        # Note: asyncio.TimeoutError and aiohttp.ClientError are already
        # handled by the data update coordinator.
        # await self.hass.async_add_executor_job(self.my_api.get_plants)
        # return await self.hass.async_add_executor_job(
        #     self.my_api.plants[0].get_last_plant_stats
        #             )
        return await self.hass.async_add_executor_job(self.device.get_device_stats)
        # async with async_timeout.timeout(10):
        #     return await self.my_api.get_power_status()

        # except ApiAuthError as err:
        #     # Raising ConfigEntryAuthFailed will cancel future updates
        #     # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #     raise ConfigEntryAuthFailed from err
        # except ApiError as err:
        #     raise UpdateFailed(f"Error communicating with API: {err}")


class FusionSolarEntity(CoordinatorEntity, SensorEntity):
    """Huawei Solar Sensor which receives its data via an DataUpdateCoordinator."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
    ):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)

        self.coordinator = coordinator
        self.entity_description = description

        # self._attr_device_info = device_info
        # self._attr_unique_id = f"{coordinator.bridge.serial_number}_{description.key}"

    @property
    def native_value(self):
        """Native sensor value."""
        value = self.coordinator.data[self.entity_description.name].value
        if self.entity_description.name in (
            "Inverter startup time",
            "Inverter shutdown time",
        ):
            if value == "N/A":
                return None
            else:
                return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=ZoneInfo("Europe/Brussels")
                )
        try:
            return float(value)
        except ValueError:
            return value


# class FusionSolarEntity(CoordinatorEntity, SensorEntity):
#     """Base class for all FusionSolarPower entities.

#     The CoordinatorEntity class provides:
#       should_poll
#       async_update
#       async_added_to_hass
#       available
#     """

#     def __init__(self, coordinator, metric):
#         """Pass coordinator to CoordinatorEntity."""
#         super().__init__(coordinator)
#         self._state = None
#         self._metric = metric
#         self._name = metric.name

#     # @property
#     # def device_class(self):
#     #     if self.metric.unit == 'kW':
#     #         return SensorDeviceClass.POWER
#     #     elif self.metric.unit == 'kWh':
#     #         return SensorDeviceClass.ENERGY

#     @property
#     def name(self) -> str:
#         return self._name

#     @property
#     def state(self):
#         if self.coordinator.data[self.name] is not None:
#             return float(self.coordinator.data[self.name])
#         else:
#             return None

#     @property
#     def unique_id(self) -> str:
#         return self.name

#     @property
#     def unit_of_measurement(self):
#         if self._device.metric.unit == "kW":
#             return POWER_KILO_WATT
#         elif self._device.metric.unit == "kWh":
#             return ENERGY_KILO_WATT_HOUR

#     # @property
#     # def state_class(self) -> str:
#     #     return STATE_CLASS_TOTAL_INCREASING
