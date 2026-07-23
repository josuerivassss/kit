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
(parent channel, staff role, welcome message) is stored, under
`guilds.tickets`, written only when an admin configures it.

Discord threads have no `topic` field (unlike text channels) -- the
keyword/description summary is pinned to the thread instead, as the
closest functional equivalent.

GUILDS TABLE

"_id": Guild ID (int)
"tickets": {
    "enabled": bool,
    "parent_channel_id": int | None,
    "staff_role_id": int | None,
    "welcome_message": str,
}
"""
from __future__ import annotations

import io
import time
from typing import Any

import discord
from discord.ext import commands

from bcommie.kernel import CommieBot, CommieContext
from bcommie.kernel.context import CommieContext as _EventContext
from bcommie.logging_setup import get_logger

logger = get_logger(__name__)

DEFAULT_TICKETS: dict[str, Any] = {
    "enabled": False,
    "parent_channel_id": None,
    "staff_role_id": None,
    "welcome_message": "Welcome {user.mention}! Support will be with you shortly.",
}

_CONFIG_CACHE_TTL = 15.0
_MAX_STAFF_AUTO_ADD = 50  # cap on how many staff-role members get thread.add_user() calls
_TRANSCRIPT_HISTORY_LIMIT = 2000
_KEYWORD_MAX_LENGTH = 100
_DESCRIPTION_MAX_LENGTH = 1000


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

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.blurple, custom_id="tickets:open", emoji="\U0001f3ab")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.cog.handle_open_button(interaction)


class TicketControlView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="tickets:close", emoji="\U0001f512")
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

    @commands.hybrid_group(name="ticket")
    @commands.has_permissions(manage_guild=True)
    async def ticket(self, ctx: CommieContext):
        """Ticket system configuration"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="parent")
    @discord.app_commands.describe(channel="The text channel under which ticket threads are created")
    async def ticket_parent(self, ctx: CommieContext, channel: discord.TextChannel):
        """Sets the parent channel for ticket threads"""
        await ctx.defer()
        T = await ctx.get_locale()
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.create_private_threads or not perms.send_messages_in_threads:
            raise commands.CommandError(T.get("errors.ticketMissingPermissions"), T.get("errors.ticketMissingPermissionsHint"))
        await self._update_config(ctx.guild.id, "parent_channel_id", channel.id)
        await ctx.answer(T.get("success.ticketParentSet", channel=channel.mention), type="success")

    @commands.has_permissions(manage_guild=True)
    @ticket.command(name="role")
    @discord.app_commands.describe(role="The staff role to ping and grant access to new ticket threads")
    async def ticket_role(self, ctx: CommieContext, role: discord.Role):
        """Sets the staff role for tickets"""
        await self._update_config(ctx.guild.id, "staff_role_id", role.id)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.ticketRoleSet", role=role.mention), type="success")
        # Proactive warning at setup time -- better than silently failing to
        # add members on every future ticket for a role this size.
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
    @ticket.command(name="panel")
    @discord.app_commands.describe(channel="Channel to post the ticket panel in (defaults to here)")
    async def ticket_panel(self, ctx: CommieContext, channel: discord.TextChannel = None):
        """Posts the ticket-opening panel"""
        await ctx.defer()
        T = await ctx.get_locale()
        config = await self._get_config(ctx.guild.id)
        if not config["parent_channel_id"]:
            raise commands.CommandError(T.get("errors.ticketNotConfigured"), T.get("errors.ticketNotConfiguredHint"))
        target = channel or ctx.channel
        embed = discord.Embed(
            title=T.get("tickets.panelTitle"),
            description=T.get("tickets.panelDescription"),
            colour=discord.Color.dark_red(),
        )
        await target.send(embed=embed, view=TicketPanelView(self))
        await self._update_config(ctx.guild.id, "enabled", True)
        await ctx.answer(T.get("success.ticketPanelPosted", channel=target.mention), type="success")

    # -- ticket lifecycle ---------------------------------------------------

    async def handle_open_button(self, interaction: discord.Interaction) -> None:
        """Pre-checks before showing the modal -- no point asking the user
        to fill it out if tickets aren't configured or they already have one."""
        T = self.bot.language.get_locale(await self._guild_language(interaction.guild_id))
        config = await self._get_config(interaction.guild_id)

        if not config["enabled"] or not config["parent_channel_id"]:
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
        if not config["enabled"] or not config["parent_channel_id"]:
            await interaction.followup.send(T.get("errors.ticketNotConfigured"), ephemeral=True)
            return
        existing = self._existing_ticket(interaction.guild, interaction.user.id)
        if existing:
            await interaction.followup.send(T.get("errors.ticketAlreadyOpen", channel=existing.mention), ephemeral=True)
            return

        parent = interaction.guild.get_channel(config["parent_channel_id"])
        if parent is None:
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
            await message.pin()  # closest available substitute for a thread "topic"
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(T.get("success.ticketCreated", channel=thread.mention), ephemeral=True)

    async def _build_ticket_embed(self, guild: discord.Guild, user: discord.Member, template: str,
                                   keyword: str, description: str, locale) -> discord.Embed:
        fake_ctx = _EventContext.create_for_event(self.bot, author=user, guild=guild)
        rendered = await self.bot.toolkit.interpolation.render(template, fake_ctx)
        body = f"{rendered.content}\n\n**{locale.get('tickets.summaryLabel')}:** {keyword}\n\n**{locale.get('tickets.descriptionLabel')}:**\n{description}"
        embed = discord.Embed(title=locale.get("tickets.embedTitle"), description=body, colour=discord.Color.dark_red())
        return embed

    async def _grant_staff_access(self, thread: discord.Thread, guild: discord.Guild, config: dict[str, Any]) -> None:
        if not config["staff_role_id"]:
            return
        role = guild.get_role(config["staff_role_id"])
        if role is None:
            return
        # "Manage Threads" already grants visibility into every private
        # thread in the channel -- no per-member invite needed, and no
        # size limit to worry about either.
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
        await self._close_ticket(interaction.channel, interaction.user, interaction)

    @commands.hybrid_command(name="close")
    async def ticket_close(self, ctx: CommieContext):
        """Closes the current ticket (usable inside a ticket thread)"""
        await ctx.defer(ephemeral=True)
        await self._close_ticket(ctx.channel, ctx.author, None)

    async def _close_ticket(self, channel: discord.abc.Messageable, closer: discord.abc.User, interaction: discord.Interaction | None) -> None:
        guild_id = channel.guild.id if hasattr(channel, "guild") else None
        T = self.bot.language.get_locale(await self._guild_language(guild_id) if guild_id else self.bot.language.default_language)

        if not isinstance(channel, discord.Thread) or not channel.name.startswith("ticket-"):
            await self._respond(interaction, channel, T.get("errors.notATicket"))
            return

        config = await self._get_config(channel.guild.id)
        opener_part = channel.name.removeprefix("ticket-")
        opener_id = int(opener_part) if opener_part.isdigit() else None
        is_opener = opener_id == closer.id
        has_staff_role = config["staff_role_id"] and any(r.id == config["staff_role_id"] for r in getattr(closer, "roles", []))
        has_manage = getattr(closer, "guild_permissions", None) and closer.guild_permissions.manage_threads
        if not (is_opener or has_staff_role or has_manage):
            await self._respond(interaction, channel, T.get("errors.unauthorized"))
            return

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
            await interaction.followup.send(text, ephemeral=True)
        else:
            await channel.send(text, delete_after=8)


async def setup(bot: CommieBot):
    await bot.add_cog(Tickets(bot))