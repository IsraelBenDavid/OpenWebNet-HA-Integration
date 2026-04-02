"""Config flow for OpenWebNet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .const import DEFAULT_PORT, DOMAIN
from .openwebnet import OpenWebNetGateway

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PASSWORD): str,
    }
)


class OpenWebNetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenWebNet."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step \u2014 gateway connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD)

            # Prevent duplicate entries for the same host:port
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            # Test the connection
            gateway = OpenWebNetGateway(host, port, password=password)
            success = await gateway.test_connection()

            if success:
                return self.async_create_entry(
                    title=f"OpenWebNet ({host})",
                    data=user_input,
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
