"""OpenWebNet integration for Home Assistant.

Connects directly to a BTicino/Legrand OpenWebNet gateway over TCP
or USB serial, discovers devices on the bus, and maps them to native
HA entities.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_SERIAL_PORT,
    CONNECTION_TYPE_SERIAL,
    DOMAIN,
)
from .openwebnet import OpenWebNetGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH, Platform.COVER]

type OpenWebNetConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: OpenWebNetConfigEntry) -> bool:
    """Set up OpenWebNet from a config entry."""
    conn_type = entry.data.get(CONF_CONNECTION_TYPE, "tcp")
    password = entry.data.get(CONF_PASSWORD)

    if conn_type == CONNECTION_TYPE_SERIAL:
        serial_port = entry.data[CONF_SERIAL_PORT]
        gateway = OpenWebNetGateway(serial_port=serial_port, password=password)
    else:
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        gateway = OpenWebNetGateway(host=host, port=port, password=password)

    try:
        await gateway.connect()
    except Exception:
        _LOGGER.exception("Failed to connect to OpenWebNet gateway")
        return False

    # Run device discovery
    try:
        await gateway.discover_devices()
    except Exception:
        _LOGGER.warning("Device discovery failed \u2014 continuing with manual entities", exc_info=True)

    # Start the event listener for real-time state updates
    try:
        await gateway.start_event_listener()
    except Exception:
        _LOGGER.warning("Failed to start event listener", exc_info=True)

    # Store the gateway instance for platforms to use
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = gateway

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenWebNetConfigEntry) -> bool:
    """Unload an OpenWebNet config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        gateway: OpenWebNetGateway = hass.data[DOMAIN].pop(entry.entry_id)
        await gateway.disconnect()

    return unload_ok
