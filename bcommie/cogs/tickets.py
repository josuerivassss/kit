"""Ticket system: button-driven private threads with staff-role access,
one open ticket per user (enforced via thread-name convention, not a DB
table), and a .txt transcript generated on close via message history.

Opening a ticket goes through a modal (keyword + description) before the
thread is created, so staff get context immediately instead of waiting for
the user to explain themselves in chat.

No per-ticket record is persisted in Mongo -- the private thread itself
(named `ticket-{user_id}`) is the source of truth for "does this user
already have an open ticket", checked against `guild.threads` (already
cached by discord.py, no extra fetch needed). Only guild-level config
(staff role, welcome message, panel location) is stored, under
`guilds.tickets`, written only when an admin configures it.

The ticket channel doubles as the panel's location and the thread parent --
`interaction.channel` at click/modal-submit time already IS that channel,
so no channel id needs to be read back from config to create a thread.
`panel_channel_id`/`panel_message_id` exist solely to retire the previous
panel's message when a new one is posted: persistent views route by
custom_id, not by message, so an old, un-deleted panel message would keep
working even after a new one is created elsewhere.

GUILDS TABLE

"_id": Guild ID (int)
"tickets": {
    "enabled": bool,
    "staff_role_id": int | None,
    "welcome_message": str,
    "panel_channel_id": int | None,
    "panel_message_id": int | None,
}
"""
from __future__ import annotations

import io
import time
from typing import Any

import discord
from discord.ext import commands

from bcommie.help import send_help_group
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.kernel.context import AnswerType, CommieContext as _EventContext
from bcommie.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_TICKETS: dict[str, Any] = {
    "enabled": False,
    "staff_role_id": None,
    "welcome_message": "Welcome {user.mention}! Support will be with you shortly.",
    "panel_channel_id": None,
    "panel_message_id": None,
}

_CONFIG_CACHE_TTL = 15.0
_MAX_STAFF_AUTO_ADD = 50  # cap on how many staff-role members get thread.add_user() calls
_TRANSCRIPT_HISTORY_LIMIT = 2000
_KEYWORD_MAX_LENGTH = 100
_DESCRIPTION_MAX_LENGTH = 1000
_BANNER_IMAGE_URL = "https://i.imgur.com/k9zLycU.png"


def _thread_name(user_id: int) -> str:
    return f"ticket-{user_id}"

class TicketModal(discord.ui.Modal):
    """Collects a short keyword and a longer description before the
    thread is created, so staff have context from the first message."""

    def __init__(self, cog: "Tickets", title: str, keyword_label: str, keyword_placeholder: str,
                 description_label: str, description_placeholder: str):
        super().__init__(title=title, custom_id="tickets:modal")
        self.cog = cog
        self.keyword = discord.ui.TextInput(
            label=keyword_label, style=discord.TextStyle.short,
            max_length=_KEYWORD_MAX_LENGTH, placeholder=keyword_placeholder,
        )
        self.description = discord.ui.TextInput(
            label=description_label, style=discord.TextStyle.paragraph,
            max_length=_DESCRIPTION_MAX_LENGTH, placeholder=description_placeholder,
        )
        self.add_item(self.keyword)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_modal_submit(interaction, self.keyword.value, self.description.value)


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Open", style=discord.ButtonStyle.blurple, custom_id="tickets:open", emoji="\U0001f3ab")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.handle_open_button(interaction)


class TicketControlView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="tickets:close", emoji="\U0001f512")
    async def close_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.handle_close_button(interaction)


class Tickets(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot
        self._config_cache: dict[int, tuple[float, dict[str, Any]]] = {}

    async def cog_load(self):
        # Re-registered every process start so buttons/modal on old panel
        # messages keep routing correctly after a restart/redeploy.
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketControlView(self))

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        cached = self._config_cache.get(guild_id)
        if cached is not None and time.monotonic() - cached[0] < _CONFIG_CACHE_TTL:
            return cached[1]
        doc = await self.bot.db.get(table="guilds", id=guild_id, path="tickets") or {}
        config = {**DEFAULT_TICKETS, **doc}
        self._config_cache[guild_id] = (time.monotonic(), config)
        return config

    async def _update_config(self, guild_id: int, field: str, value: Any) -> None:
        await self.bot.db.set(table="guilds", id=guild_id, path=f"tickets.{field}", value=value)
        cached = self._config_cache.get(guild_id)
        config = dict(cached[1]) if cached else {**DEFAULT_TICKETS}
        config[field] = value
        self._config_cache[guild_id] = (time.monotonic(), config)

    async def _guild_language(self, guild_id: int) -> str:
        return await self.bot.db.get(table="guilds", id=guild_id, path="language") or self.bot.language.default_language

    def _existing_ticket(self, guild: discord.Guild, user_id: int) -> discord.Thread | None:
        return discord.utils.get(guild.threads, name=_thread_name(user_id), archived=False)

    # -- configuration commands ------------------------------------------------

    @commands.hybrid_group(name="ticket", aliases=["tickets"])
    async def ticket(self, ctx: CommieContext):
        """Ticket system configuration"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("ticket")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="channel")
    @discord.app_commands.describe(channel="The channel where the ticket panel is posted and threads are created under")
    async def ticket_channel(self, ctx: CommieContext, channel: discord.TextChannel):
        """Sets the ticket channel, retiring any previous panel and posting a new one"""
        await ctx.defer()
        T = await ctx.get_locale()
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.create_private_threads or not perms.send_messages_in_threads or not perms.embed_links:
            raise commands.CommandError(T.get("errors.ticketMissingPermissions"), T.get("errors.ticketMissingPermissionsHint"))

        config = await self._get_config(ctx.guild.id)
        await self._retire_previous_panel(ctx.guild, config)

        embed = discord.Embed(
            title=T.get("tickets.panelTitle"),
            description=T.get("tickets.panelDescription"),
            colour=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_image(url=_BANNER_IMAGE_URL)
        embed.set_footer(text="Commie Tickets", icon_url=self.bot.user.display_avatar.url)
        try:
            message = await channel.send(embed=embed, view=TicketPanelView(self))
        except (discord.Forbidden, discord.HTTPException):
            raise commands.CommandError(T.get("errors.ticketMissingPermissions"), T.get("errors.ticketMissingPermissionsHint"))

        await self._update_config(ctx.guild.id, "panel_channel_id", channel.id)
        await self._update_config(ctx.guild.id, "panel_message_id", message.id)
        await self._update_config(ctx.guild.id, "enabled", True)
        await ctx.answer(T.get("success.ticketChannelSet", channel=channel.mention), type="success")

    async def _retire_previous_panel(self, guild: discord.Guild, config: dict[str, Any]) -> None:
        """Deletes the previous panel message, if any -- persistent views
        route by custom_id, not by message, so a stale un-deleted panel
        would keep letting users open tickets from the old channel too."""
        old_channel_id, old_message_id = config.get("panel_channel_id"), config.get("panel_message_id")
        if not old_channel_id or not old_message_id:
            return
        old_channel = guild.get_channel(old_channel_id)
        if old_channel is None:
            try:
                old_channel = await guild.fetch_channel(old_channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        try:
            old_message = await old_channel.fetch_message(old_message_id)
            await old_message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass  # already gone or inaccessible -- nothing to retire

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="role")
    @discord.app_commands.describe(role="The staff role to ping and grant access to new ticket threads")
    async def ticket_role(self, ctx: CommieContext, role: discord.Role):
        """Sets the staff role for tickets"""
        await self._update_config(ctx.guild.id, "staff_role_id", role.id)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.ticketRoleSet", role=role.mention), type="success")
        if not role.permissions.manage_threads and len(role.members) > _MAX_STAFF_AUTO_ADD:
            await ctx.send(T.get("errors.ticketRoleTooLargeWarning", count=len(role.members)), delete_after=20)

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="message")
    @discord.app_commands.describe(text="Message shown when a ticket opens. Supports {user.mention}, {guild.name}, etc.")
    async def ticket_message(self, ctx: CommieContext, *, text: str):
        """Sets the welcome message posted inside new tickets"""
        T = await ctx.get_locale()
        if not (5 <= len(text) <= 1800):
            raise commands.CommandError(T.get("errors.ticketMessageLength"))
        await self._update_config(ctx.guild.id, "welcome_message", text)
        await ctx.answer(T.get("success.ticketMessageSet"), type="success")

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="enable", aliases=["on"])
    async def ticket_enable(self, ctx: CommieContext):
        """Re-enables tickets (after a channel is already configured)"""
        T = await ctx.get_locale()
        config = await self._get_config(ctx.guild.id)
        if not config["panel_channel_id"]:
            raise commands.CommandError(T.get("errors.ticketNotConfigured"), T.get("errors.ticketNotConfiguredHint"))
        await self._update_config(ctx.guild.id, "enabled", True)
        await ctx.answer(T.get("success.ticketEnabled"), type="success")

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="disable", aliases=["off"])
    async def ticket_disable(self, ctx: CommieContext):
        """Disables tickets without losing the saved configuration"""
        await self._update_config(ctx.guild.id, "enabled", False)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.ticketDisabled"), type="success")

    # -- ticket lifecycle ---------------------------------------------------

    async def handle_open_button(self, interaction: discord.Interaction) -> None:
        """Pre-checks before showing the modal -- no point asking the user
        to fill it out if tickets aren't enabled or they already have one."""
        T = self.bot.language.get_locale(await self._guild_language(interaction.guild_id))
        config = await self._get_config(interaction.guild_id)

        if not config["enabled"]:
            await interaction.response.send_message(T.get("errors.ticketNotConfigured"), ephemeral=True)
            return

        existing = self._existing_ticket(interaction.guild, interaction.user.id)
        if existing:
            await interaction.response.send_message(T.get("errors.ticketAlreadyOpen", channel=existing.mention), ephemeral=True)
            return

        modal = TicketModal(
            self,
            title=T.get("tickets.modalTitle"),
            keyword_label=T.get("tickets.modalKeywordLabel"),
            keyword_placeholder=T.get("tickets.modalKeywordPlaceholder"),
            description_label=T.get("tickets.modalDescriptionLabel"),
            description_placeholder=T.get("tickets.modalDescriptionPlaceholder"),
        )
        await interaction.response.send_modal(modal)

    async def handle_modal_submit(self, interaction: discord.Interaction, keyword: str, description: str) -> None:
        await interaction.response.defer(ephemeral=True)
        T = self.bot.language.get_locale(await self._guild_language(interaction.guild_id))
        config = await self._get_config(interaction.guild_id)

        # Re-check right before creating the thread -- guards the narrow
        # race window between the button pre-check and the modal submit.
        if not config["enabled"]:
            await interaction.followup.send(T.get("errors.ticketNotConfigured"), ephemeral=True)
            return
        existing = self._existing_ticket(interaction.guild, interaction.user.id)
        if existing:
            await interaction.followup.send(T.get("errors.ticketAlreadyOpen", channel=existing.mention), ephemeral=True)
            return

        parent = interaction.channel  # the panel's own channel doubles as the thread parent
        if not isinstance(parent, discord.TextChannel):
            await interaction.followup.send(T.get("errors.ticketNotConfigured"), ephemeral=True)
            return

        try:
            thread = await parent.create_thread(
                name=_thread_name(interaction.user.id),
                type=discord.ChannelType.private_thread,
                invitable=False,
                reason=f"Ticket opened by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(T.get("errors.ticketMissingPermissions"), ephemeral=True)
            return
        except discord.HTTPException:
            logger.warning("ticket_thread_creation_failed", guild_id=interaction.guild_id, user_id=interaction.user.id)
            await interaction.followup.send(T.get("errors.unexpectedError"), ephemeral=True)
            return

        await thread.add_user(interaction.user)
        await self._grant_staff_access(thread, interaction.guild, config)

        role_mention = f"<@&{config['staff_role_id']}>" if config["staff_role_id"] else ""
        content = " ".join(part for part in (interaction.user.mention, role_mention) if part)
        embed = await self._build_ticket_embed(interaction.guild, interaction.user, config["welcome_message"], keyword, description, T)

        message = await thread.send(content=content, embed=embed, view=TicketControlView(self),
                                     allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        try:
            await message.pin()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(T.get("success.ticketCreated", channel=thread.mention), ephemeral=True)

    async def _build_ticket_embed(self, guild: discord.Guild, user: discord.Member, template: str,
                                   keyword: str, description: str, locale) -> discord.Embed:
        fake_ctx = _EventContext.create_for_event(self.bot, author=user, guild=guild)
        rendered = await self.bot.toolkit.interpolation.render(template, fake_ctx)
        body = f"{rendered.content}\n\n**{locale.get('tickets.summaryLabel')}:** {keyword}\n\n**{locale.get('tickets.descriptionLabel')}:**\n{description}"
        embed = discord.Embed(title=locale.get("tickets.embedTitle"), description=body, colour=discord.Color.dark_red())
        embed.set_image(url=_BANNER_IMAGE_URL)
        embed.set_footer(text="Commie Tickets", icon_url=self.bot.user.display_avatar.url)
        return embed

    async def _grant_staff_access(self, thread: discord.Thread, guild: discord.Guild, config: dict[str, Any]) -> None:
        if not config["staff_role_id"]:
            return
        role = guild.get_role(config["staff_role_id"])
        if role is None:
            return
        if role.permissions.manage_threads:
            return
        members = role.members
        if len(members) > _MAX_STAFF_AUTO_ADD:
            logger.warning("ticket_staff_role_too_large_for_autoadd", guild_id=guild.id, role_id=role.id, count=len(members))
            return
        for member in members:
            try:
                await thread.add_user(member)
            except (discord.Forbidden, discord.HTTPException):
                continue

    async def handle_close_button(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        closed = await self._close_ticket(interaction.channel, interaction.user, interaction)
        if closed:
            T = self.bot.language.get_locale(await self._guild_language(interaction.guild_id))
            # await interaction.followup.send(T.get("tickets.ticketClosed"), ephemeral=True)

    @commands.hybrid_command(name="close")
    async def ticket_close(self, ctx: CommieContext):
        """Closes the current ticket (usable inside a ticket thread)"""
        await ctx.defer(ephemeral=True)
        T = await ctx.get_locale()
        m = await ctx.answer(T.get("tickets.tryingToClose"), type="info")
        closed = await self._close_ticket(ctx.channel, ctx.author, None)
        if closed:
            if ctx.interaction:
                await m.edit(content=T.get("tickets.ticketClosed") + CommieEmojis.Heart)
        else:
            await m.edit(content=T.get("tickets.ticketCloseFailed") + CommieEmojis.Crying)

    async def _close_ticket(self, channel: discord.abc.Messageable, closer: discord.abc.User, interaction: discord.Interaction | None) -> bool:
        guild_id = channel.guild.id if hasattr(channel, "guild") else None
        T = self.bot.language.get_locale(await self._guild_language(guild_id) if guild_id else self.bot.language.default_language)

        if not isinstance(channel, discord.Thread) or not channel.name.startswith("ticket-"):
            await self._respond(interaction, channel, T.get("errors.notATicket") + " " + CommieEmojis.Crying)
            return False

        config = await self._get_config(channel.guild.id)
        opener_part = channel.name.removeprefix("ticket-")
        opener_id = int(opener_part) if opener_part.isdigit() else None
        is_opener = opener_id == closer.id
        has_staff_role = config["staff_role_id"] and any(r.id == config["staff_role_id"] for r in getattr(closer, "roles", []))
        has_manage = getattr(closer, "guild_permissions", None) and closer.guild_permissions.manage_threads
        if not (is_opener or has_staff_role or has_manage):
            await self._respond(interaction, channel, T.get("errors.unauthorized") + " " + CommieEmojis.Crying)
            return False

        transcript = await self._build_transcript(channel)
        try:
            await channel.send(T.get("tickets.closingNotice", closer=str(closer)))
            await channel.send(file=transcript)
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await channel.edit(archived=True, locked=True, reason=f"Ticket closed by {closer} ({closer.id})")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("ticket_close_failed", channel_id=channel.id)
            return False
        return True

    async def _build_transcript(self, channel: discord.Thread) -> discord.File:
        lines = []
        async for message in channel.history(limit=_TRANSCRIPT_HISTORY_LIMIT, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.content or ""
            if message.attachments:
                content += " " + " ".join(a.url for a in message.attachments)
            lines.append(f"[{timestamp}] {message.author} ({message.author.id}): {content}")
        buffer = io.BytesIO("\n".join(lines).encode("utf-8"))
        return discord.File(buffer, filename=f"{channel.name}-transcript.txt")

    async def _respond(self, interaction: discord.Interaction | None, channel: discord.abc.Messageable, text: str) -> None:
        if interaction is not None:
            await interaction.followup.send("**" + text + "**", ephemeral=True)
        else:
            await channel.send(text, delete_after=8)


async def setup(bot: CommieBot):
    await bot.add_cog(Tickets(bot))