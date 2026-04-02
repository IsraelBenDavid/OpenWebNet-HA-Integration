"""Async TCP and serial transport for OpenWebNet frames.

Handles raw byte-level I/O, frame extraction from the stream, and
write serialisation via an asyncio lock.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from .frame import OpenWebNetFrame, extract_frames

_LOGGER = logging.getLogger(__name__)

# Read buffer size
_BUFSIZE = 4096

# Default timeouts (seconds)
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 15.0


class OpenWebNetConnection:
    """Manages a single TCP (or serial-over-TCP) connection to an OWN gateway."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._buffer = ""
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._writer is not None

    async def connect(self) -> None:
        """Open the TCP connection to the gateway."""
        _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.connect_timeout,
        )
        # Disable Nagle's algorithm for low-latency frame exchange
        transport = self._writer.transport
        sock = transport.get_extra_info("socket")
        if sock is not None:
            import socket
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._connected = True
        self._buffer = ""
        _LOGGER.info("Connected to %s:%s", self.host, self.port)

    async def disconnect(self) -> None:
        """Close the connection."""
        self._connected = False
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            self._writer = None
            self._reader = None
        _LOGGER.debug("Disconnected from %s:%s", self.host, self.port)

    async def send(self, frame: str) -> None:
        """Send a raw frame string to the gateway."""
        if not self.connected:
            raise ConnectionError("Not connected to gateway")
        async with self._write_lock:
            assert self._writer is not None
            _LOGGER.debug("TX \u2192 %s", frame)
            self._writer.write(frame.encode("ascii"))
            await self._writer.drain()

    _SENTINEL = object()

    async def read_frame(self, timeout: float | None = _SENTINEL) -> OpenWebNetFrame:
        """Read the next complete frame from the stream.

        Pass timeout=None to block indefinitely (for event sessions).
        Omit timeout to use the default read_timeout.
        """
        if timeout is self._SENTINEL:
            timeout = self.read_timeout

        while True:
            # Try to extract a frame from the buffer first
            frames = extract_frames(self._buffer)
            if frames:
                raw = frames[0]
                idx = self._buffer.find(raw)
                self._buffer = self._buffer[idx + len(raw) :]
                frame = OpenWebNetFrame(raw)
                _LOGGER.debug("RX \u2190 %s", frame)
                return frame

            # Need more data
            assert self._reader is not None
            try:
                if timeout is None:
                    data = await self._reader.read(_BUFSIZE)
                else:
                    data = await asyncio.wait_for(
                        self._reader.read(_BUFSIZE), timeout=timeout
                    )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Timed out waiting for frame after {timeout}s"
                ) from None

            if not data:
                self._connected = False
                raise ConnectionError("Connection closed by gateway")

            self._buffer += data.decode("ascii", errors="replace")

    async def read_frames(self) -> AsyncIterator[OpenWebNetFrame]:
        """Continuously yield frames from the stream.

        Suitable for event-listening loops. Raises ConnectionError when
        the remote end closes the socket.
        """
        while self.connected:
            try:
                frame = await self.read_frame(timeout=None)
                yield frame
            except (ConnectionError, TimeoutError):
                self._connected = False
                raise
