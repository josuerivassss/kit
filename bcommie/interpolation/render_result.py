"""Container accumulated while rendering a template."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RenderResult:
    """Rendered text plus any embeds/emojis a placeholder function attached."""

    content: str
    embeds: list[Any] = field(default_factory=list)
    emojis: list[str] = field(default_factory=list)

    def add_embed(self, embed: Any) -> None:
        self.embeds.append(embed)

    def add_emoji(self, emoji: str) -> None:
        if emoji not in self.emojis:
            self.emojis.append(emoji)

    def merge(self, other: RenderResult) -> None:
        self.content += other.content
        self.embeds.extend(other.embeds)
        for emoji in other.emojis:
            self.add_emoji(emoji)
