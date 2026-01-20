from discord.ext import commands
from core.kernel import KitBot, KitContext
import discord

class Moderation(commands.Cog):
    def __init__(self, bot: KitBot):
        self.bot = bot

    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    @commands.hybrid_command(name="lockdown", aliases=["lock"])
    async def lockdown(self, ctx: KitContext, channel: discord.TextChannel = None):
        """Locks a channel for everyone"""
        await ctx.defer()
        T = await ctx.get_locale()
        target_channel = channel or ctx.channel
        if not target_channel.permissions_for(ctx.guild.default_role).send_messages is not True:
            raise commands.CommandError(T.get("errors.channelAlreadyLocked"))
        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Lockdown by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.channelLocked", channel=target_channel.mention), type="success", bold=False)
    
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.has_guild_permissions(manage_channels=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    @commands.hybrid_command(name="unlockdown", aliases=["unlock"])
    async def unlockdown(self, ctx: KitContext, channel: discord.TextChannel = None):
        """Unlocks a channel for everyone"""
        await ctx.defer()
        T = await ctx.get_locale()
        target_channel = channel or ctx.channel
        if target_channel.permissions_for(ctx.guild.default_role).send_messages is True:
            raise commands.CommandError(T.get("errors.channelAlreadyUnlocked"))
        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlockdown by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.channelUnlocked", channel=target_channel.mention), type="success", bold=False)
    
    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    @commands.hybrid_command(name="timeout", aliases=["tempmute"])
    async def timeout(self, ctx: KitContext, member: discord.Member, duration: int, *, reason: str = None):
        """Timeouts a member for a certain amount of seconds"""
        await ctx.defer()
        T = await ctx.get_locale()
        if member.id == ctx.author.id:
            raise commands.CommandError(T.get("errors.cantActionYourself"))
        if member.id == ctx.me.id:
            raise commands.CommandError(T.get("errors.cantActiontMe"))
        if member.top_role.position >= ctx.me.top_role.position:
            raise commands.CommandError(T.get("errors.cantActionHigherRole"), T.get("errors.cantActionHigherRoleHint"))
        if member.id == ctx.guild.owner_id:
            raise commands.CommandError(T.get("errors.cantActionOwner"))
        if member.guild_permissions.administrator:
            raise commands.CommandError(T.get("errors.cantActionAdmin"))
        if member.timed_out_until is not None:
            raise commands.CommandError(T.get("errors.memberAlreadyTimedOut"))
        if duration < 60 or duration > 2419200:
            raise commands.CommandError(T.get("errors.timeoutDurationInvalid"), T.get("errors.timeoutDurationInvalidHint"))
        until = discord.utils.utcnow() + discord.timedelta(seconds=duration)
        await member.timeout(until, reason=reason or f"Timeout by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.memberTimedOut", member=member.mention, duration=duration), type="success", bold=False)
    
    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.has_guild_permissions(moderate_members=True)
    @commands.bot_has_guild_permissions(moderate_members=True)
    @commands.hybrid_command(name="untimeout", aliases=["untimemute"])
    async def untimeout(self, ctx: KitContext, member: discord.Member, *, reason: str = None):
        """Untimeouts a member"""
        await ctx.defer()
        T = await ctx.get_locale()
        if member.id == ctx.author.id:
            raise commands.CommandError(T.get("errors.cantActionYourself"))
        if member.id == ctx.me.id:
            raise commands.CommandError(T.get("errors.cantActiontMe"))
        if member.top_role.position >= ctx.me.top_role.position:
            raise commands.CommandError(T.get("errors.cantActionHigherRole"), T.get("errors.cantActionHigherRoleHint"))
        if member.id == ctx.guild.owner_id:
            raise commands.CommandError(T.get("errors.cantActionOwner"))
        if member.guild_permissions.administrator:
            raise commands.CommandError(T.get("errors.cantActionAdmin"))
        if member.timed_out_until is None:
            raise commands.CommandError(T.get("errors.memberNotTimedOut"))
        await member.timeout(None, reason=reason or f"Untimeout by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.memberUntimedOut", member=member.mention), type="success", bold=False)
    
    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.bot_has_guild_permissions(manage_messages=True)
    @commands.has_guild_permissions(manage_messages=True)
    @commands.hybrid_command(name="clear", aliases=["purge", "clean"])
    async def clear(self, ctx: KitContext, amount: int = 10, member: discord.Member = None):
        """Clears a number of messages in the channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        if amount < 1 or amount > 100:
            raise commands.CommandError(T.get("errors.clearAmountInvalid"), T.get("errors.clearAmountInvalidHint"))
        def check(m: discord.Message):
            if member:
                return m.author.id == member.id
            return True
        deleted = await ctx.channel.purge(limit=amount, check=check, reason=f"Clear by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.messagesCleared", count=len(deleted)), type="success", bold=False)
    
    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.bot_has_guild_permissions(kick_members=True)
    @commands.has_guild_permissions(kick_members=True)
    @commands.hybrid_command(name="kick")
    async def kick(self, ctx: KitContext, member: discord.Member, *, reason: str = None):
        """Kicks a member from the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        if member.id == ctx.author.id:
            raise commands.CommandError(T.get("errors.cantActionYourself"))
        if member.id == ctx.me.id:
            raise commands.CommandError(T.get("errors.cantActiontMe"))
        if member.top_role.position >= ctx.me.top_role.position:
            raise commands.CommandError(T.get("errors.cantActionHigherRole"), T.get("errors.cantActionHigherRoleHint"))
        if member.id == ctx.guild.owner_id:
            raise commands.CommandError(T.get("errors.cantActionOwner"))
        if member.guild_permissions.administrator:
            raise commands.CommandError(T.get("errors.cantActionAdmin"))
        await member.kick(reason=reason or f"Kick by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.memberKicked", member=member.mention), type="success", bold=False)
    
    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.bot_has_guild_permissions(ban_members=True)
    @commands.has_guild_permissions(ban_members=True)
    @commands.hybrid_command(name="ban")
    async def ban(self, ctx: KitContext, member: discord.Member, *, reason: str = None):
        """Bans a member from the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        if member.id == ctx.author.id:
            raise commands.CommandError(T.get("errors.cantActionYourself"))
        if member.id == ctx.me.id:
            raise commands.CommandError(T.get("errors.cantActiontMe"))
        if member.top_role.position >= ctx.me.top_role.position:
            raise commands.CommandError(T.get("errors.cantActionHigherRole"), T.get("errors.cantActionHigherRoleHint"))
        if member.id == ctx.guild.owner_id:
            raise commands.CommandError(T.get("errors.cantActionOwner"))
        if member.guild_permissions.administrator:
            raise commands.CommandError(T.get("errors.cantActionAdmin"))
        await member.ban(reason=reason or f"Ban by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.memberBanned", member=member.mention), type="success", bold=False)

    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.bot_has_guild_permissions(ban_members=True)
    @commands.has_guild_permissions(ban_members=True)
    @commands.hybrid_command(name="unban")
    async def unban(self, ctx: KitContext, user: discord.User, *, reason: str = None):
        """Unbans a member from the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        bans = await ctx.guild.bans()
        if not any(ban_entry.user.id == user.id for ban_entry in bans):
            raise commands.CommandError(T.get("errors.userNotBanned"))
        await ctx.guild.unban(user, reason=reason or f"Unban by {ctx.author} ({ctx.author.id})")
        await ctx.answer(T.get("success.memberUnbanned", user=str(user)), type="success", bold=False)
    
async def setup(bot: KitBot):
    await bot.add_cog(Moderation(bot))