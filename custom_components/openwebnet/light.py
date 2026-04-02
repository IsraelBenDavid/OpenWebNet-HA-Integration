"""OpenWebNet light platform.

Maps OpenWebNet lighting devices (WHO=1) to Home Assistant light entities
with on/off and brightness control.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .openwebnet import OpenWebNetGateway, OpenWebNetFrame, Who, What, what_to_brightness

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OpenWebNet lights from discovered devices."""
    gateway: OpenWebNetGateway = hass.data[DOMAIN][entry.entry_id]

    entities: list[OpenWebNetLight] = []
    for dev in gateway.devices.values():
        if dev.device_type == "light":
            entities.append(OpenWebNetLight(gateway, dev.where, dev.name))

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d OpenWebNet light entities", len(entities))


class OpenWebNetLight(LightEntity):
    """Representation of an OpenWebNet light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        gateway: OpenWebNetGateway,
        where: str,
        name: str,
    ) -> None:
        self._gateway = gateway
        self._where = where
        self._attr_name = name
        self._attr_unique_id = f"own_light_{where}"
        self._attr_is_on = False
        self._attr_brightness: int = 0

    async def async_added_to_hass(self) -> None:
        """Register event callback and fetch initial state."""
        self._gateway.register_event_callback(self._handle_event)
        await self._async_refresh_state()

    async def async_will_remove_from_hass(self) -> None:
        self._gateway.unregister_event_callback(self._handle_event)

    async def _async_refresh_state(self) -> None:
        """Query the gateway for the current light state."""
        frame = await self._gateway.request_light_status(self._where)
        if frame and frame.what is not None:
            self._update_from_what(frame.what)

    async def _handle_event(self, frame: OpenWebNetFrame) -> None:
        """Process an event frame from the bus."""
        if frame.who != Who.LIGHTING or frame.where != self._where:
            return
        if frame.what is not None:
            self._update_from_what(frame.what)
            self.async_write_ha_state()

    @callback
    def _update_from_what(self, what: str) -> None:
        pct = what_to_brightness(what)
        self._attr_is_on = pct > 0
        self._attr_brightness = int(pct * 255 / 100)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            pct = int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            await self._gateway.light_brightness(self._where, pct)
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._attr_is_on = True
        else:
            await self._gateway.light_on(self._where)
            self._attr_is_on = True
            self._attr_brightness = 255
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._gateway.light_off(self._where)
        self._attr_is_on = False
        self._attr_brightness = 0
        self.async_write_ha_state()
