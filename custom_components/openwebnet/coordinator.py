"""Data update coordinator for OpenWebNet.

Provides availability tracking and a central event dispatcher so that
entity platforms don't need to manage their own reconnection logic.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .openwebnet import OpenWebNetFrame, OpenWebNetGateway

_LOGGER = logging.getLogger(__name__)

SIGNAL_OWN_EVENT = "openwebnet_event_{entry_id}"
SIGNAL_OWN_AVAILABILITY = "openwebnet_availability_{entry_id}"


class OpenWebNetCoordinator:
    """Thin wrapper around the gateway that dispatches events via HA signals."""

    def __init__(
        self, hass: HomeAssistant, gateway: OpenWebNetGateway, entry_id: str
    ) -> None:
        self.hass = hass
        self.gateway = gateway
        self.entry_id = entry_id
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    async def start(self) -> None:
        """Register event callback and mark available."""
        self.gateway.register_event_callback(self._on_event)
        self._available = True

    async def stop(self) -> None:
        self.gateway.unregister_event_callback(self._on_event)

    async def _on_event(self, frame: OpenWebNetFrame) -> None:
        """Relay bus events to HA dispatcher signals."""
        signal = SIGNAL_OWN_EVENT.format(entry_id=self.entry_id)
        async_dispatcher_send(self.hass, signal, frame)

    @callback
    def set_available(self, available: bool) -> None:
        if self._available != available:
            self._available = available
            signal = SIGNAL_OWN_AVAILABILITY.format(entry_id=self.entry_id)
            async_dispatcher_send(self.hass, signal, available)
