"""High-level OpenWebNet gateway interface.

Provides a single entry point for connecting to an OWN gateway, sending
commands, querying status, listening for events, and discovering devices.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from .connection import OpenWebNetConnection
from .frame import FrameType, OpenWebNetFrame
from .protocol import OpenWebNetCommand, Who, What, what_to_brightness
from .session import CommandError, OpenWebNetSession, SessionType

_LOGGER = logging.getLogger(__name__)

# Addresses 0-99 covers the standard SCS area/point addressing
_SCAN_AREAS = range(0, 11)      # areas 0-10
_SCAN_POINTS = range(0, 16)     # light points 0-15 per area


@dataclass
class OWNDevice:
    """Represents a discovered OpenWebNet device."""

    who: str
    where: str
    what: str | None = None
    device_type: str = ""
    name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_id(self) -> str:
        return f"own_{self.who}_{self.where}"


EventCallback = Callable[[OpenWebNetFrame], Coroutine[Any, Any, None]]


class OpenWebNetGateway:
    """Manages command and event sessions to an OpenWebNet gateway."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password

        self._cmd_session: OpenWebNetSession | None = None
        self._evt_session: OpenWebNetSession | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._event_callbacks: list[EventCallback] = []
        self._reconnect_task: asyncio.Task[None] | None = None
        self._running = False
        self._cmd_lock = asyncio.Lock()
        self.devices: dict[str, OWNDevice] = {}

    @property
    def connected(self) -> bool:
        return (
            self._cmd_session is not None
            and self._cmd_session.connection.connected
        )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish command and event sessions."""
        await self._open_command_session()
        self._running = True
        _LOGGER.info("Gateway connected to %s:%s", self.host, self.port)

    async def _open_command_session(self) -> None:
        conn = OpenWebNetConnection(self.host, self.port)
        await conn.connect()
        session = OpenWebNetSession(conn, SessionType.COMMAND, password=self.password)
        await session.negotiate()
        self._cmd_session = session

    async def _open_event_session(self) -> None:
        conn = OpenWebNetConnection(self.host, self.port, read_timeout=None)
        await conn.connect()
        session = OpenWebNetSession(conn, SessionType.EVENT, password=self.password)
        await session.negotiate()
        self._evt_session = session

    async def disconnect(self) -> None:
        """Shut down all sessions and background tasks."""
        self._running = False
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._cmd_session:
            await self._cmd_session.close()
            self._cmd_session = None
        if self._evt_session:
            await self._evt_session.close()
            self._evt_session = None
        _LOGGER.info("Gateway disconnected")

    # ------------------------------------------------------------------
    # Test / handshake
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Test that we can connect and authenticate. Returns True on success."""
        try:
            conn = OpenWebNetConnection(self.host, self.port)
            await conn.connect()
            session = OpenWebNetSession(conn, SessionType.COMMAND, password=self.password)
            await session.negotiate()
            await session.close()
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Connection test failed", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def send_command(self, frame: str) -> list[OpenWebNetFrame]:
        """Send a command frame and return response frames."""
        async with self._cmd_lock:
            if not self.connected:
                await self._open_command_session()
            assert self._cmd_session is not None
            try:
                return await self._cmd_session.execute(frame)
            except (ConnectionError, TimeoutError):
                _LOGGER.warning("Command session lost, reconnecting\u2026")
                await self._try_reconnect_cmd()
                assert self._cmd_session is not None
                return await self._cmd_session.execute(frame)

    async def _try_reconnect_cmd(self) -> None:
        if self._cmd_session:
            try:
                await self._cmd_session.close()
            except Exception:  # noqa: BLE001
                pass
        await self._open_command_session()

    # ------------------------------------------------------------------
    # Convenience command wrappers
    # ------------------------------------------------------------------

    async def light_on(self, where: str) -> None:
        await self.send_command(OpenWebNetCommand.light_on(where))

    async def light_off(self, where: str) -> None:
        await self.send_command(OpenWebNetCommand.light_off(where))

    async def light_brightness(self, where: str, pct: int) -> None:
        await self.send_command(OpenWebNetCommand.light_set_brightness(where, pct))

    async def cover_up(self, where: str) -> None:
        await self.send_command(OpenWebNetCommand.cover_up(where))

    async def cover_down(self, where: str) -> None:
        await self.send_command(OpenWebNetCommand.cover_down(where))

    async def cover_stop(self, where: str) -> None:
        await self.send_command(OpenWebNetCommand.cover_stop(where))

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    async def request_light_status(self, where: str) -> OpenWebNetFrame | None:
        """Query the current state of a light point."""
        try:
            frames = await self.send_command(OpenWebNetCommand.light_status(where))
            return frames[0] if frames else None
        except CommandError:
            return None

    async def request_cover_status(self, where: str) -> OpenWebNetFrame | None:
        try:
            frames = await self.send_command(OpenWebNetCommand.cover_status(where))
            return frames[0] if frames else None
        except CommandError:
            return None

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def discover_devices(self) -> dict[str, OWNDevice]:
        """Scan the bus for lights and automation devices.

        Sends status requests to standard area/point addresses and records
        any device that responds with data (not NACK).
        """
        _LOGGER.info("Starting device discovery scan\u2026")
        discovered: dict[str, OWNDevice] = {}

        for who, device_type in ((Who.LIGHTING, "light"), (Who.AUTOMATION, "cover")):
            for area in _SCAN_AREAS:
                for point in _SCAN_POINTS:
                    if area == 0 and point == 0:
                        continue  # 00 is a broadcast address
                    where = f"{area}{point}" if area < 10 else f"{area}{point}"
                    # Use short timeout \u2014 missing devices simply won't answer
                    try:
                        frames = await self.send_command(
                            f"*#{who}*{where}##"
                        )
                    except (CommandError, ConnectionError, TimeoutError):
                        continue

                    if frames:
                        dev = OWNDevice(
                            who=who,
                            where=where,
                            what=frames[0].what,
                            device_type=device_type,
                            name=f"{device_type.title()} {where}",
                        )
                        discovered[dev.unique_id] = dev
                        _LOGGER.debug("Discovered %s at %s", device_type, where)

        self.devices = discovered
        _LOGGER.info("Discovery complete: found %d devices", len(discovered))
        return discovered

    # ------------------------------------------------------------------
    # Event listener
    # ------------------------------------------------------------------

    def register_event_callback(self, callback: EventCallback) -> None:
        self._event_callbacks.append(callback)

    def unregister_event_callback(self, callback: EventCallback) -> None:
        self._event_callbacks.remove(callback)

    async def start_event_listener(self) -> None:
        """Open an event session and start the background listener task."""
        await self._open_event_session()
        self._event_task = asyncio.create_task(self._event_loop())

    async def _event_loop(self) -> None:
        """Background loop that reads event frames and dispatches callbacks."""
        backoff = 1
        while self._running:
            try:
                assert self._evt_session is not None
                async for frame in self._evt_session.connection.read_frames():
                    if frame.is_event:
                        for cb in self._event_callbacks:
                            try:
                                await cb(frame)
                            except Exception:  # noqa: BLE001
                                _LOGGER.exception("Error in event callback")
            except (ConnectionError, TimeoutError) as exc:
                if not self._running:
                    return
                _LOGGER.warning(
                    "Event session lost (%s), reconnecting in %ds\u2026", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                try:
                    await self._open_event_session()
                    backoff = 1
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("Event reconnect failed", exc_info=True)
            except asyncio.CancelledError:
                return
