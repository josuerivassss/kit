"""
Result container for interpolation rendering.

Stores the rendered content along with additional metadata
like embeds and emojis that can be collected during rendering.
"""

from dataclasses import dataclass, field
from typing import List, Any


@dataclass(slots=True)
class RenderResult:
    """
    Container for interpolation render results.
    
    Attributes:
        content: Rendered text content
        embeds: List of Discord embeds collected during rendering
        emojis: List of emoji strings collected during rendering
    
    This allows placeholder functions to not only return text,
    but also add embeds or track emojis used in the message.
    """
    content: str
    embeds: List[Any] = field(default_factory=list)
    emojis: List[str] = field(default_factory=list)
    
    def add_embed(self, embed: Any) -> None:
        """Add an embed to the result."""
        self.embeds.append(embed)
    
    def add_emoji(self, emoji: str) -> None:
        """Add an emoji to the tracking list."""
        if emoji not in self.emojis:
            self.emojis.append(emoji)
    
    def merge(self, other: 'RenderResult') -> None:
        """
        Merge another RenderResult into this one.
        
        Args:
            other: RenderResult to merge
        """
        self.content += other.content
        self.embeds.extend(other.embeds)
        for emoji in other.emojis:
            self.add_emoji(emoji)