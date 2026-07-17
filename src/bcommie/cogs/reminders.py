"""Reminders cog: create, list, edit, remove reminders; per-user timezones.

Schema (`reminders`, `user_timezones`) is owned by migrations/0001_init.sql,
not created at runtime — a v1 -> v2 change that keeps schema changes
reviewable and consistent across every shard/process.
"""
from discord.ext import commands, tasks
from bcommie.help import send_help_group
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.ui.confirmator import Confirmator
from typing import Optional
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import discord
import asyncio
import time
import random

_CLEANUP_EVERY_N_CYCLES = 20

class Reminders(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot
        self._reminder_cache = {}
        self._cache_loaded = False
        self._cache_sync_lock = asyncio.Lock()
        self._cleanup_cycle_counter = 0
        self._cancelled_ids: set[str] = set()

    @commands.hybrid_group(name="reminders", aliases=["reminder", "remind"])
    async def reminders(self, ctx: CommieContext):
        """Manage your reminders"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("reminders")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    async def cog_load(self):
        self.check_reminders.start()

    async def cog_unload(self):
        self.check_reminders.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._reload_cache()

    async def _reload_cache(self):
        async with self._cache_sync_lock:
            try:
                reminders = await self.bot.sql.find(
                    table="reminders",
                    where={"reminded": False},
                    order_by="remind_at ASC"
                )
                self._reminder_cache.clear()
                for reminder in reminders:
                    self._reminder_cache[reminder['id']] = reminder
                self._cache_loaded = True
            except Exception:
                self._cache_loaded = False

    def _generate_id(self) -> int:
        return int(time.time() * 1000000 + random.randint(0, 999)) % (2**63 - 1)

    def _get_utc(self) -> ZoneInfo | timezone:
        try:
            return ZoneInfo('UTC')
        except Exception:
            return timezone.utc

    async def _get_user_timezone(self, user_id: int) -> ZoneInfo | timezone:
        try:
            tz_data = await self.bot.sql.get(table="user_timezones", id=user_id, columns=["timezone"])
            if tz_data and tz_data.get('timezone'):
                try:
                    return ZoneInfo(tz_data['timezone'])
                except Exception:
                    pass
        except Exception:
            pass
        return self._get_utc()

    def _parse_time(self, time_str: str, user_tz: ZoneInfo | timezone) -> Optional[datetime]:
        time_str = time_str.strip()
        from bcommie.timeparse import load as parse_time
        ms = parse_time(time_str)
        if ms is not None:
            seconds = ms / 1000
            if seconds < 60 or seconds > 31536000:
                return None
            return datetime.now(self._get_utc()) + timedelta(seconds=seconds)
        try:
            if ' ' in time_str:
                naive_dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
                localized = naive_dt.replace(tzinfo=user_tz)
                return localized.astimezone(self._get_utc())
            elif ':' in time_str:
                time_part = datetime.strptime(time_str, '%H:%M').time()
                now = datetime.now(user_tz)
                today_dt = datetime.combine(now.date(), time_part, tzinfo=user_tz)
                if today_dt > now:
                    return today_dt.astimezone(self._get_utc())
                else:
                    tomorrow_dt = today_dt + timedelta(days=1)
                    return tomorrow_dt.astimezone(self._get_utc())
            else:
                return None
        except Exception:
            return None

    async def _auto_cleanup(self):
        try:
            await self.bot.sql.execute("DELETE FROM reminders WHERE reminded = TRUE")
        except Exception:
            pass

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        if not self._cache_loaded:
            return
        try:
            now = datetime.now(self._get_utc())
            triggered = []
            async with self._cache_sync_lock:
                for reminder_id, reminder in list(self._reminder_cache.items()):
                    try:
                        remind_at = reminder['remind_at']
                        if isinstance(remind_at, str):
                            remind_at = datetime.fromisoformat(remind_at.replace('Z', '+00:00'))
                        if isinstance(remind_at, datetime):
                            if remind_at.tzinfo is None:
                                remind_at = remind_at.replace(tzinfo=self._get_utc())
                            if remind_at <= now:
                                triggered.append(reminder)
                                del self._reminder_cache[reminder_id]
                    except Exception:
                        pass

            if triggered:
                await asyncio.gather(*[self._send_reminder(r) for r in triggered], return_exceptions=True)

            self._cleanup_cycle_counter += 1
            if self._cleanup_cycle_counter >= _CLEANUP_EVERY_N_CYCLES:
                self._cleanup_cycle_counter = 0
                asyncio.create_task(self._auto_cleanup())
        except Exception:
            pass

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    async def _send_reminder(self, reminder: dict):
        still_exists = await self.bot.sql.get(table="reminders", id=reminder['id'])
        if not still_exists:
            return
        try:
            channel = self.bot.get_channel(reminder['channel_id'])
            if not channel:
                await self.bot.sql.delete(table="reminders", id=reminder['id'])
                return
            if isinstance(channel, discord.TextChannel):
                perms = channel.permissions_for(channel.guild.me)
                if not perms.send_messages or not perms.embed_links:
                    await self.bot.sql.delete(table="reminders", id=reminder['id'])
                    return
            user = self.bot.get_user(reminder['user_id'])
            mention = user.mention if user else f"<@{reminder['user_id']}>"
            locale = self.bot.language.get_locale(self.bot.language.default_language)
            if hasattr(channel, 'guild') and channel.guild:
                try:
                    lang = await self.bot.db.get(table="guilds", id=channel.guild.id, path="language")
                    if lang:
                        locale = self.bot.language.get_locale(lang)
                except Exception:
                    pass
            embed = discord.Embed(
                title=locale.get("reminders.embed.title") + " " + CommieEmojis.Clock,
                description=reminder['message'],
                color=discord.Color.dark_red(),
                timestamp=datetime.now(self._get_utc())
            )
            embed.set_footer(text=f"ID: {reminder['id']}")
            await channel.send(mention, embed=embed)
            await self.bot.sql.delete(table="reminders", id=reminder['id'])
        except Exception:
            try:
                await self.bot.sql.delete(table="reminders", id=reminder['id'])
            except Exception:
                pass

    async def _add_reminder(self, ctx: CommieContext, time: str, message: str, channel: Optional[discord.TextChannel]):
        T = await ctx.get_locale()
        message = message.strip() if message else ""
        if not message or len(message) > 500:
            raise commands.CommandError(T.get("reminders.add.message_too_long"))
        user_tz = await self._get_user_timezone(ctx.author.id)
        remind_at = self._parse_time(time, user_tz)
        if not remind_at:
            raise commands.CommandError(T.get("reminders.add.invalid_time"))
        if remind_at <= datetime.now(self._get_utc()):
            raise commands.CommandError(T.get("reminders.add.future_only"))
        target_channel = channel or ctx.channel
        if isinstance(target_channel, discord.TextChannel):
            perms = target_channel.permissions_for(ctx.guild.me)
            if not perms.send_messages or not perms.embed_links:
                raise commands.CommandError(T.get("reminders.add.no_permissions", channel=target_channel.mention))
        active_count = len(await self.bot.sql.find(table="reminders", where={"user_id": ctx.author.id, "reminded": False}))
        if active_count >= 10:
            raise commands.CommandError(T.get("reminders.add.limit_reached"))
        reminder_id = self._generate_id()
        reminder_data = {
            "user_id": ctx.author.id,
            "guild_id": ctx.guild.id,
            "channel_id": target_channel.id,
            "message": message,
            "remind_at": remind_at,
            "reminded": False,
            "created_at": datetime.now(self._get_utc())
        }
        await self.bot.sql.set(table="reminders", id=reminder_id, data=reminder_data)
        reminder_data['id'] = reminder_id
        async with self._cache_sync_lock:
            self._reminder_cache[reminder_id] = reminder_data
        timestamp_discord = int(remind_at.timestamp())
        msg = T.get("reminders.add.success", date=f"<t:{timestamp_discord}:F>", relative=f"<t:{timestamp_discord}:R>")
        await ctx.answer(msg, type="success")

    @reminders.command(name="add")
    @discord.app_commands.describe(time="Time (e.g: 30m, 2h, 1d, 14:30)", message="Reminder message", channel="Target channel (optional)")
    @commands.cooldown(1, 45, commands.BucketType.member)
    async def reminder_add(self, ctx: CommieContext, time: str, *, message: str, channel: Optional[discord.TextChannel] = None):
        """Add a new reminder"""
        await ctx.defer()
        await self._add_reminder(ctx, time, message, channel)

    @reminders.command(name="list")
    @discord.app_commands.describe(limit="Number to show (1-25)")
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def reminder_list(self, ctx: CommieContext, limit: int = 10):
        """Show your active reminders"""
        await ctx.defer()
        T = await ctx.get_locale()
        limit = min(max(limit, 1), 25)
        reminders = await self.bot.sql.find(
            table="reminders",
            where={"user_id": ctx.author.id, "reminded": False},
            order_by="remind_at ASC",
            limit=limit
        )
        if not reminders:
            raise commands.CommandError(T.get("reminders.list.empty"))
        embed = discord.Embed(title=T.get("reminders.list.title"), color=discord.Color.dark_red(), timestamp=datetime.now(self._get_utc()))
        for reminder in reminders:
            remind_at = reminder['remind_at']
            if isinstance(remind_at, str):
                remind_at = datetime.fromisoformat(remind_at.replace('Z', '+00:00'))
            if isinstance(remind_at, datetime):
                if remind_at.tzinfo is None:
                    remind_at = remind_at.replace(tzinfo=self._get_utc())
                timestamp = int(remind_at.timestamp())
                embed.add_field(
                    name=f"ID: {reminder['id']}",
                    value=f"<t:{timestamp}:F> · <t:{timestamp}:R>",
                    inline=False
                )
        embed.set_footer(text=f"Total: {len(reminders)}")
        await ctx.send(embed=embed)

    @reminders.command(name="remove")
    @discord.app_commands.describe(reminder_id="ID of the reminder to remove")
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def reminder_remove(self, ctx: CommieContext, reminder_id: int):
        """Remove a reminder"""
        await ctx.defer()
        T = await ctx.get_locale()
        reminder = await self.bot.sql.get(table="reminders", id=reminder_id)
        if not reminder:
            raise commands.CommandError(T.get("reminders.remove.not_found"))
        if reminder['user_id'] != ctx.author.id:
            raise commands.CommandError(T.get("reminders.remove.not_owner"))
        await self.bot.sql.delete(table="reminders", id=reminder_id)
        async with self._cache_sync_lock:
            self._reminder_cache.pop(reminder_id, None)
            self._cancelled_ids.add(str(reminder_id))
        await ctx.answer(T.get("reminders.remove.success"), type="success")

    @reminders.command(name="edit")
    @discord.app_commands.describe(reminder_id="ID to edit", time="New time (optional)", message="New message (optional)")
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def reminder_edit(self, ctx: CommieContext, reminder_id: int, time: Optional[str] = None, message: Optional[str] = None):
        """Edit a reminder"""
        await ctx.defer()
        T = await ctx.get_locale()
        reminder = await self.bot.sql.get(table="reminders", id=reminder_id)
        if not reminder:
            raise commands.CommandError(T.get("reminders.edit.not_found"))
        if reminder['user_id'] != ctx.author.id:
            raise commands.CommandError(T.get("reminders.remove.not_owner"))
        if reminder['reminded']:
            raise commands.CommandError(T.get("reminders.edit.already_completed"))
        update_data = {}
        if time:
            user_tz = await self._get_user_timezone(ctx.author.id)
            remind_at = self._parse_time(time, user_tz)
            if not remind_at or remind_at <= datetime.now(self._get_utc()):
                raise commands.CommandError(T.get("reminders.add.invalid_time"))
            update_data['remind_at'] = remind_at
        if message:
            message = message.strip()
            if not message or len(message) > 500:
                raise commands.CommandError(T.get("reminders.add.message_too_long"))
            update_data['message'] = message
        if not update_data:
            raise commands.CommandError(T.get("reminders.edit.no_fields"))
        await self.bot.sql.update(table="reminders", id=reminder_id, data=update_data)
        async with self._cache_sync_lock:
            if reminder_id in self._reminder_cache:
                self._reminder_cache[reminder_id].update(update_data)
        await ctx.answer(T.get("reminders.edit.success"), type="success")

    @reminders.command(name="prune")
    @commands.cooldown(1, 10, commands.BucketType.member)
    async def reminder_prune(self, ctx: CommieContext):
        """Remove all your active reminders"""
        await ctx.defer()
        T = await ctx.get_locale()

        reminders_to_delete = await self.bot.sql.find(
            table="reminders",
            where={"user_id": ctx.author.id, "reminded": False}
        )
        if not reminders_to_delete:
            raise commands.CommandError(T.get("reminders.prune.empty"))

        ids_to_delete = [r['id'] for r in reminders_to_delete]

        async def confirm(interaction: discord.Interaction):
            await self.bot.sql.bulk_delete(table="reminders", ids=ids_to_delete)
            async with self._cache_sync_lock:
                for reminder_id in ids_to_delete:
                    self._reminder_cache.pop(reminder_id, None)
                    self._cancelled_ids.add(str(reminder_id))
            await ctx.answer(T.get("reminders.prune.success", count=len(ids_to_delete)), type="success")

        async def cancel(_):
            await ctx.answer(T.get("confirmator.cancelled"), type="info")

        embed = discord.Embed(
            title=T.get("confirmator.title"),
            description=T.get("reminders.prune.confirmPrune", count=len(ids_to_delete)),
            color=discord.Color.red()
        )
        view = Confirmator(ctx=ctx, locale=T, on_confirm=confirm, on_cancel=cancel)
        view.message = await ctx.send(embed=embed, view=view)

    @reminders.command(name="timezone")
    @discord.app_commands.describe(timezone="IANA timezone (e.g: America/Mexico_City)")
    @commands.cooldown(1, 2, commands.BucketType.member)
    async def reminder_timezone(self, ctx: CommieContext, *, timezone: str):
        """Set your timezone for reminders"""
        await ctx.defer()
        T = await ctx.get_locale()
        try:
            user_tz = ZoneInfo(timezone)
        except Exception:
            raise commands.CommandError(T.get("reminders.timezone.invalid"))
        await self.bot.sql.set(
            table="user_timezones",
            id=ctx.author.id,
            data={"timezone": timezone, "updated_at": datetime.now(self._get_utc())}
        )
        current_time = datetime.now(user_tz)
        await ctx.answer(
            T.get("reminders.timezone.success", timezone=timezone, time=current_time.strftime("%Y-%m-%d %H:%M:%S")),
            type="success"
        )


async def setup(bot: CommieBot):
    await bot.add_cog(Reminders(bot))