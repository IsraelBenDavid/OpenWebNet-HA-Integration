"""OpenWebNet protocol constants and command helpers.

Defines WHO categories, WHAT command codes, and convenience builders
for lighting, automation and temperature control.
"""

from __future__ import annotations

import enum

from .frame import (
    build_bus_command,
    build_dimension_request,
    build_status_request,
)


# ---------------------------------------------------------------------------
# WHO \u2014 device category
# ---------------------------------------------------------------------------

class Who(str, enum.Enum):
    """OpenWebNet WHO identifiers (device categories)."""

    LIGHTING = "1"
    AUTOMATION = "2"
    LOAD_CONTROL = "3"
    TEMPERATURE = "4"
    BURGLAR_ALARM = "5"
    DOOR_ENTRY = "6"
    MULTIMEDIA = "7"
    AUXILIARY = "9"
    GATEWAY = "13"
    CEN_COMMANDS = "15"
    SOUND_SYSTEM = "16"
    SCENARIO_PLUS = "25"
    ENERGY = "18"
    DIAGNOSTICS = "1000"
    AUTOMATION_DIAG = "1001"
    LIGHTING_DIAG = "1004"
    CEN_PLUS = "25"


# ---------------------------------------------------------------------------
# WHAT \u2014 command codes per category
# ---------------------------------------------------------------------------

class What:
    """Common WHAT codes grouped by WHO category."""

    class Lighting:
        OFF = "0"
        ON = "1"
        DIM_20 = "2"
        DIM_30 = "3"
        DIM_40 = "4"
        DIM_50 = "5"
        DIM_60 = "6"
        DIM_70 = "7"
        DIM_80 = "8"
        DIM_90 = "9"
        DIM_100 = "10"
        ON_TIMED_1MIN = "11"
        ON_TIMED_2MIN = "12"
        ON_TIMED_3MIN = "13"
        ON_TIMED_4MIN = "14"
        ON_TIMED_5MIN = "15"
        ON_TIMED_15MIN = "16"
        ON_TIMED_30SEC = "17"
        ON_TIMED_05SEC = "18"
        TOGGLE = "32"
        DIM_STOP = "38"

    class Automation:
        STOP = "0"
        UP = "1"
        DOWN = "2"

    class Temperature:
        """Dimension codes used with temperature WHO."""
        DIM_TEMPERATURE = "0"
        DIM_SET_POINT = "14"
        DIM_VALVE_STATUS = "19"
        DIM_ACTUATOR_STATUS = "20"

    class Gateway:
        """Management / gateway commands."""
        FIRMWARE_VERSION_DIM = "16"
        DATE_TIME_DIM = "22"


# ---------------------------------------------------------------------------
# Brightness mapping helpers
# ---------------------------------------------------------------------------

# Map percentage (0-100) to OWN dimming levels
_BRIGHTNESS_TO_WHAT: list[tuple[int, str]] = [
    (0, What.Lighting.OFF),
    (20, What.Lighting.DIM_20),
    (30, What.Lighting.DIM_30),
    (40, What.Lighting.DIM_40),
    (50, What.Lighting.DIM_50),
    (60, What.Lighting.DIM_60),
    (70, What.Lighting.DIM_70),
    (80, What.Lighting.DIM_80),
    (90, What.Lighting.DIM_90),
    (100, What.Lighting.DIM_100),
]

_WHAT_TO_BRIGHTNESS: dict[str, int] = {
    What.Lighting.OFF: 0,
    What.Lighting.ON: 100,
    What.Lighting.DIM_20: 20,
    What.Lighting.DIM_30: 30,
    What.Lighting.DIM_40: 40,
    What.Lighting.DIM_50: 50,
    What.Lighting.DIM_60: 60,
    What.Lighting.DIM_70: 70,
    What.Lighting.DIM_80: 80,
    What.Lighting.DIM_90: 90,
    What.Lighting.DIM_100: 100,
}


def brightness_to_what(pct: int) -> str:
    """Convert a brightness percentage (0-100) to the closest WHAT code."""
    if pct <= 0:
        return What.Lighting.OFF
    best = What.Lighting.DIM_100
    for threshold, code in _BRIGHTNESS_TO_WHAT:
        if pct <= threshold:
            return code
        best = code
    return best


def what_to_brightness(what: str) -> int:
    """Convert a lighting WHAT code to a brightness percentage."""
    return _WHAT_TO_BRIGHTNESS.get(what, 100 if what != What.Lighting.OFF else 0)


# ---------------------------------------------------------------------------
# High-level command builders
# ---------------------------------------------------------------------------

class OpenWebNetCommand:
    """Convenience builders that return raw frame strings."""

    # -- Lighting --
    @staticmethod
    def light_on(where: str) -> str:
        return build_bus_command(Who.LIGHTING, What.Lighting.ON, where)

    @staticmethod
    def light_off(where: str) -> str:
        return build_bus_command(Who.LIGHTING, What.Lighting.OFF, where)

    @staticmethod
    def light_set_brightness(where: str, pct: int) -> str:
        return build_bus_command(Who.LIGHTING, brightness_to_what(pct), where)

    @staticmethod
    def light_status(where: str) -> str:
        return build_status_request(Who.LIGHTING, where)

    @staticmethod
    def light_toggle(where: str) -> str:
        return build_bus_command(Who.LIGHTING, What.Lighting.TOGGLE, where)

    # -- Automation --
    @staticmethod
    def cover_up(where: str) -> str:
        return build_bus_command(Who.AUTOMATION, What.Automation.UP, where)

    @staticmethod
    def cover_down(where: str) -> str:
        return build_bus_command(Who.AUTOMATION, What.Automation.DOWN, where)

    @staticmethod
    def cover_stop(where: str) -> str:
        return build_bus_command(Who.AUTOMATION, What.Automation.STOP, where)

    @staticmethod
    def cover_status(where: str) -> str:
        return build_status_request(Who.AUTOMATION, where)

    # -- Temperature --
    @staticmethod
    def temperature_request(where: str) -> str:
        return build_dimension_request(
            Who.TEMPERATURE, where, What.Temperature.DIM_TEMPERATURE
        )

    # -- Gateway --
    @staticmethod
    def firmware_version() -> str:
        return build_dimension_request(
            Who.GATEWAY, "", What.Gateway.FIRMWARE_VERSION_DIM
        )
