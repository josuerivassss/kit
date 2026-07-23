"""Starboard cog: pins messages that collect enough reactions of a
configurable emoji into a dedicated channel.

Config lives in the same `guilds` document used by welcome/leave/autoroles,
under the `starboard` path -- kept in sync with the dashboard API's
DEFAULT_STARBOARD/StarboardUpdate shape in routers/json/guilds.py.

No per-message mapping is persisted in Mongo. Instead, whether a message
was already starred is resolved by scanning the starboard channel's recent
history for an embed whose footer encodes the original message id -- same
approach as the previous starboard implementation. This trades a Discord
API call (channel.history, cheap and generously rate-limited) for a Mongo
write per reaction (expensive under load), at the cost of only finding
entries within HISTORY_SCAN_LIMIT messages back.

GUILDS TABLE

"_id": Guild ID (int)
"starboard": {
    "enabled": bool,
    "channel_id": int | None,
    "emoji": str,
    "threshold": int,
    "count_self_stars": bool,
}
"""
from __future__ import annotations

import time
from typing import Any

import discord
from discord.ext import commands

from bcommie.help import send_help_group
from bcommie.kernel import CommieBot, CommieContext
from bcommie.logging_setup import get_logger

logger = get_logger(__name__)

# Mirrors DEFAULT_STARBOARD in routers/json/guilds.py exactly (channel_id
# stays as int here since the bot works with raw Discord snowflakes).
DEFAULT_STARBOARD: dict[str, Any] = {
    "enabled": False,
    "channel_id": None,
    "emoji": "\u2b50",
    "threshold": 3,
    "count_self_stars": False,
}

_CONFIG_CACHE_TTL = 15.0  # seconds; per-process only, see _get_config()
HISTORY_SCAN_LIMIT = 100  # how far back to look for an existing starboard entry
FOOTER_MARKER = "Starboard"

# Escalating visual only applies to the default star emoji, matching the
# previous implementation's aesthetic -- a custom/non-default emoji is
# shown as-is regardless of count, since "getting sparklier" only makes
# visual sense for the star family.
_ESCALATION_TIERS = ((13, "\u2728"), (9, "\U0001f4ab"), (5, "\U0001f31f"))


def _scaled_emoji(base_emoji: str, count: int, threshold: int) -> str:
    if base_emoji != DEFAULT_STARBOARD["emoji"]:
        return base_emoji
    for offset, tier_emoji in _ESCALATION_TIERS:
        if count >= threshold + offset:
            return tier_emoji
    return base_emoji


class Starboard(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot
        # In-memory cache of resolved starboard config per guild, so a busy
        # server's reaction spam doesn't hit Mongo on every single reaction.
        # Bounded TTL, NOT shared across shards/processes -- a config
        # change made via command is reflected immediately on the shard
        # that ran it (see _update_config), and propagates to other
        # shards/processes within one TTL window. That staleness window is
        # acceptable for a cosmetic config like this.
        self._config_cache: dict[int, tuple[float, dict[str, Any]]] = {}

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        cached = self._config_cache.get(guild_id)
        if cached is not None and time.monotonic() - cached[0] < _CONFIG_CACHE_TTL:
            return cached[1]
        doc = await self.bot.db.get(table="guilds", id=guild_id, path="starboard") or {}
        config = {**DEFAULT_STARBOARD, **doc}
        self._config_cache[guild_id] = (time.monotonic(), config)
        return config

    async def _update_config(self, guild_id: int, field: str, value: Any) -> None:
        await self.bot.db.set(table="guilds", id=guild_id, path=f"starboard.{field}", value=value)
        cached = self._config_cache.get(guild_id)
        config = dict(cached[1]) if cached else {**DEFAULT_STARBOARD}
        config[field] = value
        self._config_cache[guild_id] = (time.monotonic(), config)

    # -- commands -------------------------------------------------------------

    @commands.hybrid_group(name="starboard")
    async def starboard(self, ctx: CommieContext):
        """Starboard configuration commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("starboard")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="enable", aliases=["on"])
    async def starboard_enable(self, ctx: CommieContext):
        """Enables the starboard"""
        await self._update_config(ctx.guild.id, "enabled", True)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.starboardEnabled"), type="success")

    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="disable", aliases=["off"])
    async def starboard_disable(self, ctx: CommieContext):
        """Disables the starboard"""
        await self._update_config(ctx.guild.id, "enabled", False)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.starboardDisabled"), type="success")

    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="channel")
    @discord.app_commands.describe(channel="The channel where starred messages will be posted")
    async def starboard_channel(self, ctx: CommieContext, channel: discord.TextChannel):
        """Sets the starboard channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links or not perms.read_message_history:
            raise commands.CommandError(T.get("errors.cantSeeChannel"), T.get("errors.cantSeeChannelHint"))
        await self._update_config(ctx.guild.id, "channel_id", channel.id)
        # Enable implicitly on channel-set, same pattern as welcome/leave channel.
        await self._update_config(ctx.guild.id, "enabled", True)
        await ctx.answer(T.get("success.starboardChannelSet", channel=channel.mention), type="success")

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="emoji")
    @discord.app_commands.describe(emoji="The emoji messages need to be starred with")
    async def starboard_emoji(self, ctx: CommieContext, emoji: str):
        """Sets the starboard emoji"""
        await ctx.defer()
        T = await ctx.get_locale()
        parsed = self.bot.toolkit.parse_emoji(emoji, allow="both")
        if not parsed:
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
        await self._update_config(ctx.guild.id, "emoji", parsed)
        await ctx.answer(T.get("success.starboardEmojiSet", emoji=parsed), type="success")

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="threshold")
    @discord.app_commands.describe(amount="Minimum number of stars needed (1-500)")
    async def starboard_threshold(self, ctx: CommieContext, amount: discord.app_commands.Range[int, 1, 500]):
        """Sets the star threshold"""
        await self._update_config(ctx.guild.id, "threshold", amount)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.starboardThresholdSet", amount=amount), type="success")

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @starboard.command(name="selfstars")
    @discord.app_commands.describe(state="Whether authors can star their own messages")
    async def starboard_selfstars(self, ctx: CommieContext, state: bool):
        """Toggles whether authors can star their own messages"""
        await self._update_config(ctx.guild.id, "count_self_stars", state)
        T = await ctx.get_locale()
        key = "success.starboardSelfStarsEnabled" if state else "success.starboardSelfStarsDisabled"
        await ctx.answer(T.get(key), type="success")

    # -- reaction handling ------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction_event(payload.guild_id, payload.channel_id, payload.message_id, payload.emoji)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction_event(payload.guild_id, payload.channel_id, payload.message_id, payload.emoji)

    @commands.Cog.listener()
    async def on_raw_reaction_clear(self, payload: discord.RawReactionClearEvent):
        # All reactions wiped -- the entry (if any) no longer qualifies, drop it unconditionally.
        if payload.guild_id is None:
            return
        config = await self._get_config(payload.guild_id)
        if not config["enabled"] or not config["channel_id"]:
            return
        target_channel = await self._resolve_channel(config["channel_id"])
        if target_channel is None:
            return
        existing = await self._find_starboard_message(target_channel, payload.message_id)
        if existing:
            try:
                await existing.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    async def _handle_reaction_event(
        self, guild_id: int | None, channel_id: int, message_id: int, emoji: discord.PartialEmoji
    ) -> None:
        if guild_id is None:
            return
        config = await self._get_config(guild_id)
        # Early return before any fetch -- guilds not using starboard should
        # never trigger a Discord/Mongo round-trip on reaction spam.
        if not config["enabled"] or not config["channel_id"]:
            return
        if str(emoji) != config["emoji"]:
            return
        await self._sync_entry(channel_id, message_id, config)

    async def _resolve_channel(self, channel_id: int) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _find_starboard_message(
        self, target_channel: discord.TextChannel, source_message_id: int
    ) -> discord.Message | None:
        """Scans the starboard channel's recent history for an existing
        entry pointing at `source_message_id`, identified via the embed
        footer -- avoids persisting a message-id mapping in Mongo."""
        marker = f"{FOOTER_MARKER} | {source_message_id}"
        async for candidate in target_channel.history(limit=HISTORY_SCAN_LIMIT):
            if candidate.author.id != self.bot.user.id or not candidate.embeds:
                continue
            footer = candidate.embeds[0].footer
            if footer and footer.text and footer.text.endswith(marker):
                return candidate
        return None

    async def _sync_entry(self, source_channel_id: int, message_id: int, config: dict[str, Any]) -> None:
        source_channel = await self._resolve_channel(source_channel_id)
        if source_channel is None or getattr(source_channel, "nsfw", False):
            return
        try:
            message = await source_channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # Discord is the source of truth for the count -- no local state kept.
        reaction = discord.utils.find(lambda r: str(r.emoji) == config["emoji"], message.reactions)
        count = reaction.count if reaction else 0
        if reaction and not config["count_self_stars"]:
            async for reactor in reaction.users():
                if reactor.id == message.author.id:
                    count -= 1
                    break

        target_channel = await self._resolve_channel(config["channel_id"])
        if target_channel is None:
            logger.warning("starboard_target_channel_unavailable", channel_id=config["channel_id"])
            return

        existing = await self._find_starboard_message(target_channel, message_id)

        if count < config["threshold"]:
            if existing:
                try:
                    await existing.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            return

        star_emoji = _scaled_emoji(config["emoji"], count, config["threshold"])
        content = f"{star_emoji} **{count}** <#{source_channel_id}>"
        embed = self._build_embed(message, message_id)

        try:
            if existing:
                await existing.edit(content=content, embed=embed)
            else:
                await target_channel.send(content=content, embed=embed, view=self._build_jump_view(message))
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("starboard_post_failed", channel_id=config["channel_id"], message_id=message_id)

    def _build_embed(self, message: discord.Message, source_message_id: int) -> discord.Embed:
        content = message.content[:4000] if message.content else None
        image_url = None
        if message.attachments and (message.attachments[0].content_type or "").startswith("image/"):
            image_url = message.attachments[0].url

        embed = discord.Embed(description=content, colour=discord.Color.gold(), timestamp=message.created_at)
        embed.set_author(name=f"@{message.author.name}", icon_url=message.author.display_avatar)
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(
            text=f"{self.bot.user.name} {FOOTER_MARKER} | {source_message_id}",
            icon_url=self.bot.user.display_avatar,
        )
        return embed

    def _build_jump_view(self, message: discord.Message) -> discord.ui.View:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="Jump to message", url=message.jump_url))
        return view


async def setup(bot: CommieBot):
    await bot.add_cog(Starboard(bot))