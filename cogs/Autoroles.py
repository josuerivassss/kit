from discord.ext import commands
from core.kernel import KitBot, KitContext
from core.help import send_help_group
import discord
from typing import Literal

"""
GUILDS TABLE

"_id": Guild ID (int)
"autoroles": {
    "humans": [int],
    "bots": [int],
}
"""

class Autoroles(commands.Cog):

    def __init__(self, bot: KitBot):
        self.bot = bot
    
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.hybrid_group(name="autoroles")
    async def autoroles(self, ctx: KitContext):
        """Autoroles related commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("autoroles")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())
    
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @autoroles.command(name="add")
    async def autoroles_add(self, ctx: KitContext, role: discord.Role, usertype: Literal["bots", "humans"] = "humans"):
        """Adds a role to the autoroles"""
        await ctx.defer()
        T = await ctx.get_locale()
        if role.is_default():
            raise commands.CommandError(T.get("errors.roleIsDefault"), T.get("errors.roleIsDefaultHint"))
        if role.position >= ctx.me.top_role.position:
            raise commands.CommandError(T.get("errors.roleIsAboveMine"), T.get("errors.roleIsAboveMineHint"))
        roles = await self.bot.db.get(table="guilds", id=ctx.guild.id, path=f"autoroles.{usertype}") or []
        if len(roles) >= 2:
            raise commands.CommandError(T.get("errors.autorolesLimitReached", userType=usertype), T.get("errors.autorolesLimitReachedHint"))
        if next((r for r in roles if r == role.id), None):
            raise commands.CommandError(T.get("errors.autoroleAlreadyExists"), T.get("errors.autoroleAlreadyExistsHint"))
        roles.append(role.id)
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path=f"autoroles.{usertype}", value=roles)
        await ctx.answer(T.get("success.autoroleAdded", name=role.name), type="success")
    
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @autoroles.command(name="remove", aliases=["delete"])
    async def autoroles_remove(self, ctx: KitContext, role: discord.Role, usertype: Literal["bots", "humans"] = "humans"):
        """Removes a role from the autoroles"""
        await ctx.defer()
        T = await ctx.get_locale()
        if role.is_default():
            raise commands.CommandError(T.get("errors.roleIsDefault"), T.get("errors.roleIsDefaultHint"))
        roles = await self.bot.db.get(table="guilds", id=ctx.guild.id, path=f"autoroles.{usertype}") or []
        if role.id not in roles:
            raise commands.CommandError(T.get("errors.autoroleNotFound"), T.get("errors.autoroleNotFoundHint"))
        roles = [r for r in roles if r != role.id]
        await self.bot.db.set(table="guilds", id=ctx.guild.id, path=f"autoroles.{usertype}", value=roles)
        await ctx.answer(T.get("success.autoroleRemoved", name=role.name), type="success")
    
    @commands.has_guild_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @autoroles.command(name="list", aliases=["show"])
    async def autoroles_list(self, ctx: KitContext):
        """Lists the autoroles"""
        await ctx.defer()
        T = await ctx.get_locale()
        humans = await self.bot.db.get(table="guilds", id=ctx.guild.id, path="autoroles.humans") or []
        bots = await self.bot.db.get(table="guilds", id=ctx.guild.id, path="autoroles.bots") or []
        
        def format_roles(role_ids):
            roles = []
            for r_id in role_ids:
                role = ctx.guild.get_role(r_id)
                if role:
                    roles.append(role.mention)
                else:
                    roles.append(f"`{r_id}`")
            return ", ".join(roles) if roles else T.get("errors.noRolesSet")
        
        embed = discord.Embed(title="Autoroles", color=discord.Color.blue())
        embed.add_field(name=T.get("info.humans"), value=format_roles(humans), inline=False)
        embed.add_field(name=T.get("info.bots"), value=format_roles(bots), inline=False)
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_data = await self.bot.db.get(table="guilds", id=member.guild.id)
        if not guild_data or "autoroles" not in guild_data:
            return
        autoroles = guild_data["autoroles"]
        user_type = "bots" if member.bot else "humans"
        role_ids = autoroles.get(user_type, [])
        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Autorole assigned on member join")
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass


async def setup(bot: KitBot):
    await bot.add_cog(Autoroles(bot))