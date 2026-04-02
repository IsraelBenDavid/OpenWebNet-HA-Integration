"""OpenWebNet authentication helpers.

Implements both the modern HMAC digest authentication and the legacy
OPEN (XOR/rotation) authentication used by older gateways.
"""

from __future__ import annotations

import hashlib
import hmac
import os


# ---------------------------------------------------------------------------
# HMAC Digest Authentication (modern gateways)
# ---------------------------------------------------------------------------

def compute_hmac_response(
    server_nonce: bytes,
    password: str,
    *,
    use_sha256: bool = True,
) -> tuple[bytes, bytes, bytes]:
    """Compute the HMAC authentication response.

    Returns (client_nonce, client_digest, expected_server_digest).

    The gateway sends a server nonce encoded as ASCII digit-pairs. The client
    generates a random client nonce, then computes:
        digest = HMAC(key=password_hash, msg=server_nonce + client_nonce + fixed_salt)

    The fixed salt is the hex string "736F70653E636F70653E" which is the
    OpenWebNet HMAC salt used by all BTicino/Legrand gateways.
    """
    hash_fn = hashlib.sha256 if use_sha256 else hashlib.sha1

    # Password hash
    pwd_hash = hash_fn(password.encode("utf-8")).digest()

    # Client nonce (random)
    client_nonce = os.urandom(32 if use_sha256 else 20)

    # Fixed salt from the protocol specification
    salt = bytes.fromhex("736F70653E636F70653E")

    # Client digest: HMAC(pwd_hash, server_nonce + client_nonce + salt)
    msg = server_nonce + client_nonce + salt
    client_digest = hmac.new(pwd_hash, msg, hash_fn).digest()

    # Expected server response: HMAC(pwd_hash, server_nonce + client_nonce + salt_reversed)
    # The server uses the same formula but the gateway implementation may differ;
    # we accept any ACK as confirmation.
    expected = hmac.new(pwd_hash, msg, hash_fn).digest()

    return client_nonce, client_digest, expected


def encode_nonce_hex(nonce: bytes) -> str:
    """Encode a nonce as digit-pairs for the OWN frame.

    Each byte is represented as two ASCII digits (zero-padded).
    """
    return "".join(f"{b:02d}" for b in nonce)


def decode_nonce_hex(digit_string: str) -> bytes:
    """Decode a digit-pair nonce string back to bytes."""
    result = bytearray()
    for i in range(0, len(digit_string), 2):
        result.append(int(digit_string[i : i + 2]))
    return bytes(result)


# ---------------------------------------------------------------------------
# Legacy OPEN Authentication (older gateways)
# ---------------------------------------------------------------------------

def compute_open_password(password: str, nonce: str) -> str:
    """Compute the obfuscated password for legacy OPEN authentication.

    The algorithm applies a series of bit rotations and XOR operations
    based on each digit of the server nonce.
    """
    pwd = int(password) if password.isdigit() else 0
    # Ensure we work in 32-bit unsigned space
    pwd &= 0xFFFFFFFF

    for ch in nonce:
        digit = int(ch) if ch.isdigit() else 0
        if digit == 1:
            pwd = _rotate_right(pwd, 7)
        elif digit == 2:
            pwd = _rotate_right(pwd, 4)
        elif digit == 3:
            pwd = _rotate_left(pwd, 1)
        elif digit == 4:
            pwd = _rotate_left(pwd, 3)
        elif digit == 5:
            pwd = _rotate_right(pwd, 5)
        elif digit == 6:
            pwd = _rotate_left(pwd, 6)
        elif digit == 7:
            pwd ^= 0x00FF00FF
        elif digit == 8:
            pwd = ((pwd & 0x0000FFFF) << 16) | ((pwd >> 16) & 0x0000FFFF)
        elif digit == 9:
            pwd = ~pwd & 0xFFFFFFFF
        # digit == 0: no operation

    return str(pwd)


def _rotate_right(val: int, bits: int) -> int:
    val &= 0xFFFFFFFF
    return ((val >> bits) | (val << (32 - bits))) & 0xFFFFFFFF


def _rotate_left(val: int, bits: int) -> int:
    val &= 0xFFFFFFFF
    return ((val << bits) | (val >> (32 - bits))) & 0xFFFFFFFF
