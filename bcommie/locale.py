"""Dotted-key access into a loaded locale JSON document, with .format() interpolation."""
from __future__ import annotations

from typing import Any


class Locale:
    """Read-only view over one language's translation strings."""

    def __init__(self, data: dict[str, Any], lang: str) -> None:
        self._data = data
        self.lang = lang

    def get(self, key: str, **placeholders: Any) -> str:
        """Resolve a dotted key (e.g. 'moderation.banned') to its translated string.

        Returns `[key]` if missing, so untranslated strings are visibly obvious
        rather than silently blank.
        """
        value: Any = self._data
        for part in key.split("."):
            if not isinstance(value, dict):
                return f"[{key}]"
            value = value.get(part)
            if value is None:
                return f"[{key}]"
        if not isinstance(value, str):
            return f"[{key}]"
        if placeholders:
            try:
                value = value.format(**placeholders)
            except KeyError:
                return f"[{key}]"
        return value
