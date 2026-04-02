"""OpenWebNet frame parser and builder.

Frame format: *field1*field2*field3...##
Fields are separated by '*', parameters within a field by '#'.
Special frames: ACK = *#*1##, NACK = *#*0##, BUSY_NACK = *#*6##
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field


class FrameType(enum.Enum):
    """Types of OpenWebNet frames."""

    ACK = "ack"
    NACK = "nack"
    BUSY_NACK = "busy_nack"
    BUS_COMMAND = "bus_command"
    STATUS_REQUEST = "status_request"
    DIMENSION_REQUEST = "dimension_request"
    DIMENSION_READ = "dimension_read"
    DIMENSION_SET = "dimension_set"
    UNKNOWN = "unknown"


# Well-known constant frames
ACK = "*#*1##"
NACK = "*#*0##"
BUSY_NACK = "*#*6##"

_FRAME_RE = re.compile(r"^\*.*##$")


@dataclass(frozen=True)
class OpenWebNetFrame:
    """Represents a parsed OpenWebNet frame."""

    raw: str
    frame_type: FrameType = field(init=False)
    who: str | None = field(init=False)
    what: str | None = field(init=False)
    where: str | None = field(init=False)
    dimension: str | None = field(init=False)
    values: list[str] = field(init=False)

    def __post_init__(self) -> None:
        ft, who, what, where, dim, vals = _parse(self.raw)
        object.__setattr__(self, "frame_type", ft)
        object.__setattr__(self, "who", who)
        object.__setattr__(self, "what", what)
        object.__setattr__(self, "where", where)
        object.__setattr__(self, "dimension", dim)
        object.__setattr__(self, "values", vals)

    @property
    def is_ack(self) -> bool:
        return self.frame_type is FrameType.ACK

    @property
    def is_nack(self) -> bool:
        return self.frame_type in (FrameType.NACK, FrameType.BUSY_NACK)

    @property
    def is_event(self) -> bool:
        return self.frame_type is FrameType.BUS_COMMAND

    def __str__(self) -> str:
        return self.raw


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def build_bus_command(who: str, what: str, where: str) -> str:
    """Build a BUS_COMMAND frame: *WHO*WHAT*WHERE##"""
    return f"*{who}*{what}*{where}##"


def build_status_request(who: str, where: str) -> str:
    """Build a STATUS_REQUEST frame: *#WHO*WHERE##"""
    return f"*#{who}*{where}##"


def build_dimension_request(who: str, where: str, dimension: str) -> str:
    """Build a DIMENSION_REQUEST frame: *#WHO*WHERE*#DIM##"""
    return f"*#{who}*{where}*#{dimension}##"


def build_dimension_set(who: str, where: str, dimension: str, *values: str) -> str:
    """Build a DIMENSION_SET frame: *#WHO*WHERE*#DIM*VAL1*VAL2...##"""
    val_part = "".join(f"*{v}" for v in values)
    return f"*#{who}*{where}*#{dimension}{val_part}##"


# ---------------------------------------------------------------------------
# Parser internals
# ---------------------------------------------------------------------------

def _parse(raw: str) -> tuple[FrameType, str | None, str | None, str | None, str | None, list[str]]:
    """Parse a raw frame string into its components."""
    if raw == ACK:
        return FrameType.ACK, None, None, None, None, []
    if raw == NACK:
        return FrameType.NACK, None, None, None, None, []
    if raw == BUSY_NACK:
        return FrameType.BUSY_NACK, None, None, None, None, []

    if not raw.startswith("*") or not raw.endswith("##"):
        return FrameType.UNKNOWN, None, None, None, None, []

    # Strip leading '*' and trailing '##'
    body = raw[1:-2]

    # Split on '*' delimiter — but handle '#' prefixed fields carefully.
    # We split the body by '*' keeping track of '#' prefixes.
    fields = _split_fields(body)

    if not fields:
        return FrameType.UNKNOWN, None, None, None, None, []

    # Determine frame type based on field patterns
    # Status request: starts with '#' prefix → *#WHO*WHERE##
    # Dimension frames: have '#' prefixed dimension field
    first = fields[0]

    if first.startswith("#"):
        # This is a status/dimension frame: *#WHO*...##
        who = first[1:]  # strip '#'
        if len(fields) < 2:
            return FrameType.STATUS_REQUEST, who, None, None, None, []

        where = fields[1]

        if len(fields) == 2:
            # *#WHO*WHERE## → status request
            return FrameType.STATUS_REQUEST, who, where, None, None, []

        dim_field = fields[2]
        remaining = fields[3:]

        if dim_field.startswith("#"):
            # *#WHO*WHERE*#DIM...## → dimension request or set
            dim = dim_field[1:]
            if remaining:
                # Dimension set or read with values
                return FrameType.DIMENSION_SET, who, None, where, dim, remaining
            return FrameType.DIMENSION_REQUEST, who, None, where, dim, []
        else:
            # *#WHO*WHERE*DIM*VAL...## → dimension read (no '#' prefix on dim)
            return FrameType.DIMENSION_READ, who, None, where, dim_field, remaining

    else:
        # Bus command: *WHO*WHAT*WHERE##
        who = first
        what = fields[1] if len(fields) > 1 else None
        where = fields[2] if len(fields) > 2 else None
        extra = fields[3:] if len(fields) > 3 else []
        return FrameType.BUS_COMMAND, who, what, where, None, extra


def _split_fields(body: str) -> list[str]:
    """Split the frame body by '*' delimiter.

    Handles the case where a field starts with '#' (e.g. *#1*...).
    The body has the leading '*' already stripped.
    """
    result: list[str] = []
    current = ""
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "*":
            result.append(current)
            current = ""
        else:
            current += ch
        i += 1
    if current:
        result.append(current)
    return result


def extract_frames(data: str) -> list[str]:
    """Extract all complete frames from a data buffer.

    Returns a list of raw frame strings (each starting with '*' and ending
    with '##'). Useful for splitting a stream chunk into individual frames.
    """
    frames: list[str] = []
    buf = data
    while buf:
        start = buf.find("*")
        if start == -1:
            break
        end = buf.find("##", start)
        if end == -1:
            break
        frame_str = buf[start : end + 2]
        frames.append(frame_str)
        buf = buf[end + 2 :]
    return frames
