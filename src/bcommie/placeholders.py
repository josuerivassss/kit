"""Central catalog of template placeholders (variables and functions).

Extending the template language means adding a method here decorated with
`@placeholder(...)` — the engine discovers it automatically at startup
(see `interpolation/interpolator.py`). No other file needs to change.
"""
from __future__ import annotations

from typing import Any

import discord

from bcommie.interpolation.decorators import PlaceholderType, placeholder
from bcommie.interpolation.render_result import RenderResult


class PlaceholderManager:
    """All variables (`{user.name}`) and functions (`{sum:1;2}`) usable in templates."""

    # -- user variables ---------------------------------------------------

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_name(self, ctx: Any) -> str:
        """Author's username."""
        return ctx.author.name

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_id(self, ctx: Any) -> str:
        """Author's Discord ID."""
        return str(ctx.author.id)

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_mention(self, ctx: Any) -> str:
        """Author mention string."""
        return ctx.author.mention

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_discriminator(self, ctx: Any) -> str:
        """Author's discriminator ('0' for new-style usernames)."""
        return ctx.author.discriminator

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_avatar(self, ctx: Any) -> str:
        """Author's display avatar URL."""
        return str(ctx.author.display_avatar.url)

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_tag(self, ctx: Any) -> str:
        """Author's full tag."""
        return str(ctx.author)

    # -- guild variables --------------------------------------------------

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_name(self, ctx: Any) -> str:
        """Guild name, or 'DM' outside a guild."""
        return ctx.guild.name if ctx.guild else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_id(self, ctx: Any) -> str:
        """Guild ID, or 'DM' outside a guild."""
        return str(ctx.guild.id) if ctx.guild else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_members(self, ctx: Any) -> str:
        """Guild member count."""
        return str(ctx.guild.member_count) if ctx.guild else "0"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_icon(self, ctx: Any) -> str:
        """Guild icon URL, or empty string if unset."""
        if ctx.guild and ctx.guild.icon:
            return str(ctx.guild.icon.url)
        return ""

    # -- channel variables --------------------------------------------------

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_name(self, ctx: Any) -> str:
        """Channel name, or 'DM'."""
        return ctx.channel.name if hasattr(ctx.channel, "name") else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_id(self, ctx: Any) -> str:
        """Channel ID."""
        return str(ctx.channel.id)

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_mention(self, ctx: Any) -> str:
        """Channel mention string, or empty in DMs."""
        return ctx.channel.mention if hasattr(ctx.channel, "mention") else ""

    # -- text functions ---------------------------------------------------

    @placeholder(use=PlaceholderType.FUNCTION)
    async def upper(self, ctx: Any, result: RenderResult, text: str) -> str:
        """`{upper:hello}` -> HELLO."""
        return text.upper()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def lower(self, ctx: Any, result: RenderResult, text: str) -> str:
        """`{lower:HELLO}` -> hello."""
        return text.lower()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def title(self, ctx: Any, result: RenderResult, text: str) -> str:
        """`{title:hello world}` -> Hello World."""
        return text.title()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def length(self, ctx: Any, result: RenderResult, text: str) -> str:
        """`{length:hello}` -> 5."""
        return str(len(text))

    @placeholder(use=PlaceholderType.FUNCTION)
    async def repeat(self, ctx: Any, result: RenderResult, text: str, times: str) -> str:
        """`{repeat:hi;3}` -> hihihi. Clamped to [0, 10] repetitions."""
        try:
            count = min(max(int(times), 0), 10)
            return text * count
        except (ValueError, TypeError):
            return text

    # -- math functions -----------------------------------------------------

    @placeholder(use=PlaceholderType.FUNCTION)
    async def sum(self, ctx: Any, result: RenderResult, *args: str) -> str:
        """`{sum:1;2;3}` -> 6. Non-numeric args are skipped."""
        total = 0
        for arg in args:
            try:
                total += int(arg)
            except (ValueError, TypeError):
                continue
        return str(total)

    @placeholder(use=PlaceholderType.FUNCTION)
    async def sub(self, ctx: Any, result: RenderResult, a: str, b: str) -> str:
        """`{sub:10;3}` -> 7."""
        try:
            return str(int(a) - int(b))
        except (ValueError, TypeError):
            return "0"

    @placeholder(use=PlaceholderType.FUNCTION)
    async def mul(self, ctx: Any, result: RenderResult, a: str, b: str) -> str:
        """`{mul:5;3}` -> 15."""
        try:
            return str(int(a) * int(b))
        except (ValueError, TypeError):
            return "0"

    @placeholder(use=PlaceholderType.FUNCTION)
    async def div(self, ctx: Any, result: RenderResult, a: str, b: str) -> str:
        """`{div:10;2}` -> 5. Returns 'undefined' on division by zero."""
        try:
            divisor = int(b)
            if divisor == 0:
                return "undefined"
            return str(int(a) // divisor)
        except (ValueError, TypeError):
            return "0"

    # -- embed builder functions ----------------------------------------------

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_title(self, ctx: Any, result: RenderResult, title: str) -> str:
        """Starts a new embed with this title. `{embed.title:Welcome!}`."""
        embed = discord.Embed()
        embed.title = title[:256]
        result.add_embed(embed)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_description(self, ctx: Any, result: RenderResult, description: str) -> str:
        """Sets the description of the current (last) embed."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].description = description[:4096]
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_color(self, ctx: Any, result: RenderResult, color: str) -> str:
        """Sets the color of the current embed. Accepts hex with or without '#'."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        try:
            result.embeds[-1].color = discord.Color(int(color.lstrip("#"), 16))
        except (ValueError, TypeError):
            pass
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_footer(self, ctx: Any, result: RenderResult, text: str) -> str:
        """Sets the footer text of the current embed."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_footer(text=text[:2048])
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_image(self, ctx: Any, result: RenderResult, url: str) -> str:
        """Sets the main image of the current embed."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_image(url=url)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_thumbnail(self, ctx: Any, result: RenderResult, url: str) -> str:
        """Sets the thumbnail of the current embed."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_thumbnail(url=url)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_field(
        self, ctx: Any, result: RenderResult, name: str, value: str, inline: str = "true"
    ) -> str:
        """Adds a field to the current embed. `{embed.field:Name;Value;true}`."""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].add_field(
            name=name[:256], value=value[:1024], inline=inline.lower() in ("true", "yes", "1")
        )
        return ""

    # -- misc functions -----------------------------------------------------

    @placeholder(use=PlaceholderType.FUNCTION)
    async def emoji(self, ctx: Any, result: RenderResult, emoji: str) -> str:
        """Registers an emoji to react with; renders nothing itself."""
        result.add_emoji(emoji)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def if_condition(
        self, ctx: Any, result: RenderResult, condition: str, true_val: str, false_val: str = ""
    ) -> str:
        """`{if:1;yes;no}`. Falsy values: '', '0', 'false', 'no'."""
        is_truthy = bool(condition) and condition.lower() not in ("0", "false", "no", "")
        return true_val if is_truthy else false_val
