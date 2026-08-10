"""Configuration cog: per-guild prefix and language settings."""
from __future__ import annotations
import time
from typing import Any
from bcommie.command_registry import COG_IDS, COMMAND_IDS, ID_TO_COG, ID_TO_COMMAND, root_id
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, Locale, CommieEmojis, AnswerType
from bcommie.permissions import protected
from bcommie.ui.base import BaseView
import discord

_CACHE_TTL = 15.0

class CommandDisabledError(commands.CheckFailure):
    """Raised by the global check when the invoked command is disabled.
    Handled explicitly in Events.on_command_error to stay fully silent."""

def _resolve_target(bot: CommieBot, query: str) -> tuple[str, str, str] | None:
    """Resolves user input to (kind, display_name, id). kind is 'command' or 'cog'."""
    normalized = query.strip().lower()
    command = bot.get_command(normalized)
    if command is not None:
        command_id = COMMAND_IDS.get(command.qualified_name)
        return ("command", command.qualified_name, command_id) if command_id else None
    cog = discord.utils.find(lambda c: c.qualified_name.lower() == normalized, bot.cogs.values())
    if cog is not None:
        cog_id = COG_IDS.get(cog.qualified_name)
        return ("cog", cog.qualified_name, cog_id) if cog_id else None
    return None

class LanguageMenu(discord.ui.Select):
    def __init__(self, *, ctx: CommieContext, locale: Locale):
        self.ctx = ctx
        self.t = locale
        super().__init__(placeholder=self.t.get("info.selectLanguage"), max_values=1, min_values=1, options=[
            discord.SelectOption(label="English", value="en", description="Your adventure starts here!", emoji="🇺🇸"),
            discord.SelectOption(label="Español", value="es", description="Tu aventura comienza aquí!", emoji="🇲🇽")])
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_language = self.values[0]
        await self.ctx.bot.db.set(table="guilds", id=self.ctx.guild.id, path="language", value=selected_language)
        T = self.ctx.bot.language.get_locale(selected_language) # Access the new locale for the selected language without awaiting
        await interaction.followup.send(T.get("success.languageSet", language=selected_language) + " " + CommieEmojis.Heart, ephemeral=True)

class Configuration(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot
        self._cache: dict[int, tuple[float, set[str]]] = {}
    
    async def cog_load(self):
        self.bot.add_check(self._global_disabled_check)

    async def cog_unload(self):
        self.bot.remove_check(self._global_disabled_check)

    # -- disabled-set cache ---------------------------------------------------

    async def _get_disabled(self, guild_id: int) -> set[str]:
        cached = self._cache.get(guild_id)
        if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL:
            return cached[1]
        raw = await self.bot.db.get(table="guilds", id=guild_id, path="disabled") or []
        disabled = set(raw)
        self._cache[guild_id] = (time.monotonic(), disabled)
        return disabled

    def _mutate_cache(self, guild_id: int, target_id: str, enabled: bool) -> None:
        cached = self._cache.get(guild_id)
        disabled = set(cached[1]) if cached else set()
        disabled.discard(target_id) if enabled else disabled.add(target_id)
        self._cache[guild_id] = (time.monotonic(), disabled)

    # -- global check -----------------------------------------------------------

    async def _global_disabled_check(self, ctx: CommieContext) -> bool:
        if ctx.guild is None or ctx.command is None:
            return True
        if ctx.command.extras.get("protected"):
            return True
        disabled = await self._get_disabled(ctx.guild.id)
        if not disabled:
            return True
        command_id = COMMAND_IDS.get(ctx.command.qualified_name)
        if command_id and (command_id in disabled or root_id(command_id) in disabled):
            raise CommandDisabledError()
        cog_name = ctx.command.cog.qualified_name if ctx.command.cog else None
        cog_id = COG_IDS.get(cog_name) if cog_name else None
        if cog_id and cog_id in disabled:
            raise CommandDisabledError()
        return True
    
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.hybrid_command(name="enable")
    @discord.app_commands.describe(target="The command, subcommand, or cog to enable")
    async def enable(self, ctx: CommieContext, *, target: str):
        """Re-enables a previously disabled command, subcommand, or cog"""
        await self._toggle(ctx, target, enabled=True)

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.hybrid_command(name="disable")
    @discord.app_commands.describe(target="The command, subcommand, or cog to disable")
    async def disable(self, ctx: CommieContext, *, target: str):
        """Disables a command, subcommand, or cog for this server"""
        await self._toggle(ctx, target, enabled=False)

    async def _toggle(self, ctx: CommieContext, target: str, *, enabled: bool) -> None:
        await ctx.defer()
        T = await ctx.get_locale()
        resolved = _resolve_target(self.bot, target)
        if resolved is None:
            raise commands.CommandError(T.get("errors.commandNotFound", target=target))
        kind, name, target_id = resolved

        if enabled:
            await self.bot.db.pull(table="guilds", id=ctx.guild.id, field="disabled", value=target_id)
        else:
            await self.bot.db.push(table="guilds", id=ctx.guild.id, field="disabled", value=target_id, unique=True)
        self._mutate_cache(ctx.guild.id, target_id, enabled)

        key = "success.commandEnabled" if enabled else "success.commandDisabled"
        await ctx.answer(T.get(key, name=name), type="success")
    
    @protected
    @commands.hybrid_command(name="prefix")
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.describe(prefix="The new prefix for the bot, or 'reset' to use the default one")
    async def prefix(self, ctx: CommieContext, *, prefix: str):
        """Sets a new prefix for the bot in this server"""
        await ctx.defer()
        T = await ctx.get_locale()
        if len(prefix) > 15:
            raise commands.CommandError(T.get("errors.prefixTooLong", max=15))
        if prefix.lower() == "default" or prefix == "reset":
            # Remove from database to save space cuz yeah
            await self.bot.db.delete(table="guilds", id=ctx.guild.id, field="prefix")
            await ctx.answer(T.get("success.prefixReset", prefix=ctx.clean_prefix), type="success")
        else:
            await self.bot.db.set(table="guilds", id=ctx.guild.id, path="prefix", value=prefix)
            await ctx.answer(T.get("success.prefixSet", prefix=prefix), type="success")

    @protected
    @commands.hybrid_command(name="language", aliases=["locale"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    async def language(self, ctx: CommieContext):
        """Sets a new language for the bot in this server"""
        try:
            T = await ctx.get_locale()
            v = BaseView(ctx=ctx, locale=T)
            v.add_item(LanguageMenu(ctx=ctx, locale=T))
            v.message = await ctx.answer(T.get("info.selectLanguage"), view=v, ephemeral=True, type=AnswerType.Ok)
        except Exception as e:
            await ctx.answer("An error occurred", type="error")
            raise e

async def setup(bot: CommieBot):
    await bot.add_cog(Configuration(bot))