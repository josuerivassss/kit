"""Greetings cog: templated welcome/leave messages rendered via the interpolation engine."""
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext
from bcommie.help import send_help_group
import discord

"""
GUILDS TABLE

"_id": Guild ID (int)
"welcome": {
    "enabled": bool,
    "channel": int,
    "message": str,
},
"leave": {
    "enabled": bool,
    "channel": int,
    "message": str,
    }
"""

class Greetings(commands.Cog):

    def __init__(self, bot: CommieBot):
        self.bot = bot
        self.default_welcome_message = "Welcome to the server, {user.mention}!"
        self.default_leave_message = "Goodbye, {user.mention}!"
    
    @commands.hybrid_group(name="welcome")
    async def welcome(self, ctx: CommieContext):
        """Welcome message related commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("welcome")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())
    
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @welcome.command(name="enable", aliases=["on"])
    async def welcome_enable(self, ctx: CommieContext):
        """Enables welcome messages"""
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="welcome.enabled", value=True)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.welcomeEnabled"), type="success")
    
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @welcome.command(name="disable", aliases=["off"])
    async def welcome_disable(self, ctx: CommieContext):
        """Disables welcome messages"""
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="welcome.enabled", value=False)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.welcomeDisabled"), type="success")
    
    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @welcome.command(name="channel")
    async def welcome_channel(self, ctx: CommieContext, channel: discord.TextChannel):
        """Sets the welcome message channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not channel.permissions_for(ctx.guild.me).send_messages:
            raise commands.CommandError(T.get("errors.cantSeeChannel"), T.get("errors.cantSeeChannelHint"))
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="welcome.channel", value=channel.id)
        # we enable this system by default after using this command to avoid confusion
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="welcome.enabled", value=True)
        await ctx.answer(T.get("success.welcomeChannelSet", channel=channel.mention), type="success")
    
    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @welcome.command(name="message", extras={"supports_placeholders": True})
    async def welcome_message(self, ctx: CommieContext, *, message: str):
        """Sets the welcome message. Use {user} to mention the new member."""
        await ctx.defer()
        T = await ctx.get_locale()
        if 5 > len(message):
            raise commands.CommandError(T.get("errors.welcomeMessageTooShort"), T.get("errors.welcomeMessageTooShortHint"))
        if 1800 < len(message):
            raise commands.CommandError(T.get("errors.welcomeMessageTooLong"), T.get("errors.welcomeMessageTooLongHint"))
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="welcome.message", value=message)
        await ctx.answer(T.get("success.welcomeMessageSet"), type="success")
    
    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @welcome.command(name="preview", extras={"supports_placeholders": True})
    async def welcome_preview(self, ctx: CommieContext):
        """Previews the welcome message with your user as the new member."""
        guild_data = await self.bot.db.get(table="guilds", id=ctx.guild.id)
        m = self.default_leave_message
        if guild_data and guild_data.get("welcome") and guild_data["welcome"].get("message"):
            m = guild_data["welcome"]["message"]
        await ctx.send_render(m) # Using interpolation system

    @commands.hybrid_group(name="leave")
    async def leave(self, ctx: CommieContext):
        """Leave message related commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("leave")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())
    
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @leave.command(name="enable", aliases=["on"])
    async def leave_enable(self, ctx: CommieContext):
        """Enables leave messages"""
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="leave.enabled", value=True)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.leaveEnabled"), type="success")
    
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @leave.command(name="disable", aliases=["off"])
    async def leave_disable(self, ctx: CommieContext):
        """Disables leave messages"""
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="leave.enabled", value=False)
        T = await ctx.get_locale()
        await ctx.answer(T.get("success.leaveDisabled"), type="success")

    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.describe(channel="The channel to send leave messages in")
    @leave.command(name="channel")
    async def leave_channel(self, ctx: CommieContext, channel: discord.TextChannel):
        """Sets the leave message channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not channel.permissions_for(ctx.guild.me).send_messages:
            raise commands.CommandError(T.get("errors.cantSeeChannel"), T.get("errors.cantSeeChannelHint"))
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="leave.channel", value=channel.id)
        # we enable this system by default after using this command to avoid confusion
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="leave.enabled", value=True)
        await ctx.answer(T.get("success.leaveChannelSet", channel=channel.mention), type="success")
    
    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.describe(message="The message to send when a member leaves.")
    @leave.command(name="message", extras={"supports_placeholders": True})
    async def leave_message(self, ctx: CommieContext, *, message: str):
        """Sets the leave message. Use {user} to mention the member who left."""
        await ctx.defer()
        T = await ctx.get_locale()
        if 5 > len(message):
            raise commands.CommandError(T.get("errors.leaveMessageTooShort"), T.get("errors.leaveMessageTooShortHint"))
        if 1800 < len(message):
            raise commands.CommandError(T.get("errors.leaveMessageTooLong"), T.get("errors.leaveMessageTooLongHint"))
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path="leave.message", value=message)
        await ctx.answer(T.get("success.leaveMessageSet"), type="success")

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @leave.command(name="preview", extras={"supports_placeholders": True})
    async def leave_preview(self, ctx: CommieContext):
        """Previews the leave message with your user as the member who left."""
        # T = await ctx.get_locale()
        guild_data = await self.bot.db.get(table="guilds", id=ctx.guild.id)
        m = self.default_leave_message
        if guild_data and guild_data.get("leave") and guild_data["leave"].get("message"):
            m = guild_data["leave"]["message"]
        await ctx.send_render(m) # Using interpolation system
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_data = await self.bot.db.get(table="guilds", id=member.guild.id)
        if not guild_data or not guild_data.get("welcome") or not guild_data["welcome"].get("enabled") or not guild_data["welcome"].get("channel"):
            return
        channel_id = guild_data["welcome"]["channel"]
        message = (guild_data.get("welcome", {}).get("message") or "").strip() or self.default_welcome_message
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return
        fake_ctx = CommieContext.create_for_event(self.bot, member, guild=member.guild) # Create a fake context for interpolation
        result = await self.bot.toolkit.interpolation.render(message, fake_ctx)
        content = result.content.strip() if result.content else None
        if not content and not result.embeds:
            content = "\u200b"
        sent = await channel.send(content=content, embeds=result.embeds[:10])
        for reaction in result.emojis[:20]:
            try:
                await sent.add_reaction(reaction)
            except discord.HTTPException:
                continue

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild_data = await self.bot.db.get(table="guilds", id=member.guild.id)
        if not guild_data or not guild_data.get("leave") or not guild_data["leave"].get("enabled") or not guild_data["leave"].get("channel"):
            return
        channel_id = guild_data["leave"]["channel"]
        message = (guild_data.get("leave", {}).get("message") or "").strip() or self.default_leave_message
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return
        fake_ctx = CommieContext.create_for_event(self.bot, member, guild=member.guild) # Create a fake context for interpolation
        result = await self.bot.toolkit.interpolation.render(message, fake_ctx)
        content = result.content.strip() if result.content else None
        if not content and not result.embeds:
            content = "\u200b"
        sent = await channel.send(content=content, embeds=result.embeds[:10])
        for reaction in result.emojis[:20]:
            try:
                await sent.add_reaction(reaction)
            except discord.HTTPException:
                continue
    

async def setup(bot: CommieBot):
    await bot.add_cog(Greetings(bot))