"""OpenWebNet cover platform.

Maps OpenWebNet automation devices (WHO=2) to Home Assistant cover
entities with open/close/stop control.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
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
    """Set up OpenWebNet covers from discovered devices."""
    gateway: OpenWebNetGateway = hass.data[DOMAIN][entry.entry_id]

    entities: list[OpenWebNetCover] = []
    for dev in gateway.devices.values():
        if dev.device_type == "cover":
            entities.append(OpenWebNetCover(gateway, dev.where, dev.name))

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d OpenWebNet cover entities", len(entities))


class OpenWebNetCover(CoverEntity):
    """Representation of an OpenWebNet cover (shutter/blind)."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        gateway: OpenWebNetGateway,
        where: str,
        name: str,
    ) -> None:
        self._gateway = gateway
        self._where = where
        self._attr_name = name
        self._attr_unique_id = f"own_cover_{where}"
        self._attr_is_closed: bool | None = None
        self._moving: str | None = None  # "up", "down", or None

    async def async_added_to_hass(self) -> None:
        self._gateway.register_event_callback(self._handle_event)
        await self._async_refresh_state()

    async def async_will_remove_from_hass(self) -> None:
        self._gateway.unregister_event_callback(self._handle_event)

    async def _async_refresh_state(self) -> None:
        frame = await self._gateway.request_cover_status(self._where)
        if frame and frame.what is not None:
            self._update_from_what(frame.what)

    async def _handle_event(self, frame: OpenWebNetFrame) -> None:
        if frame.who != Who.AUTOMATION or frame.where != self._where:
            return
        if frame.what is not None:
            self._update_from_what(frame.what)
            self.async_write_ha_state()

    @callback
    def _update_from_what(self, what: str) -> None:
        if what == What.Automation.STOP:
            self._moving = None
        elif what == What.Automation.UP:
            self._moving = "up"
            self._attr_is_closed = False
        elif what == What.Automation.DOWN:
            self._moving = "down"
            self._attr_is_closed = True

    @property
    def is_opening(self) -> bool:
        return self._moving == "up"

    @property
    def is_closing(self) -> bool:
        return self._moving == "down"

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._gateway.cover_up(self._where)
        self._moving = "up"
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._gateway.cover_down(self._where)
        self._moving = "down"
        self._attr_is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._gateway.cover_stop(self._where)
        self._moving = None
        self.async_write_ha_state()
