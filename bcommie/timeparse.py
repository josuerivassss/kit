"""Small human-friendly duration parser/formatter (e.g. "1h30m" <-> 5400000 ms).

Kept as its own module (single responsibility) rather than bundled into
ToolKit, so it can be unit-tested and reused independently (e.g. by the
future dashboard API).
"""
from __future__ import annotations

import re

_UNITS_MS = {
    "ms": 1,
    "s": 1000,
    "m": 1000 * 60,
    "h": 1000 * 60 * 60,
    "d": 1000 * 60 * 60 * 24,
    "w": 1000 * 60 * 60 * 24 * 7,
    "mo": 1000 * 60 * 60 * 24 * 30,
    "y": 1000 * 60 * 60 * 24 * 365.25,
}
_UNIT_NAMES = {
    "ms": "milisecond",
    "s": "second",
    "m": "minute",
    "h": "hour",
    "d": "day",
    "w": "week",
    "mo": "month",
    "y": "year",
}
_DURATION_RE = re.compile(r"(\d+\.\d+|\d+)(ms|s|mo|m|h|d|w|y)", re.IGNORECASE)


def parse_duration(text: str) -> float | None:
    """Parse a compound duration string ("1h30m") into milliseconds."""
    matches = _DURATION_RE.findall(text)
    if not matches:
        return None
    return sum(float(amount) * _UNITS_MS[unit.lower()] for amount, unit in matches)


def ms_to_short(ms: float) -> str:
    """Format milliseconds as the largest matching short unit, e.g. '5m'."""
    magnitude = abs(ms)
    for unit in reversed(_UNITS_MS):
        if magnitude >= _UNITS_MS[unit]:
            return f"{round(ms / _UNITS_MS[unit])}{unit}"
    return "0ms"


def ms_to_long(ms: float) -> str:
    """Format milliseconds as a pluralized long unit, e.g. '5 minutes'."""
    magnitude = abs(ms)
    for unit in reversed(_UNITS_MS):
        scale = _UNITS_MS[unit]
        if magnitude >= scale:
            plural = "s" if magnitude >= scale * 1.5 else ""
            return f"{round(ms / scale)} {_UNIT_NAMES[unit]}{plural}"
    return "0 miliseconds"


def load(value: str | int | float, *, long: bool = False) -> float | str | None:
    """Parse a duration string to ms, or format a ms value to text."""
    if isinstance(value, str):
        return parse_duration(value)
    return ms_to_long(value) if long else ms_to_short(value)
