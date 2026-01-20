from pathlib import Path
from PIL import ImageFont

class TypefaceManager:
    SUPPORTED_EXTENSIONS = {".ttf", ".otf"}

    def __init__(self, path: str):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ValueError(f"Invalid fonts directory: {path}")
        self._fonts = self._index_fonts()

    def _index_fonts(self) -> dict[str, dict[str, Path]]:
        fonts: dict[str, dict[str, Path]] = {}

        for file in self.path.rglob("*"):
            if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            parts = file.stem.split("_", 1)
            family = parts[0].lower()
            style = parts[1].lower() if len(parts) > 1 else "regular"

            fonts.setdefault(family, {})[style] = file

        return fonts

    def fetch(
        self,
        name: str,
        style: str = "regular",
        size: int = 12
    ) -> ImageFont.FreeTypeFont:

        family = name.lower()
        style = style.lower()

        try:
            font_path = self._fonts[family][style]
        except KeyError:
            raise KeyError(f"Font '{name}' with style '{style}' not found")

        return ImageFont.truetype(str(font_path), size=size)

    def list(self) -> dict[str, list[str]]:
        return {
            family: list(styles.keys())
            for family, styles in self._fonts.items()
        }