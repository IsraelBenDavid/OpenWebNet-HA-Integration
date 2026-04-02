"""OpenWebNet switch platform.

Maps OpenWebNet lighting devices used as simple on/off actuators
to Home Assistant switch entities.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .openwebnet import OpenWebNetGateway, OpenWebNetFrame, Who, What

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWebNet switches.

    Currently, switches are registered manually via configuration or
    by users recategorising discovered lights. This platform is ready
    to accept entities added by future discovery enhancements.
    """
    # Switches share the lighting WHO but are used for non-dimmable loads.
    # For now we set up an empty list \u2014 users can add via customisation.
    # Future: detect non-dimmable actuators during discovery.
    gateway: OpenWebNetGateway = hass.data[DOMAIN][entry.entry_id]
    entities: list[OpenWebNetSwitch] = []

    # If any devices are explicitly marked as switches, add them
    for dev in gateway.devices.values():
        if dev.device_type == "switch":
            entities.append(OpenWebNetSwitch(gateway, dev.where, dev.name))

    if entities:
        async_add_entities(entities)


class OpenWebNetSwitch(SwitchEntity):
    """Representation of an OpenWebNet switch (on/off actuator)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        gateway: OpenWebNetGateway,
        where: str,
        name: str,
    ) -> None:
        self._gateway = gateway
        self._where = where
        self._attr_name = name
        self._attr_unique_id = f"own_switch_{where}"
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        self._gateway.register_event_callback(self._handle_event)
        frame = await self._gateway.request_light_status(self._where)
        if frame and frame.what is not None:
            self._attr_is_on = frame.what != What.Lighting.OFF

    async def async_will_remove_from_hass(self) -> None:
        self._gateway.unregister_event_callback(self._handle_event)

    async def _handle_event(self, frame: OpenWebNetFrame) -> None:
        if frame.who != Who.LIGHTING or frame.where != self._where:
            return
        if frame.what is not None:
            self._attr_is_on = frame.what != What.Lighting.OFF
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._gateway.light_on(self._where)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._gateway.light_off(self._where)
        self._attr_is_on = False
        self.async_write_ha_state()
