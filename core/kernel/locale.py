from typing import Any

class Locale:
    def __init__(self, data: dict[str, Any], lang: str):
        self._data = data
        self.lang = lang

    def get(self, key: str, **placeholders) -> str:
        """
        Get a localized string by key, applying placeholders if provided.
        """
        parts = key.split(".")
        value: Any = self._data

        for part in parts:
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
