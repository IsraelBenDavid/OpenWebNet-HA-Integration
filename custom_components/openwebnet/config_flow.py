"""Config flow for OpenWebNet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_SERIAL_PORT,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_TCP,
    DEFAULT_PORT,
    DOMAIN,
)
from .openwebnet import OpenWebNetGateway

_LOGGER = logging.getLogger(__name__)

STEP_CONNECTION_TYPE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_TCP): vol.In(
            {
                CONNECTION_TYPE_TCP: "TCP/IP (Ethernet gateway)",
                CONNECTION_TYPE_SERIAL: "USB / Serial dongle",
            }
        ),
    }
)

STEP_TCP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PASSWORD): str,
    }
)

STEP_SERIAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL_PORT): str,
        vol.Optional(CONF_PASSWORD): str,
    }
)


class OpenWebNetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenWebNet."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection_type: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: Choose connection type (TCP or Serial)."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            if self._connection_type == CONNECTION_TYPE_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_CONNECTION_TYPE_SCHEMA,
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2a: TCP gateway details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            password = user_input.get(CONF_PASSWORD)

            await self.async_set_unique_id(f"tcp:{host}:{port}")
            self._abort_if_unique_id_configured()

            gateway = OpenWebNetGateway(host=host, port=port, password=password)
            success = await gateway.test_connection()

            if success:
                return self.async_create_entry(
                    title=f"OpenWebNet ({host})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_TCP,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_PASSWORD: password,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="tcp",
            data_schema=STEP_TCP_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: Serial/USB gateway details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial_port = user_input[CONF_SERIAL_PORT]
            password = user_input.get(CONF_PASSWORD)

            await self.async_set_unique_id(f"serial:{serial_port}")
            self._abort_if_unique_id_configured()

            gateway = OpenWebNetGateway(
                serial_port=serial_port, password=password
            )
            success = await gateway.test_connection()

            if success:
                return self.async_create_entry(
                    title=f"OpenWebNet ({serial_port})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                        CONF_SERIAL_PORT: serial_port,
                        CONF_PASSWORD: password,
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="serial",
            data_schema=STEP_SERIAL_DATA_SCHEMA,
            errors=errors,
        )
