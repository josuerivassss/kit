from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import Union, Any, Optional, Tuple, List, TYPE_CHECKING
from discord import File
from collections import OrderedDict
import numpy as np
import emoji
import re
from functools import lru_cache

if TYPE_CHECKING:
    from core.toolkit import ToolKit


class ImagesManager:
    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    DEFAULT_MAX_CACHE_SIZE = 50
    DEFAULT_MAX_MEMORY_MB = 100
    
    # Twemoji CDN for emoji images
    EMOJI_CDN = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/"

    def __init__(
        self, 
        path: str,
        max_cache_size: int = DEFAULT_MAX_CACHE_SIZE,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        preload: Optional[List[str]] = None,
        toolkit: Optional['ToolKit'] = None
    ):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ValueError(f"Invalid image directory: {path}")
        
        self.max_cache_size = max_cache_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.toolkit = toolkit  # Reference to ToolKit for HTTP requests
        
        # Lightweight index: only paths, not images
        self._index: dict[str, Path] = self._build_index()
        
        # LRU cache with OrderedDict
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_memory: int = 0
        
        # Emoji cache
        self._emoji_cache: dict[str, Image.Image] = {}
        
        # Metrics
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }
        
        # Preload critical images
        if preload:
            for name in preload:
                try:
                    self._load_to_cache(name)
                except KeyError:
                    pass

    def _build_index(self) -> dict[str, Path]:
        """Build lightweight index mapping image names to file paths"""
        index = {}
        for file in self.path.rglob("*"):
            if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            key = file.stem.lower()
            index[key] = file
        return index

    def _estimate_memory(self, img: Image.Image) -> int:
        """Estimate memory usage of an image in bytes"""
        return img.width * img.height * len(img.getbands())

    def _load_to_cache(self, name: str) -> Image.Image:
        """Load image from disk into cache"""
        key = name.lower()
        
        if key not in self._index:
            raise KeyError(f"Image '{name}' not found")
        
        path = self._index[key]
        
        with Image.open(path) as img:
            loaded = img.convert("RGBA")
        
        img_size = self._estimate_memory(loaded)
        
        # Evict if exceeds limits
        while (
            len(self._cache) >= self.max_cache_size or 
            self._cache_memory + img_size > self.max_memory_bytes
        ):
            if not self._cache:
                break
            self._evict_lru()
        
        self._cache[key] = loaded
        self._cache_memory += img_size
        
        return loaded

    def _evict_lru(self):
        """Remove least recently used image from cache"""
        if not self._cache:
            return
        
        oldest_key, oldest_img = self._cache.popitem(last=False)
        self._cache_memory -= self._estimate_memory(oldest_img)
        self._stats["evictions"] += 1

    async def _get_emoji_image(self, emoji_char: str, size: int = 72) -> Optional[Image.Image]:
        """
        Download and cache emoji image from Twemoji CDN
        
        Args:
            emoji_char: Single emoji character
            size: Emoji size in pixels
            
        Returns:
            PIL Image of emoji or None if download fails
        """
        # Check cache first
        cache_key = f"{emoji_char}_{size}"
        if cache_key in self._emoji_cache:
            return self._emoji_cache[cache_key].copy()
        
        # Require toolkit for HTTP requests
        if not self.toolkit:
            return None
        
        try:
            # Convert emoji to Unicode codepoint
            codepoint = "-".join(f"{ord(c):x}" for c in emoji_char)
            url = f"{self.EMOJI_CDN}{codepoint}.png"
            
            # Use toolkit's HTTP method
            image_bytes = await self.toolkit.request(
                method="GET",
                url=url,
                extract="bytes"
            )
            
            if image_bytes:
                emoji_img = Image.open(BytesIO(image_bytes)).convert("RGBA")
                emoji_img = emoji_img.resize((size, size), Image.Resampling.LANCZOS)
                self._emoji_cache[cache_key] = emoji_img
                return emoji_img.copy()
        except Exception:
            pass
        
        return None

    def _parse_text_with_emojis(self, text: str) -> List[Tuple[str, bool]]:
        """
        Parse text into segments of regular text and emojis
        
        Args:
            text: Text to parse
            
        Returns:
            List of (segment, is_emoji) tuples
        """
        segments = []
        current_text = ""
        
        for char in text:
            if char in emoji.EMOJI_DATA:
                # Save accumulated text
                if current_text:
                    segments.append((current_text, False))
                    current_text = ""
                # Add emoji
                segments.append((char, True))
            else:
                current_text += char
        
        # Add remaining text
        if current_text:
            segments.append((current_text, False))
        
        return segments

    # ===== CORE METHODS =====

    def fetch(self, name: str) -> Image.Image:
        """
        Retrieve an image with lazy loading and LRU caching
        
        Args:
            name: Image name (without extension)
            
        Returns:
            Copy of the image in RGBA format
            
        Raises:
            KeyError: If image doesn't exist
        """
        key = name.lower()
        
        # Cache hit
        if key in self._cache:
            self._stats["hits"] += 1
            self._cache.move_to_end(key)
            return self._cache[key].copy()
        
        # Cache miss
        self._stats["misses"] += 1
        img = self._load_to_cache(key)
        return img.copy()

    def list(self) -> list[str]:
        """Return list of all available images"""
        return list(self._index.keys())

    def has_image(self, name: str) -> bool:
        """
        Check if an image exists without loading it
        
        Args:
            name: Image name
            
        Returns:
            True if exists, False otherwise
        """
        return name.lower() in self._index

    def warm_cache(self, names: List[str]):
        """
        Preload multiple images into cache
        
        Args:
            names: List of image names to preload
        """
        for name in names:
            try:
                if name.lower() not in self._cache:
                    self._load_to_cache(name)
            except KeyError:
                pass

    def flush_cache(self):
        """Clear entire image cache"""
        self._cache.clear()
        self._cache_memory = 0
        self._stats["evictions"] = 0
        self._emoji_cache.clear()

    def get_cache_stats(self) -> dict:
        """
        Get cache performance metrics
        
        Returns:
            Dict with hits, misses, hit_rate, cache_size, memory usage
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (
            self._stats["hits"] / total_requests * 100 
            if total_requests > 0 else 0
        )
        
        return {
            **self._stats,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
            "cache_memory_mb": f"{self._cache_memory / (1024 * 1024):.2f}",
            "indexed_images": len(self._index),
            "emoji_cache_size": len(self._emoji_cache)
        }

    # ===== CONVERSION METHODS =====

    def from_bytes(
        self, 
        data: Union[bytes, bytearray, BytesIO], 
        mode: str = "RGBA"
    ) -> Image.Image:
        """
        Create image from bytes
        
        Args:
            data: Image data as bytes, bytearray or BytesIO
            mode: Color mode (default: RGBA)
            
        Returns:
            PIL Image
            
        Raises:
            TypeError: If data type is invalid
            ValueError: If data is not a valid image
        """
        if isinstance(data, (bytes, bytearray)):
            buffer = BytesIO(data)
        elif isinstance(data, BytesIO):
            buffer = data
        else:
            raise TypeError("Data must be bytes, bytearray, or BytesIO")

        try:
            with Image.open(buffer) as img:
                return img.convert(mode)
        except Exception as e:
            raise ValueError("Invalid image data") from e

    def to_bytes(
        self, 
        image: Image.Image, 
        format: str = "PNG",
        quality: int = 95,
        optimize: bool = False,
        **save_kwargs: Any
    ) -> bytes:
        """
        Convert PIL image to bytes
        
        Args:
            image: PIL Image
            format: Output format (PNG, JPEG, WEBP, etc)
            quality: Compression quality (1-100, for JPEG/WEBP)
            optimize: Optimize file size
            **save_kwargs: Additional Image.save() arguments
            
        Returns:
            Image as bytes
            
        Raises:
            TypeError: If not a valid PIL image
        """
        if not isinstance(image, Image.Image):
            raise TypeError("Image must be PIL.Image.Image")

        buffer = BytesIO()
        
        save_params = save_kwargs.copy()
        if format.upper() in ("JPEG", "JPG"):
            save_params.setdefault("quality", quality)
            save_params.setdefault("optimize", optimize)
        elif format.upper() == "WEBP":
            save_params.setdefault("quality", quality)
        elif format.upper() == "PNG":
            save_params.setdefault("optimize", optimize)
        
        image.save(buffer, format=format.upper(), **save_params)
        buffer.seek(0)
        return buffer.getvalue()

    def to_file(
        self, 
        image: Image.Image, 
        filename: str,
        format: str = "PNG",
        **kwargs
    ) -> File:
        """
        Convert PIL image to discord.File
        
        Args:
            image: PIL Image
            filename: File name
            format: Output format
            **kwargs: Additional to_bytes() arguments
            
        Returns:
            discord.File ready to send
        """
        data = self.to_bytes(image, format=format, **kwargs)
        return File(fp=BytesIO(data), filename=filename)

    # ===== MASKING & SHAPE OPERATIONS =====

    def mask_ellipse(self, image: Image.Image) -> Image.Image:
        """
        Apply elliptical mask to image
        
        Args:
            image: Source image
            
        Returns:
            Image with ellipse mask applied
        """
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        width, height = image.size
        draw.ellipse((0, 0, width, height), fill=255)
        image.putalpha(mask)
        return image

    def round_corners(
        self, 
        image: Image.Image, 
        radius: int = 10
    ) -> Image.Image:
        """
        Apply rounded corners to image
        
        Args:
            image: Source image
            radius: Corner radius in pixels
            
        Returns:
            Image with rounded corners
        """
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        width, height = image.size
        draw.rounded_rectangle((0, 0, width, height), radius, fill=255)
        image.putalpha(mask)
        return image

    # ===== TEXT RENDERING =====

    async def render_text(
        self, 
        image: Image.Image,
        xy: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: Tuple[int, int, int, int] = (255, 255, 255, 255),
        spacing: int = 4,
        align: str = "left",
        emoji_scale: float = 1.0,
        stroke_width: int = 0,
        stroke_fill: Tuple[int, int, int, int] = (0, 0, 0, 255),
        max_width: int | None = None
    ):
        """
        Render text with emoji support using ToolKit's HTTP
        
        Args:
            image: Base image to draw on
            xy: (x, y) position to start drawing
            text: Text to render (with emojis)
            font: Font to use for text
            fill: Text color as RGBA tuple
            spacing: Line spacing in pixels
            align: Text alignment ("left", "center", "right")
            emoji_scale: Scale factor for emoji size relative to font
            stroke_width: Width of text stroke
            stroke_fill: Color of text stroke as RGBA tuple
            max_width: Maximum width for text wrapping (in pixels)
        
        Example:
            await manager.render_text(
                img, 
                xy=(10, 10), 
                text="Hello 👋 World 🌍", 
                font=font, 
                fill=(255, 255, 255, 255)
            )
        """
        draw = ImageDraw.Draw(image)
        x, y = xy
        emoji_size = int(font.size * emoji_scale)
        
        lines = text.split('\n')
        for line in lines:
            segments = self._parse_text_with_emojis(line)
            
            # Calculate total line width
            line_width = 0
            for segment, is_emoji in segments:
                if is_emoji:
                    line_width += emoji_size + 2
                else:
                    bbox = font.getbbox(segment)
                    line_width += bbox[2] - bbox[0]
            
            # Apply alignment
            if align == "center" and max_width:
                current_x = x + (max_width - line_width) // 2
            elif align == "right" and max_width:
                current_x = x + (max_width - line_width)
            else:  # left
                current_x = x
            
            # Render segments
            for segment, is_emoji in segments:
                if is_emoji:
                    emoji_img = await self._get_emoji_image(segment, emoji_size)
                    if emoji_img:
                        emoji_y = y + (font.size - emoji_size) // 2
                        image.paste(emoji_img, (current_x, emoji_y), emoji_img)
                        current_x += emoji_size + 2
                else:
                    draw.text((current_x, y), segment, font=font, fill=fill, 
                            stroke_width=stroke_width, stroke_fill=stroke_fill)
                    bbox = font.getbbox(segment)
                    current_x += bbox[2] - bbox[0]
            
            y += font.size + spacing

    async def measure_text(
        self, 
        font: ImageFont.FreeTypeFont, 
        text: str, 
        spacing: int = 4,
        emoji_scale: float = 1.0
    ) -> Tuple[int, int]:
        """
        Measure text dimensions with emoji support
        
        Args:
            font: Font to use
            text: Text to measure
            spacing: Line spacing in pixels
            emoji_scale: Scale factor for emoji size
            
        Returns:
            Tuple (width, height) in pixels
        """
        emoji_size = int(font.size * emoji_scale)
        max_width = 0
        total_height = 0
        
        lines = text.split('\n')
        for line_idx, line in enumerate(lines):
            line_width = 0
            segments = self._parse_text_with_emojis(line)
            
            for segment, is_emoji in segments:
                if is_emoji:
                    line_width += emoji_size + 2
                else:
                    bbox = font.getbbox(segment)
                    line_width += bbox[2] - bbox[0]
            
            max_width = max(max_width, line_width)
            total_height += font.size
            
            if line_idx < len(lines) - 1:
                total_height += spacing
        
        return max_width, total_height
    
    def wrap_text(
    self,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    emoji_scale: float = 1.0
    ) -> str:
        """
        Wrap text to fit within max_width in pixels
        
        Args:
            text: Text to wrap
            font: Font to use for measuring
            max_width: Maximum width in pixels
            emoji_scale: Emoji scale factor
            
        Returns:
            Text with newlines inserted where needed
        
        Example:
            wrapped = manager.wrap_text(
                "This is a very long text that needs wrapping",
                font=font,
                max_width=400
            )
            await manager.render_text(img, xy=(10,10), text=wrapped, font=font)
        """
        words = text.split(' ')
        lines = []
        current_line = []
        
        emoji_size = int(font.size * emoji_scale)
        
        for word in words:
            # Test line with this word added
            test_line = ' '.join(current_line + [word])
            
            # Calculate width considering emojis
            line_width = 0
            segments = self._parse_text_with_emojis(test_line)
            
            for segment, is_emoji in segments:
                if is_emoji:
                    line_width += emoji_size + 2
                else:
                    bbox = font.getbbox(segment)
                    line_width += bbox[2] - bbox[0]
            
            # Check if line exceeds max width
            if line_width <= max_width:
                current_line.append(word)
            else:
                # Line too long, save current and start new
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word too long, force it anyway
                    lines.append(word)
        
        # Add last line
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)

    def calculate_text_bbox(
        self, 
        font: ImageFont.FreeTypeFont, 
        text: str
    ) -> Tuple[int, int]:
        """
        Calculate text bounding box (without emoji support, fast)
        
        Args:
            font: Font to use
            text: Text to measure (supports multiline with \\n)
            
        Returns:
            Tuple (width, height) in pixels
        """
        if "\n" in text:
            lines = text.split("\n")
            max_width, total_height = 0, 0
            for line in lines:
                bbox = font.getbbox(line)
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                if width > max_width:
                    max_width = width
                total_height += height
            return max_width, total_height
        else:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]

    # ===== COLOR ANALYSIS =====

    def _kmeans_clustering(
        self, 
        pixels: np.ndarray, 
        k: int, 
        max_iter: int = 100
    ) -> np.ndarray:
        """
        K-means clustering algorithm for color quantization
        
        Args:
            pixels: Pixel array (N, 4) with RGBA values
            k: Number of clusters
            max_iter: Maximum iterations
            
        Returns:
            Array of centroids (color clusters)
        """
        centroids = pixels[np.random.choice(pixels.shape[0], size=k, replace=False)]
        
        for _ in range(max_iter):
            distances = np.sqrt(((pixels - centroids[:, np.newaxis])**2).sum(axis=2))
            closest = np.argmin(distances, axis=0)
            
            new_centroids = []
            for cluster_idx in range(centroids.shape[0]):
                cluster_pixels = pixels[closest == cluster_idx]
                if len(cluster_pixels) > 0:
                    new_centroid = cluster_pixels.mean(axis=0)
                    new_centroids.append(new_centroid)
                else:
                    new_centroids.append(centroids[cluster_idx])
            
            new_centroids = np.array(new_centroids)
            if np.all(centroids == new_centroids):
                break
            centroids = new_centroids
        
        return centroids

    def extract_palette(
        self, 
        image: Image.Image, 
        n_colors: int = 2
    ) -> List[List[int]]:
        """
        Extract dominant color palette using K-means clustering
        
        Args:
            image: Source image
            n_colors: Number of colors to extract
            
        Returns:
            List of colors in [R, G, B, A] format, sorted by dominance
        """
        # Downsample for performance
        downsampled = image.resize((image.size[0] // 2, image.size[1] // 2))
        downsampled = downsampled.convert('RGBA')
        
        # Flatten pixel array
        pixels = np.array(downsampled)
        pixels = pixels.reshape(-1, pixels.shape[-1])
        
        # Find dominant colors
        dominant_colors = self._kmeans_clustering(pixels, n_colors)
        
        # Calculate cluster sizes
        closest = np.argmin(
            np.sqrt(((pixels - dominant_colors[:, np.newaxis])**2).sum(axis=2)), 
            axis=0
        )
        cluster_counts = np.bincount(closest, minlength=dominant_colors.shape[0])
        
        # Calculate diversity scores
        pairwise_distances = np.sqrt(
            ((dominant_colors[:, np.newaxis, :] - dominant_colors[np.newaxis, :, :])**2).sum(axis=2)
        )
        
        # Score based on prevalence and distinctiveness
        scores = cluster_counts * (1 / (1 + pairwise_distances.sum(axis=0)))
        sorted_indices = np.argsort(scores)[::-1]
        sorted_colors = dominant_colors[sorted_indices]
        
        return [list(map(int, color)) for color in sorted_colors[:n_colors]]

    # ===== GRADIENT RENDERING =====

    def fill_gradient(
        self, 
        base: Image.Image, 
        bbox: Tuple[Tuple[int, int], Tuple[int, int]], 
        stops: List[Tuple[int, int, int, int]], 
        orientation: str = "vertical"
    ):
        """
        Fill region with gradient
        
        Args:
            base: Base image to draw on
            bbox: ((x, y), (width, height)) - position and dimensions
            stops: List of RGBA color stops (minimum 2 required)
            orientation: "vertical" or "horizontal"
            
        Raises:
            ValueError: If orientation invalid or less than 2 color stops
        
        Example:
            manager.fill_gradient(
                img,
                bbox=((0, 0), (800, 600)),
                stops=[(255, 0, 0, 255), (0, 0, 255, 255)],
                orientation="vertical"
            )
        """
        if orientation not in ("vertical", "horizontal"):
            raise ValueError("Invalid orientation. Use 'vertical' or 'horizontal'.")
        
        if len(stops) < 2:
            raise ValueError("At least two color stops required for gradient.")
        
        gradient = []
        width, height = bbox[1]
        steps = height if orientation == "vertical" else width
        
        for i in range(steps):
            # Determine which color stops to interpolate between
            segment_index = int(i / steps * (len(stops) - 1))
            r1, g1, b1, a1 = stops[segment_index]
            r2, g2, b2, a2 = stops[segment_index + 1]
            
            # Calculate interpolation ratio
            ratio = (i / steps * len(stops)) - segment_index
            
            # Interpolate RGB values
            r = int(r1 * (1 - ratio) + r2 * ratio)
            g = int(g1 * (1 - ratio) + g2 * ratio)
            b = int(b1 * (1 - ratio) + b2 * ratio)
            gradient.append((r, g, b))
        
        # Draw gradient
        draw = ImageDraw.Draw(base)
        x_start, y_start = bbox[0]
        
        for i in range(steps):
            if orientation == "vertical":
                draw.line(
                    (x_start, y_start + i, x_start + width, y_start + i + 1), 
                    fill=gradient[i], 
                    width=1
                )
            else:
                draw.line(
                    (x_start + i, y_start, x_start + i + 1, y_start + height), 
                    fill=gradient[i], 
                    width=1
                )