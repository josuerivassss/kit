"""Cog: global command-error handling and cross-cutting gateway events.

Every uncaught command error funnels through `on_command_error`, ensuring a
single, consistent error-reply format regardless of which cog raised it.
"""
import discord
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext
from bcommie.logging_setup import get_logger

logger = get_logger(__name__)


class Events(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Emitted once the bot (or this shard) finishes its initial handshake."""
        logger.info("shard_ready", user=str(self.bot.user), shard_id=getattr(self.bot, "shard_id", None))

    @commands.Cog.listener()
    async def on_command_error(self, ctx: CommieContext, error: commands.CommandError):
        T = await ctx.get_locale()

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.answer(f"{T.get('errors.onCooldown')}", hint=T.get("errors.onCooldownHint", time=round(error.retry_after, 2)), type="error", deleteAfter=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.answer(f"{T.get('errors.missingArgument')}", hint=T.get("errors.missingArgumentHint", argument=error.param.name), type="error")
        elif isinstance(error, commands.UserNotFound):
            return await ctx.answer(f"{T.get('errors.userNotFound', user=error.argument)}", hint=T.get("errors.userNotFoundHint"), type="error")
        elif isinstance(error, commands.MemberNotFound):
            return await ctx.answer(f"{T.get('errors.memberNotFound', member=error.argument)}", hint=T.get("errors.memberNotFoundHint"), type="error")
        elif isinstance(error, commands.ChannelNotFound):
            return await ctx.answer(f"{T.get('errors.channelNotFound', channel=error.argument)}", hint=T.get("errors.channelNotFoundHint"), type="error")
        elif isinstance(error, commands.RoleNotFound):
            return await ctx.answer(f"{T.get('errors.roleNotFound', role=error.argument)}", hint=T.get("errors.roleNotFoundHint"), type="error")
        elif isinstance(error, commands.BadArgument):
            argument_name = ctx.current_parameter.name if ctx.current_parameter else "unknown"
            return await ctx.answer(f"{T.get('errors.badArgument')}", hint=T.get("errors.badArgumentHint", argument=argument_name), type="error")
            return
        elif isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            return await ctx.answer(f"{T.get('errors.missingPermissions')}", hint=T.get("errors.missingPermissionsHint", permissions=missing), type="error", bold=False)
        elif isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            return await ctx.answer(f"{T.get('errors.botMissingPermissions')}", hint=T.get("errors.botMissingPermissionsHint", permissions=missing), type="error", bold=False)
        elif isinstance(error, commands.NoPrivateMessage):
            return await ctx.answer(f"{T.get('errors.noDM')}", hint=T.get("errors.noDMHint"), type="error")
        elif isinstance(error, commands.CommandError):
            message = error.args[0] if error.args else T.get('errors.unexpectedError')
            hint = error.args[1] if len(error.args) > 1 else ''
            if hint:
                return await ctx.answer(f"{message}", hint=hint, type="error")
            else:
                return await ctx.answer(message, type="error")
        else:
            await ctx.answer(f"{T.get('errors.unexpectedError')}", hint=T.get("errors.unexpectedErrorHint"), type="error", deleteAfter=10)
            logger.exception(
                "unhandled_command_error",
                command=str(ctx.command),
                guild_id=ctx.guild.id if ctx.guild else None,
                exc_info=error,
            )

    @commands.Cog.listener()
    async def on_error(self, event_method: str, *args, **kwargs):
        """Emitted when an error occurs outside of command invocation."""
        logger.exception("unhandled_gateway_error", event=event_method)

    # -- reminder bookkeeping on guild/channel removal -----------------------

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Delete pending reminders scoped to a guild the bot was removed from."""
        try:
            reminders = await self.bot.sql.find(table="reminders", where={"guild_id": guild.id})
            for reminder in reminders:
                try:
                    await self.bot.sql.delete(table="reminders", id=reminder['id'])
                    reminders_cog = self.bot.get_cog('Reminders')
                    if reminders_cog and hasattr(reminders_cog, '_reminder_cache'):
                        reminders_cog._reminder_cache.pop(reminder['id'], None)
                except Exception:
                    logger.warning("reminder_cleanup_failed", reminder_id=reminder.get('id'))
        except Exception:
            logger.warning("guild_remove_reminder_sweep_failed", guild_id=guild.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.TextChannel):
        """Re-route or delete reminders whose target channel was deleted."""
        try:
            reminders = await self.bot.sql.find(
                table="reminders",
                where={"channel_id": channel.id, "reminded": False}
            )
            if not reminders:
                return
            system_channel = channel.guild.system_channel
            reminders_cog = self.bot.get_cog('Reminders')
            if system_channel:
                for reminder in reminders:
                    try:
                        await self.bot.sql.update(
                            table="reminders",
                            id=reminder['id'],
                            data={"channel_id": system_channel.id}
                        )
                        if reminders_cog and reminder['id'] in getattr(reminders_cog, '_reminder_cache', {}):
                            reminders_cog._reminder_cache[reminder['id']]['channel_id'] = system_channel.id
                    except Exception:
                        logger.warning("reminder_reroute_failed", reminder_id=reminder.get('id'))
            else:
                for reminder in reminders:
                    try:
                        await self.bot.sql.delete(table="reminders", id=reminder['id'])
                        if reminders_cog and hasattr(reminders_cog, '_reminder_cache'):
                            reminders_cog._reminder_cache.pop(reminder['id'], None)
                    except Exception:
                        logger.warning("reminder_cleanup_failed", reminder_id=reminder.get('id'))
        except Exception:
            logger.warning("channel_delete_reminder_sweep_failed", channel_id=channel.id)


async def setup(bot: CommieBot):
    await bot.add_cog(Events(bot))
