"""Facade over cross-cutting utilities: HTTP, validation, time, emoji, images/fonts.

Kept deliberately small and dependency-light so cogs only need `bot.toolkit`
instead of importing aiohttp/regex/etc. directly.
"""
from __future__ import annotations

import asyncio
import random
import re
import unicodedata
from traceback import format_exception
from typing import TYPE_CHECKING, Any, Literal

import aiohttp
import regex as reg

from bcommie import timeparse
from bcommie.interpolation.interpolator import InterpolationEngine
from bcommie.logging_setup import get_logger
from bcommie.managers.images import ImagesManager
from bcommie.managers.typeface import TypefaceManager
from bcommie.placeholders import PlaceholderManager

if TYPE_CHECKING:
    from bcommie.kernel.bot import CommieBot

logger = get_logger(__name__)

HEX_REGEX = re.compile(r"^#?([A-F0-9]{6}|[A-F0-9]{3})$", re.IGNORECASE)
URL_REGEX = re.compile(r"^https?://\S+$")


class ToolKit:
    """Shared services instantiated once and attached to the bot as `bot.toolkit`."""

    def __init__(
        self, bot: CommieBot, images_path: str = "./assets/images", fonts_path: str = "./assets/fonts"
    ) -> None:
        self.bot = bot
        self.images = ImagesManager(path=images_path, toolkit=self)
        self.fonts = TypefaceManager(path=fonts_path)
        self.placeholders = PlaceholderManager()
        self.interpolation = InterpolationEngine(self.placeholders)
        self.http: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(3)
        self._delay = 0.25

    async def setup(self) -> None:
        """Open the shared HTTP session. Call once during bot startup."""
        if self.http is None or self.http.closed:
            self.http = aiohttp.ClientSession()

    async def close(self) -> None:
        """Close the shared HTTP session. Call once during bot shutdown."""
        if self.http and not self.http.closed:
            await self.http.close()

    # -- HTTP ---------------------------------------------------------------

    async def request(
        self,
        *,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET",
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, Any] | None = None,
        extract: Literal["json", "text", "bytes"] = "json",
    ) -> Any:
        """Rate-limited outbound HTTP call (max 3 concurrent, 250ms spacing)."""
        assert self.http is not None, "ToolKit.setup() must be called first"
        await self._semaphore.acquire()
        try:
            if self._delay:
                await asyncio.sleep(self._delay)
            async with self.http.request(method, url, params=params, json=json, data=data, headers=headers) as res:
                if res.status not in (200, 201):
                    logger.warning("http_request_non_2xx", url=url, status=res.status)
                    return None
                if extract == "json":
                    return await res.json()
                if extract == "bytes":
                    return await res.read()
                return await res.text()
        finally:
            self._semaphore.release()

    # -- text / validation --------------------------------------------------

    def is_hex(self, text: str) -> bool:
        """True if `text` is a valid 3- or 6-digit hex color, with or without '#'."""
        return bool(HEX_REGEX.match(text))

    def is_url(self, text: str) -> bool:
        """True if `text` looks like an http(s) URL."""
        return bool(URL_REGEX.match(text))

    def cut(self, text: str, max_len: int) -> str:
        """Truncate `text` to `max_len`, appending '...' if it was cut."""
        return text[:max_len] + "..." if len(text) > max_len else text

    def normalize(self, name: str) -> str:
        """Slugify: lowercase, strip accents, spaces -> underscores, ASCII only."""
        name = unicodedata.normalize("NFD", name.lower().strip())
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")
        name = re.sub(r"\s+", "_", name)
        name = re.sub(r"[^a-z0-9_-]", "", name)
        name = re.sub(r"[_-]+", "_", name)
        return name.strip("_")

    # -- time -----------------------------------------------------------------

    def parse_ms(self, ms: int) -> str:
        """Format milliseconds as 'XhYmZs'."""
        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def parse_time(self, data: str | int, long: bool = False) -> float | str | None:
        """Parse a duration string to ms, or format an ms value to text (see timeparse.py)."""
        return timeparse.load(data, long=long)

    # -- random -----------------------------------------------------------------

    def choice(self, arr: list[Any], amount: int = 1) -> list[Any]:
        """Random sample of `amount` items (or the whole list if amount >= len)."""
        if amount >= len(arr):
            return arr
        return random.sample(arr, amount)

    # -- emoji ------------------------------------------------------------------

    def parse_emoji(self, emoji: str, allow: Literal["unicode", "custom", "both"] = "both") -> str | None:
        """Validate an emoji string, restricting to unicode/custom/either."""
        if not emoji:
            return None
        is_unicode = bool(reg.match(r"\p{Extended_Pictographic}", emoji))
        is_custom = bool(reg.match(r"<a?:\w+:\d+>", emoji))
        if allow == "unicode":
            return emoji if is_unicode else None
        if allow == "custom":
            return emoji if is_custom else None
        return emoji if (is_unicode or is_custom) else None

    # -- debug ------------------------------------------------------------------

    def format_exception(self, exc: BaseException) -> str:
        """Format a full traceback as a string, for logs/owner DMs."""
        return "".join(format_exception(exc, exc, exc.__traceback__))
