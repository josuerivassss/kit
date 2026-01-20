import aiohttp, random, re, regex as reg, asyncio, unicodedata
from typing import Any, Literal
from traceback import format_exception
from discord.ext import commands
from core.interpolation.interpolator import InterpolationEngine
from core.placeholders import PlaceholderManager
from core.managers.ImagesManager import ImagesManager
from core.managers.TypefaceManager import TypefaceManager

HEX_REGEX = re.compile(r'^#?([A-F0-9]{6}|[A-F0-9]{3})$', re.IGNORECASE)
URL_REGEX = re.compile(r'^https?:\/\/\S+$')

class ToolKit:
    def __init__(self, bot: commands.Bot, images_path: str = "./assets/images", fonts_path: str = "./assets/fonts"):
        self.bot = bot
        self.images = ImagesManager(path=images_path, toolkit=self)
        self.fonts = TypefaceManager(path=fonts_path)
        self.placeholders = PlaceholderManager()
        self.interpolation = InterpolationEngine(self.placeholders)
        self.http: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(3)
        self._delay: float = 0.25

    async def setup(self):
        if self.http is None or self.http.closed:
            self.http = aiohttp.ClientSession()

    # ========= HTTP =========
    async def _safe_request(self): # Acquire semaphore and apply delay
        await self._semaphore.acquire()
        if self._delay:
            await asyncio.sleep(self._delay)

    def _release(self):
        self._semaphore.release()

    async def request(
        self,
        *,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET",
        url: str,
        params: dict | None = None,
        json: dict | None = None,
        data: Any = None,
        headers: dict | None = None,
        extract: Literal["json", "text", "bytes"] = "json"
    ):
        await self._safe_request()
        try:
            async with self.http.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=headers
            ) as res:
                if res.status not in (200, 201):
                    return None
                if extract == "json":
                    return await res.json()
                if extract == "bytes":
                    return await res.read()
                return await res.text()
        finally:
            self._release()

    # ========= TEXT / VALIDATION =========
    def is_hex(self, text: str) -> bool:
        return bool(HEX_REGEX.match(text))

    def is_url(self, text: str) -> bool:
        return bool(URL_REGEX.match(text))

    def cut(self, text: str, max_len: int) -> str:
        return text[:max_len] + "..." if len(text) > max_len else text
    
    def normalize(self, name: str) -> str:
        name = name.lower().strip()
        name = unicodedata.normalize("NFD", name)
        name = "".join(c for c in name if unicodedata.category(c) != "Mn")
        name = re.sub(r"\s+", "_", name)
        name = re.sub(r"[^a-z0-9_-]", "", name)
        name = re.sub(r"[_-]+", "_", name)
        name = name.strip("_")
        return name

    # ========= TIME =========
    def parse_ms(self, ms: int) -> str:
        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m {seconds}s"
    
    def parse_time(self, str) -> int:
        time_units = {
            'd': 86400,
            'h': 3600,
            'm': 60,
            's': 1
        }
        total_seconds = 0
        matches = re.findall(r'(\d+)([dhms])', str)
        for value, unit in matches:
            if unit in time_units:
                total_seconds += int(value) * time_units[unit]
        return total_seconds

    # ========= RANDOM =========
    def choice(self, arr: list, amount: int = 1):
        if amount >= len(arr):
            return arr
        return random.sample(arr, amount)

    # ========= EMOJI =========
    def parse_emoji(
        self,
        emoji: str,
        allow: Literal["unicode", "custom", "both"] = "both"
    ):
        if not emoji:
            return None
        is_unicode = reg.match(r"\p{Extended_Pictographic}", emoji)
        is_custom = reg.match(r"<a?:\w+:\d+>", emoji)
        if allow == "unicode":
            return emoji if is_unicode else None
        if allow == "custom":
            return emoji if is_custom else None
        return emoji if is_unicode or is_custom else None

    # ========= DEBUG =========
    def format_exception(self, exc: Exception) -> str:
        return "".join(format_exception(exc, exc, exc.__traceback__))

    # ========= LIFECYCLE =========
    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()
