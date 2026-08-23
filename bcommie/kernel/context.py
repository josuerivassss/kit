"""Extended discord.py Context: localized/formatted replies + template rendering."""
from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bcommie.kernel.emojis import CommieEmojis
from bcommie.locale import Locale

if TYPE_CHECKING:
    from bcommie.interpolation.render_result import RenderResult
    from bcommie.kernel.bot import CommieBot


class AnswerType(StrEnum):
    Info = "info"
    Error = "error"
    Ok = "success"


class CommieContext(commands.Context):
    """`commands.Context` subclass adding localization, formatted replies, and
    template rendering shared by every cog."""

    bot: CommieBot

    async def get_language(self) -> str:
        """Resolve the effective language for this context (guild setting, or default)."""
        if self.guild is None:
            return self.bot.language.default_language
        lang = await self.bot.db.get(table="guilds", id=self.guild.id, path="language")
        return lang or self.bot.language.default_language

    async def get_locale(self) -> Locale:
        """Load the Locale object for `get_language()`."""
        return self.bot.language.get_locale(await self.get_language())

    async def think(self, *, emoji: bool = True, typing: bool = True) -> None:
        """Signals a response is coming. Interactions get `defer()`; prefix
        messages have no such state, so instead get a clock reaction and/or
        a typing indicator. Each option is attempted independently -- one
        failing (e.g. missing permissions) never blocks the other."""
        if self.interaction is not None:
            try:
                await self.defer()
            except discord.HTTPException:
                pass
            return
        if emoji:
            try:
                await self.message.add_reaction("\u23f0")
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        if typing:
            try:
                await self.channel.trigger_typing()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    async def answer(
        self,
        message: str,
        type: AnswerType = AnswerType.Error,
        emoji: bool | discord.Emoji = True,
        ephemeral: bool = True,
        deleteAfter: int | None = None,
        bold: bool = True,
        view: discord.ui.View | None = None,
        hint: str | None = None,
    ) -> discord.Message:
        """Send a consistently formatted status reply (success/error/info)."""
        if bold:
            message = f"**{message}**"
        if emoji:
            if isinstance(emoji, discord.Emoji):
                message = f"{message} {emoji}"
            else:
                icons = {AnswerType.Ok: CommieEmojis.Heart, AnswerType.Error: CommieEmojis.Crying, AnswerType.Info: CommieEmojis.Idea}
                message = f"{message} {icons.get(type, '')}"
        if hint:
            message = f"{message}\n-# {hint}"
        return await self.send(message, ephemeral=ephemeral, view=view, delete_after=deleteAfter)

    async def render(self, template: str) -> RenderResult:
        """Run `template` through the bot's InterpolationEngine."""
        if not hasattr(self.bot.toolkit, "interpolation"):
            raise RuntimeError("Interpolation engine not initialized on bot")
        return await self.bot.toolkit.interpolation.render(template, self)

    async def send_render(
        self,
        template: str | None = None,
        result: RenderResult | None = None,
        ephemeral: bool = False,
        delete_after: int | None = None,
        view: discord.ui.View | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
    ) -> discord.Message:
        """Render (or accept a pre-rendered) template and send content/embeds/reactions."""
        if result is None:
            if template is None:
                raise ValueError("Either 'template' or 'result' must be provided")
            result = await self.render(template)

        content = result.content.strip() if result.content else None
        if not content and not result.embeds:
            content = "\u200b"

        sent = await self.send(
            content=content,
            embeds=result.embeds[:10],
            view=view,
            ephemeral=ephemeral,
            delete_after=delete_after,
            allowed_mentions=allowed_mentions or discord.AllowedMentions.none(),
        )
        if result.emojis and not ephemeral:
            for reaction in result.emojis[:20]:
                try:
                    await sent.add_reaction(reaction)
                except discord.HTTPException:
                    continue
        return sent

    @classmethod
    def create_for_event(
        cls,
        bot: CommieBot,
        author: discord.Member | discord.User,
        guild: discord.Guild | None = None,
        channel: discord.abc.Messageable | None = None,
    ) -> CommieContext:
        """Build a minimal context-like object for gateway events (e.g. member join),
        so the same `render`/`send_render` machinery works outside of commands."""
        fake_ctx = cls.__new__(cls)
        fake_ctx.bot = bot
        fake_ctx.author = author
        fake_ctx.guild = guild or (author.guild if isinstance(author, discord.Member) else None)
        fake_ctx.channel = channel
        fake_ctx.message = None
        fake_ctx.command = None
        fake_ctx.prefix = None
        return fake_ctx
