"""Config flow for Huawei Fusionsolar integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
# from homeassistant.components.sensor import PLATFORM_SCHEMA

from .const import DOMAIN, CONF_REGION, CONF_USERNAME, CONF_PASSWORD
from .FusionSolarPy.src.fusion_solar_py.client import FusionSolarClient

_LOGGER = logging.getLogger(__name__)

# TODO adjust the data schema to the data that you need
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="region04eu5"): str,
        vol.Required(CONF_USERNAME, default="jan.molemans@gmail.com"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def validate_credentials(username, password, region):
    client =  FusionSolarClient(username, password, region)
    client._login()

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO validate the data can be used to set up a connection.

    # If your PyPI package is not built with async, pass your methods
    # to the executor:
    await hass.async_add_executor_job(
        validate_credentials, data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_REGION]
    )

    # try: 
    #     client =  FusionSolarClient(data["username/email"], data["password"], data["region"])
    # except: #TODO catch fusionsolar exceptions and raise the appropriate exceptions
    #     raise InvalidAuth
    # if not await hub.authenticate(data["username/email"], data["password"]):
    #     raise InvalidAuth

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    return {"title": "plant_name"} #TODO create method to get plant name


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Huawei Fusionsolar."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
