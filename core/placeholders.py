"""
Central registry for all template placeholders.

Provides variables (no args) and functions (with args) for
use in templates like welcome messages, tags, etc.
"""

import discord
from core.interpolation.decorators import placeholder, PlaceholderType


class PlaceholderManager:
    """
    Central registry for all placeholders.
    
    Variables: {user.name}, {user.id}, {guild.name}
    Functions: {upper:text}, {sum:a;b}, {embed.title:text}
    """

    # ========= USER VARIABLES =========

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_name(self, ctx):
        """Returns the username of the author."""
        return ctx.author.name

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_id(self, ctx):
        """Returns the user ID as a string."""
        return str(ctx.author.id)

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_mention(self, ctx):
        """Returns a mention string for the user."""
        return ctx.author.mention

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_discriminator(self, ctx):
        """Returns the user's discriminator (or '0' for new usernames)."""
        return ctx.author.discriminator

    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_avatar(self, ctx):
        """Returns the user's avatar URL."""
        return str(ctx.author.display_avatar.url)
    
    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_tag(self, ctx):
        """Returns the user's full tag (name#discriminator)."""
        return str(ctx.author)

    # ========= GUILD VARIABLES =========

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_name(self, ctx):
        """Returns the guild name, or 'DM' if in direct messages."""
        return ctx.guild.name if ctx.guild else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_id(self, ctx):
        """Returns the guild ID, or 'DM' if in direct messages."""
        return str(ctx.guild.id) if ctx.guild else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_members(self, ctx):
        """Returns the member count of the guild."""
        return str(ctx.guild.member_count) if ctx.guild else "0"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def guild_icon(self, ctx):
        """Returns the guild icon URL."""
        if ctx.guild and ctx.guild.icon:
            return str(ctx.guild.icon.url)
        return ""

    # ========= CHANNEL VARIABLES =========

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_name(self, ctx):
        """Returns the channel name."""
        return ctx.channel.name if hasattr(ctx.channel, 'name') else "DM"

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_id(self, ctx):
        """Returns the channel ID."""
        return str(ctx.channel.id)

    @placeholder(use=PlaceholderType.VARIABLE)
    async def channel_mention(self, ctx):
        """Returns a mention string for the channel."""
        return ctx.channel.mention if hasattr(ctx.channel, 'mention') else ""

    # ========= TEXT FUNCTIONS =========

    @placeholder(use=PlaceholderType.FUNCTION)
    async def upper(self, ctx, result, text):
        """Converts text to uppercase. Usage: {upper:hello}"""
        return text.upper()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def lower(self, ctx, result, text):
        """Converts text to lowercase. Usage: {lower:HELLO}"""
        return text.lower()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def title(self, ctx, result, text):
        """Converts text to title case. Usage: {title:hello world}"""
        return text.title()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def length(self, ctx, result, text):
        """Returns the length of text. Usage: {length:hello}"""
        return str(len(text))

    @placeholder(use=PlaceholderType.FUNCTION)
    async def repeat(self, ctx, result, text, times):
        """Repeats text N times. Usage: {repeat:hello;3}"""
        try:
            count = int(times)
            # Limit repetitions to prevent abuse
            count = min(max(count, 0), 10)
            return text * count
        except (ValueError, TypeError):
            return text

    # ========= MATH FUNCTIONS =========

    @placeholder(use=PlaceholderType.FUNCTION)
    async def sum(self, ctx, result, *args):
        """
        Sums all numeric arguments. Usage: {sum:1;2;3}
        
        Returns "0" if no valid numbers are provided.
        """
        total = 0
        for arg in args:
            try:
                total += int(arg)
            except (ValueError, TypeError):
                continue
        return str(total)

    @placeholder(use=PlaceholderType.FUNCTION)
    async def sub(self, ctx, result, a, b):
        """Subtracts b from a. Usage: {sub:10;3}"""
        try:
            return str(int(a) - int(b))
        except (ValueError, TypeError):
            return "0"

    @placeholder(use=PlaceholderType.FUNCTION)
    async def mul(self, ctx, result, a, b):
        """Multiplies a by b. Usage: {mul:5;3}"""
        try:
            return str(int(a) * int(b))
        except (ValueError, TypeError):
            return "0"

    @placeholder(use=PlaceholderType.FUNCTION)
    async def div(self, ctx, result, a, b):
        """Divides a by b. Usage: {div:10;2}"""
        try:
            divisor = int(b)
            if divisor == 0:
                return "undefined"
            return str(int(a) // divisor)
        except (ValueError, TypeError):
            return "0"

    # ========= EMBED FUNCTIONS =========

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_title(self, ctx, result, title):
        """
        Sets the title of a new embed. Usage: {embed.title:Welcome!}
        
        Creates a new embed each time it's called, allowing multiple embeds
        in one message.
        """
        embed = discord.Embed()
        embed.title = title[:256]  # Discord limit
        result.add_embed(embed)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_description(self, ctx, result, description):
        """
        Sets the description of the last embed. Usage: {embed.description:Hello}
        
        If no embed exists, creates one first.
        """
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].description = description[:4096]  # Discord limit
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_color(self, ctx, result, color):
        """
        Sets the color of the last embed. Usage: {embed.color:#ff0000}
        
        Accepts hex colors with or without #.
        """
        if not result.embeds:
            result.add_embed(discord.Embed())
        
        # Remove # if present
        color = color.lstrip('#')
        
        try:
            # Convert hex to int
            color_int = int(color, 16)
            result.embeds[-1].color = discord.Color(color_int)
        except (ValueError, TypeError):
            # Invalid color, ignore
            pass
        
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_footer(self, ctx, result, text):
        """Sets the footer of the last embed. Usage: {embed.footer:Footer text}"""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_footer(text=text[:2048])  # Discord limit
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_image(self, ctx, result, url):
        """Sets the image of the last embed. Usage: {embed.image:https://...}"""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_image(url=url)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_thumbnail(self, ctx, result, url):
        """Sets the thumbnail of the last embed. Usage: {embed.thumbnail:https://...}"""
        if not result.embeds:
            result.add_embed(discord.Embed())
        result.embeds[-1].set_thumbnail(url=url)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def embed_field(self, ctx, result, name, value, inline="true"):
        """
        Adds a field to the last embed. Usage: {embed.field:Name;Value;true}
        
        The inline parameter is optional and defaults to "true".
        """
        if not result.embeds:
            result.add_embed(discord.Embed())
        
        # Parse inline parameter
        is_inline = inline.lower() in ("true", "yes", "1")
        
        result.embeds[-1].add_field(
            name=name[:256],  # Discord limit
            value=value[:1024],  # Discord limit
            inline=is_inline
        )
        return ""

    # ========= UTILITY FUNCTIONS =========

    @placeholder(use=PlaceholderType.FUNCTION)
    async def emoji(self, ctx, result, emoji):
        """
        Tracks an emoji for reaction purposes. Usage: {emoji:👍}
        
        Does not render anything, just adds to the emoji list.
        """
        result.add_emoji(emoji)
        return ""

    @placeholder(use=PlaceholderType.FUNCTION)
    async def if_condition(self, ctx, result, condition, true_val, false_val=""):
        """
        Simple conditional. Usage: {if:1;yes;no}
        
        Returns true_val if condition is truthy, else false_val.
        Truthy values: any non-empty string except "0", "false", "no"
        """
        is_truthy = condition and condition.lower() not in ("0", "false", "no", "")
        return true_val if is_truthy else false_val