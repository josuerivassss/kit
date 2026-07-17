"""Local image asset cache plus PIL-based rendering helpers used by the Fun cog.

Design notes (unchanged from v1, still valid):
- Lazy-loaded LRU cache bounded by both entry count and estimated memory,
  so serving image-edit commands never grows the process unbounded.
- Emoji-aware text rendering fetches glyphs from the Twemoji CDN via
  ToolKit's rate-limited HTTP client and caches them in memory.
"""
from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

import emoji
import numpy as np
from discord import File
from PIL import Image, ImageDraw, ImageFont

from bcommie.logging_setup import get_logger

if TYPE_CHECKING:
    from bcommie.toolkit import ToolKit

logger = get_logger(__name__)


class ImagesManager:
    """Lazy, LRU-cached access to local image assets, plus PIL rendering helpers."""

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    DEFAULT_MAX_CACHE_SIZE = 50
    DEFAULT_MAX_MEMORY_MB = 100
    EMOJI_CDN = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/"

    def __init__(
        self,
        path: str,
        max_cache_size: int = DEFAULT_MAX_CACHE_SIZE,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        preload: list[str] | None = None,
        toolkit: ToolKit | None = None,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_dir():
            raise ValueError(f"Invalid image directory: {path}")

        self.max_cache_size = max_cache_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.toolkit = toolkit

        self._index: dict[str, Path] = self._build_index()
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_memory = 0
        self._emoji_cache: dict[str, Image.Image] = {}
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

        for name in preload or []:
            try:
                self._load_to_cache(name)
            except KeyError:
                pass

    def _build_index(self) -> dict[str, Path]:
        return {
            f.stem.lower(): f for f in self.path.rglob("*") if f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        }

    def _estimate_memory(self, img: Image.Image) -> int:
        return img.width * img.height * len(img.getbands())

    def _load_to_cache(self, name: str) -> Image.Image:
        key = name.lower()
        if key not in self._index:
            raise KeyError(f"Image '{name}' not found")
        with Image.open(self._index[key]) as img:
            loaded = img.convert("RGBA")
        img_size = self._estimate_memory(loaded)
        while len(self._cache) >= self.max_cache_size or self._cache_memory + img_size > self.max_memory_bytes:
            if not self._cache:
                break
            self._evict_lru()
        self._cache[key] = loaded
        self._cache_memory += img_size
        return loaded

    def _evict_lru(self) -> None:
        if not self._cache:
            return
        _, oldest_img = self._cache.popitem(last=False)
        self._cache_memory -= self._estimate_memory(oldest_img)
        self._stats["evictions"] += 1

    async def _get_emoji_image(self, emoji_char: str, size: int = 72) -> Image.Image | None:
        """Fetch (and cache) an emoji glyph image from the Twemoji CDN."""
        cache_key = f"{emoji_char}_{size}"
        if cache_key in self._emoji_cache:
            return self._emoji_cache[cache_key].copy()
        if not self.toolkit:
            return None
        try:
            codepoint = "-".join(f"{ord(c):x}" for c in emoji_char)
            image_bytes = await self.toolkit.request(
                method="GET", url=f"{self.EMOJI_CDN}{codepoint}.png", extract="bytes"
            )
            if image_bytes:
                emoji_img = Image.open(BytesIO(image_bytes)).convert("RGBA")
                emoji_img = emoji_img.resize((size, size), Image.Resampling.LANCZOS)
                self._emoji_cache[cache_key] = emoji_img
                return emoji_img.copy()
        except Exception:
            logger.warning("emoji_fetch_failed", emoji=emoji_char)
        return None

    def _parse_text_with_emojis(self, text: str) -> list[tuple[str, bool]]:
        """Split text into (segment, is_emoji) runs."""
        segments: list[tuple[str, bool]] = []
        buffer = ""
        for char in text:
            if char in emoji.EMOJI_DATA:
                if buffer:
                    segments.append((buffer, False))
                    buffer = ""
                segments.append((char, True))
            else:
                buffer += char
        if buffer:
            segments.append((buffer, False))
        return segments

    # -- core access ------------------------------------------------------

    def fetch(self, name: str) -> Image.Image:
        """Return a copy of a cached/loaded image asset (RGBA). Raises KeyError if missing."""
        key = name.lower()
        if key in self._cache:
            self._stats["hits"] += 1
            self._cache.move_to_end(key)
            return self._cache[key].copy()
        self._stats["misses"] += 1
        return self._load_to_cache(key).copy()

    def list(self) -> list[str]:
        """All indexed image asset names."""
        return list(self._index)

    def has_image(self, name: str) -> bool:
        """True if an asset with this name is indexed (without loading it)."""
        return name.lower() in self._index

    def warm_cache(self, names: list[str]) -> None:
        """Eagerly load several assets into cache."""
        for name in names:
            try:
                if name.lower() not in self._cache:
                    self._load_to_cache(name)
            except KeyError:
                pass

    def flush_cache(self) -> None:
        """Clear the entire in-memory image cache."""
        self._cache.clear()
        self._cache_memory = 0
        self._stats["evictions"] = 0
        self._emoji_cache.clear()

    def get_cache_stats(self) -> dict[str, Any]:
        """Cache hit rate, size, and memory footprint (used by the /info command)."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total else 0
        return {
            **self._stats,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
            "cache_memory_mb": f"{self._cache_memory / (1024 * 1024):.2f}",
            "indexed_images": len(self._index),
            "emoji_cache_size": len(self._emoji_cache),
        }

    # -- conversion ---------------------------------------------------------

    def from_bytes(self, data: bytes | bytearray | BytesIO, mode: str = "RGBA") -> Image.Image:
        """Decode raw bytes into a PIL image."""
        buffer = BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        try:
            with Image.open(buffer) as img:
                return img.convert(mode)
        except Exception as exc:
            raise ValueError("Invalid image data") from exc

    def to_bytes(self, image: Image.Image, format: str = "PNG", quality: int = 95, optimize: bool = False, **kwargs: Any) -> bytes:
        """Encode a PIL image to bytes in the given format."""
        buffer = BytesIO()
        params = dict(kwargs)
        if format.upper() in ("JPEG", "JPG"):
            params.setdefault("quality", quality)
            params.setdefault("optimize", optimize)
        elif format.upper() == "WEBP":
            params.setdefault("quality", quality)
        elif format.upper() == "PNG":
            params.setdefault("optimize", optimize)
        image.save(buffer, format=format.upper(), **params)
        buffer.seek(0)
        return buffer.getvalue()

    def to_file(self, image: Image.Image, filename: str, format: str = "PNG", **kwargs: Any) -> File:
        """Encode a PIL image directly into a discord.File ready to send."""
        return File(fp=BytesIO(self.to_bytes(image, format=format, **kwargs)), filename=filename)

    # -- masking --------------------------------------------------------------

    def mask_ellipse(self, image: Image.Image) -> Image.Image:
        """Apply a circular/elliptical alpha mask (e.g. round avatars)."""
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, *image.size), fill=255)
        image.putalpha(mask)
        return image

    def round_corners(self, image: Image.Image, radius: int = 10) -> Image.Image:
        """Apply rounded-rectangle alpha mask."""
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *image.size), radius, fill=255)
        image.putalpha(mask)
        return image

    # -- text rendering -------------------------------------------------------

    async def render_text(
        self,
        image: Image.Image,
        xy: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple[int, int, int, int] = (255, 255, 255, 255),
        spacing: int = 4,
        align: str = "left",
        emoji_scale: float = 1.0,
        stroke_width: int = 0,
        stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255),
        max_width: int | None = None,
    ) -> None:
        """Draw multi-line, emoji-aware text onto `image` in place."""
        draw = ImageDraw.Draw(image)
        x, y = xy
        emoji_size = int(font.size * emoji_scale)

        for line in text.split("\n"):
            segments = self._parse_text_with_emojis(line)
            line_width = sum(
                emoji_size + 2 if is_emoji else (font.getbbox(seg)[2] - font.getbbox(seg)[0])
                for seg, is_emoji in segments
            )
            if align == "center" and max_width:
                current_x = x + (max_width - line_width) // 2
            elif align == "right" and max_width:
                current_x = x + (max_width - line_width)
            else:
                current_x = x

            for segment, is_emoji in segments:
                if is_emoji:
                    emoji_img = await self._get_emoji_image(segment, emoji_size)
                    if emoji_img:
                        image.paste(emoji_img, (current_x, y + (font.size - emoji_size) // 2), emoji_img)
                        current_x += emoji_size + 2
                else:
                    draw.text(
                        (current_x, y), segment, font=font, fill=fill,
                        stroke_width=stroke_width, stroke_fill=stroke_fill,
                    )
                    bbox = font.getbbox(segment)
                    current_x += bbox[2] - bbox[0]
            y += font.size + spacing

    async def measure_text(
        self, font: ImageFont.FreeTypeFont, text: str, spacing: int = 4, emoji_scale: float = 1.0
    ) -> tuple[int, int]:
        """Measure the pixel (width, height) of emoji-aware multi-line text."""
        emoji_size = int(font.size * emoji_scale)
        max_width, total_height = 0, 0
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            segments = self._parse_text_with_emojis(line)
            line_width = sum(
                emoji_size + 2 if is_emoji else (font.getbbox(seg)[2] - font.getbbox(seg)[0])
                for seg, is_emoji in segments
            )
            max_width = max(max_width, line_width)
            total_height += font.size + (spacing if idx < len(lines) - 1 else 0)
        return max_width, total_height

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int, emoji_scale: float = 1.0) -> str:
        """Insert newlines so `text` fits within `max_width` pixels."""
        words = text.split(" ")
        lines: list[str] = []
        current: list[str] = []
        emoji_size = int(font.size * emoji_scale)

        for word in words:
            test_line = " ".join([*current, word])
            segments = self._parse_text_with_emojis(test_line)
            line_width = sum(
                emoji_size + 2 if is_emoji else (font.getbbox(seg)[2] - font.getbbox(seg)[0])
                for seg, is_emoji in segments
            )
            if line_width <= max_width:
                current.append(word)
            elif current:
                lines.append(" ".join(current))
                current = [word]
            else:
                lines.append(word)  # single word wider than max_width: emit anyway

        if current:
            lines.append(" ".join(current))
        return "\n".join(lines)

    def calculate_text_bbox(self, font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
        """Fast (no-emoji) bounding box for possibly multi-line text."""
        if "\n" not in text:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        max_width, total_height = 0, 0
        for line in text.split("\n"):
            bbox = font.getbbox(line)
            max_width = max(max_width, bbox[2] - bbox[0])
            total_height += bbox[3] - bbox[1]
        return max_width, total_height

    # -- color analysis -----------------------------------------------------

    def _kmeans_clustering(self, pixels: np.ndarray, k: int, max_iter: int = 100) -> np.ndarray:
        """Basic k-means over RGBA pixel samples (used for palette extraction)."""
        rng = np.random.default_rng()
        centroids = pixels[rng.choice(pixels.shape[0], size=k, replace=False)]
        for _ in range(max_iter):
            distances = np.sqrt(((pixels - centroids[:, np.newaxis]) ** 2).sum(axis=2))
            closest = np.argmin(distances, axis=0)
            new_centroids = np.array(
                [
                    pixels[closest == i].mean(axis=0) if np.any(closest == i) else centroids[i]
                    for i in range(centroids.shape[0])
                ]
            )
            if np.all(centroids == new_centroids):
                break
            centroids = new_centroids
        return centroids

    def extract_palette(self, image: Image.Image, n_colors: int = 2) -> list[list[int]]:
        """Extract `n_colors` dominant colors, ranked by prevalence and distinctiveness."""
        downsampled = image.resize((image.size[0] // 2, image.size[1] // 2)).convert("RGBA")
        pixels = np.array(downsampled).reshape(-1, 4)
        dominant = self._kmeans_clustering(pixels, n_colors)
        closest = np.argmin(np.sqrt(((pixels - dominant[:, np.newaxis]) ** 2).sum(axis=2)), axis=0)
        counts = np.bincount(closest, minlength=dominant.shape[0])
        pairwise = np.sqrt(((dominant[:, np.newaxis, :] - dominant[np.newaxis, :, :]) ** 2).sum(axis=2))
        scores = counts * (1 / (1 + pairwise.sum(axis=0)))
        order = np.argsort(scores)[::-1]
        return [list(map(int, c)) for c in dominant[order][:n_colors]]

    # -- gradients ------------------------------------------------------------

    def fill_gradient(
        self,
        base: Image.Image,
        bbox: tuple[tuple[int, int], tuple[int, int]],
        stops: list[tuple[int, int, int, int]],
        orientation: str = "vertical",
    ) -> None:
        """Paint a linear gradient (>=2 RGBA stops) into `bbox` on `base`."""
        if orientation not in ("vertical", "horizontal"):
            raise ValueError("orientation must be 'vertical' or 'horizontal'")
        if len(stops) < 2:
            raise ValueError("At least two color stops are required")

        (x0, y0), (width, height) = bbox
        steps = height if orientation == "vertical" else width
        gradient = []
        for i in range(steps):
            segment = int(i / steps * (len(stops) - 1))
            r1, g1, b1, _ = stops[segment]
            r2, g2, b2, _ = stops[segment + 1]
            ratio = (i / steps * len(stops)) - segment
            gradient.append((int(r1 * (1 - ratio) + r2 * ratio), int(g1 * (1 - ratio) + g2 * ratio), int(b1 * (1 - ratio) + b2 * ratio)))

        draw = ImageDraw.Draw(base)
        for i, color in enumerate(gradient):
            if orientation == "vertical":
                draw.line((x0, y0 + i, x0 + width, y0 + i + 1), fill=color, width=1)
            else:
                draw.line((x0 + i, y0, x0 + i + 1, y0 + height), fill=color, width=1)
