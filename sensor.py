"""Example integration using DataUpdateCoordinator."""

import datetime
from zoneinfo import ZoneInfo

import logging
import pandas

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
import homeassistant.util.dt as dt_util
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    async_import_statistics
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

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
    The only difference is we retrieve the config data from the config entry instance.
    It seems this function is run on each (re)start of HASS, 
    TODO so we need a way to check if we need to add the stats or already added them
    """
    # assuming API object stored here by __init__.py
    fusion_api = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    # add plant statistics (this overlaps with device statistics)
    plants = await hass.async_add_executor_job(fusion_api.get_plants)
    for plant in plants:
        coordinator = PlantCoordinator(hass, plant)
        await coordinator.async_config_entry_first_refresh()  # TODO check where this needs to come
        for metric in coordinator.data.values():
            description = metric_to_description(metric)
            if description is not None:
                entities.append(FusionSolarEntity(coordinator, description))

    # add device statistics
    add_device_metrics = False  # TODO enable later
    if add_device_metrics:
        devices = await hass.async_add_executor_job(fusion_api.get_devices)
        for device in devices:
            coordinator = DeviceCoordinator(hass, device)
            await coordinator.async_config_entry_first_refresh()  # TODO check where this needs to come
            for metric in coordinator.data.values():
                description = metric_to_description(metric)
                if description is not None:
                    entities.append(FusionSolarEntity(coordinator, description))

    async_add_entities(entities)  # TODO remove await

    # insert historical data
    _LOGGER.info("adding historical statistics")

    await _insert_statistics(hass, plants)



async def _insert_statistics(hass, plants):
    """Insert historical statistics for last 7 days."""

    base = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    date_list = [base - datetime.timedelta(days=x) for x in range(1,8)]
    for dt in date_list:
        query_time = int(dt.timestamp()) * 1000

        df = await hass.async_add_executor_job(lambda x: plants[0].get_plant_stats(*x, query_time=query_time), [])  # very ugly hack as i am not allowed ot provide keyword arguments
        aggs = {f"{ag}_{col}": (col, ag) for col in df.columns for ag in ['min', 'mean', 'max']}
        df_hour = df.groupby(pandas.Grouper(freq='60Min')).agg(**aggs)

        for column in df.columns:
            # statistic_id = f"{DOMAIN}:{column}".lower() #external statistic
            statistic_id = f"sensor.{column}".lower()

            _LOGGER.info(f"adding historical statistics for column {statistic_id}")

            statistics = []
            for dt, mean, min, max in zip(df_hour.index, df_hour[f"mean_{column}"], df_hour[f"min_{column}"], df_hour[f"max_{column}"]):
                statistics.append(
                    StatisticData(
                        start=dt,
                        mean=mean*1000, #convert to Watt
                        min=min*1000, #convert to Watt
                        max=max*1000, #convert to Watt
                    ))

            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=column,
                # source=DOMAIN,
                source='recorder',
                statistic_id=statistic_id,
                unit_of_measurement=POWER_WATT, # kilo watt not allowed by statistics
            )
            _LOGGER.info(f"adding {len(statistics)} statistics for column {statistic_id}")
            # async_add_external_statistics(hass, metadata, statistics)
            async_import_statistics(hass, metadata, statistics)


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


class PlantCoordinator(DataUpdateCoordinator):
    """My custom plant coordinator."""

    def __init__(self, hass, plant):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=plant.name,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=datetime.timedelta(seconds=300),  # TODO change
        )
        self.plant = plant

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        return await self.hass.async_add_executor_job(self.plant.get_last_plant_stats)


class DeviceCoordinator(DataUpdateCoordinator):
    """My custom device coordinator."""

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
