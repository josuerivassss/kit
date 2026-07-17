"""Loads and caches per-guild locale JSON files (locales/{lang}.json)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bcommie.locale import Locale


class LanguageManager:
    """Small bounded LRU-ish cache over parsed locale files (max 10 languages)."""

    MAX_CACHE = 10

    def __init__(self, locales_path: str | Path, default_language: str = "en") -> None:
        self.locales_path = Path(locales_path)
        self.default_language = default_language
        self._raw_cache: dict[str, dict[str, Any]] = {}
        self._locale_cache: dict[str, Locale] = {}

    def _load_language(self, lang: str) -> None:
        if lang in self._raw_cache:
            return
        path = self.locales_path / f"{lang}.json"
        if not path.exists():
            return
        if len(self._raw_cache) >= self.MAX_CACHE:
            oldest = next(iter(self._raw_cache))
            self._raw_cache.pop(oldest, None)
            self._locale_cache.pop(oldest, None)
        self._raw_cache[lang] = json.loads(path.read_text(encoding="utf-8"))

    def get_locale(self, lang: str) -> Locale:
        """Return the Locale for `lang`, falling back to `default_language`."""
        if lang in self._locale_cache:
            return self._locale_cache[lang]
        self._load_language(lang)
        data = self._raw_cache.get(lang)
        if data is None:
            lang = self.default_language
            self._load_language(lang)
            data = self._raw_cache[lang]
        locale = Locale(data, lang)
        self._locale_cache[lang] = locale
        return locale
