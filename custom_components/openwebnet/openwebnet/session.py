"""OpenWebNet session negotiation and command execution.

A session wraps a Connection and handles the authentication handshake,
session-type negotiation, and command/response sequencing.
"""

from __future__ import annotations

import enum
import logging

from .auth import compute_hmac_response, compute_open_password, decode_nonce_hex, encode_nonce_hex
from .connection import OpenWebNetConnection
from .frame import ACK, NACK, FrameType, OpenWebNetFrame

_LOGGER = logging.getLogger(__name__)


class SessionType(enum.Enum):
    """OpenWebNet session types."""

    COMMAND = "9"
    EVENT = "1"


class AuthMethod(enum.Enum):
    SHA1 = 1
    SHA256 = 2


class OpenWebNetSession:
    """Manages a negotiated session on top of a raw connection.

    Typical lifecycle:
        session = OpenWebNetSession(connection, SessionType.COMMAND, password="12345")
        await session.negotiate()
        response = await session.execute("*1*1*11##")
        ...
    """

    def __init__(
        self,
        connection: OpenWebNetConnection,
        session_type: SessionType,
        *,
        password: str | None = None,
    ) -> None:
        self.connection = connection
        self.session_type = session_type
        self.password = password
        self._negotiated = False

    @property
    def negotiated(self) -> bool:
        return self._negotiated

    async def negotiate(self) -> None:
        """Perform the session handshake including authentication."""
        conn = self.connection

        # Step 1: Read the initial frame from the gateway
        initial = await conn.read_frame(timeout=10.0)

        if initial.is_ack:
            # Gateway immediately ACKed \u2014 either whitelisted or open gateway.
            # Now request our session type.
            await conn.send(f"*99*{self.session_type.value}##")
            resp = await conn.read_frame(timeout=10.0)

            if resp.is_ack:
                # No authentication required
                self._negotiated = True
                _LOGGER.info("Session negotiated (no auth, type=%s)", self.session_type.value)
                return

            if resp.raw.startswith("*98*"):
                # Authentication required \u2014 gateway sent auth method
                await self._handle_auth(resp)
                return

            if resp.is_nack:
                raise ConnectionError("Gateway rejected session request")

            # Some gateways may send the nonce directly after session request
            if resp.raw.startswith("*#*"):
                await self._handle_legacy_auth(resp)
                return

            raise ConnectionError(f"Unexpected response during negotiation: {resp.raw}")

        # Gateway sent something else as first frame \u2014 could be auth challenge
        if initial.raw.startswith("*98*"):
            await self._handle_auth(initial)
            return

        if initial.raw.startswith("*#*") and initial.raw != NACK:
            # Legacy nonce
            await self._handle_legacy_auth(initial)
            return

        if initial.is_nack:
            raise ConnectionError("Gateway sent NACK on connect")

        raise ConnectionError(f"Unexpected initial frame: {initial.raw}")

    async def _handle_auth(self, auth_frame: OpenWebNetFrame) -> None:
        """Handle HMAC digest authentication."""
        if not self.password:
            raise ConnectionError("Authentication required but no password provided")

        # Parse auth method from *98*METHOD##
        method_str = auth_frame.what
        try:
            method = AuthMethod(int(method_str)) if method_str else AuthMethod.SHA256
        except ValueError:
            method = AuthMethod.SHA256

        use_sha256 = method is AuthMethod.SHA256
        conn = self.connection

        # ACK the auth method
        await conn.send(ACK)

        # Read server nonce: *#*NONCE##
        nonce_frame = await conn.read_frame(timeout=10.0)
        nonce_body = nonce_frame.raw[3:-2]  # strip '*#*' and '##'

        server_nonce = decode_nonce_hex(nonce_body)

        client_nonce, client_digest, _ = compute_hmac_response(
            server_nonce, self.password, use_sha256=use_sha256
        )

        # Send client response: *#CLIENT_NONCE*CLIENT_DIGEST##
        cn_str = encode_nonce_hex(client_nonce)
        cd_str = encode_nonce_hex(client_digest)
        await conn.send(f"*#{cn_str}*{cd_str}##")

        # Read server's digest response
        server_resp = await conn.read_frame(timeout=10.0)

        # Read final ACK
        if server_resp.is_ack:
            self._negotiated = True
            _LOGGER.info("HMAC authentication successful")
            return

        # Server may send its digest first, then ACK
        final = await conn.read_frame(timeout=10.0)
        if final.is_ack:
            self._negotiated = True
            _LOGGER.info("HMAC authentication successful")
            return

        raise ConnectionError("HMAC authentication failed")

    async def _handle_legacy_auth(self, nonce_frame: OpenWebNetFrame) -> None:
        """Handle legacy OPEN password authentication."""
        if not self.password:
            raise ConnectionError("Authentication required but no password provided")

        conn = self.connection

        # Nonce is in *#*NONCE## format
        nonce = nonce_frame.raw[3:-2]

        obfuscated = compute_open_password(self.password, nonce)
        await conn.send(f"*#{obfuscated}##")

        resp = await conn.read_frame(timeout=10.0)
        if resp.is_ack:
            self._negotiated = True
            _LOGGER.info("Legacy OPEN authentication successful")
            return

        raise ConnectionError("Legacy authentication failed \u2014 wrong password?")

    async def execute(self, frame: str) -> list[OpenWebNetFrame]:
        """Send a frame and collect all response frames until ACK/NACK.

        Returns the list of data frames received before the final
        acknowledgement. Raises ConnectionError on NACK.
        """
        if not self._negotiated:
            raise RuntimeError("Session not negotiated")

        conn = self.connection
        await conn.send(frame)

        responses: list[OpenWebNetFrame] = []
        while True:
            resp = await conn.read_frame()
            if resp.is_ack:
                return responses
            if resp.is_nack:
                raise CommandError(f"Command rejected by gateway: {frame}")
            responses.append(resp)

    async def close(self) -> None:
        """Close the underlying connection."""
        await self.connection.disconnect()


class CommandError(Exception):
    """Raised when a command is rejected (NACK) by the gateway."""
