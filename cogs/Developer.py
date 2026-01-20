import discord, sys, datetime, os
from discord.ext import commands
from core.kernel import KitBot, KitContext
from core.help import send_help, send_help_cog, send_help_group, send_help_command
from core.kernel import AnswerType

class Developer(commands.Cog):
    def __init__(self, bot: KitBot):
        self.bot = bot

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: KitContext):
        """Returns pong"""
        T = await ctx.get_locale()
        await ctx.send(T.get("ping", ms=round(self.bot.latency, 2)))
    
    @commands.is_owner()
    @commands.hybrid_command(name="reload")
    async def dev_reload(self, ctx: KitContext, path: str, sync_too: bool = False):
        """Reloads a cog"""
        file_path = path.replace(".", os.sep) + ".py"
        if not os.path.exists(file_path):
            raise commands.CommandError("That cog doesn't exist")
        old = ctx.bot.commands
        await ctx.bot.reload_extension(path)
        view = discord.ui.View().add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label=f"Commands", custom_id="general", disabled=True)).add_item(discord.ui.Button(style=discord.ButtonStyle.red, label=f"Before: {len(old)}", custom_id="before", disabled=True)).add_item(discord.ui.Button(style=discord.ButtonStyle.green, label=f"After: {len(ctx.bot.commands)}", custom_id="after", disabled=True))
        if sync_too:
            self.bot.slash_cache = await self.bot.tree.sync()
        await ctx.answer(f"**{path}** successfully reloaded!", bold=False, view=view, type=AnswerType.Ok)
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="interpolate")
    async def interpolate(self, ctx: KitContext, *, text: str):
        """Interpolates a string with locale placeholders"""
        await ctx.send_render(text)

    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.hybrid_command(name="help")
    async def help_command(self, ctx: KitContext, *, query: str = None):
        """Get help about the bot"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not query:
            await send_help(ctx, self.bot.slash_cache, T)
        else:
            cog = self.bot.get_cog(query.title())
            if cog:
                await send_help_cog(ctx, query.title(), self.bot.slash_cache, T)
            else:
                cmd = self.bot.get_command(query.lower())
                if isinstance(cmd, commands.HybridGroup):
                    await send_help_group(ctx, cmd, self.bot.slash_cache, T)
                elif isinstance(cmd, commands.HybridCommand):
                    await send_help_command(ctx, cmd, self.bot.slash_cache, T)
                else:
                    pass
    
    @commands.hybrid_command(name="uptime")
    async def uptime(self, ctx: KitContext):
        """Shows bot uptime"""
        uptime = datetime.timedelta(milliseconds=(round(datetime.datetime.now().timestamp()) - round(self.bot.start_time.timestamp())) * 1000)
        await ctx.send(f"Uptime: {uptime} hrs")
    
    # This command won't be translated
    @commands.hybrid_command(name="info", aliases=["software", "botinfo"])
    async def info(self, ctx: KitContext):
        """Shows information about the bot"""
        uptime = datetime.timedelta(milliseconds=(round(datetime.datetime.now().timestamp()) - round(self.bot.start_time.timestamp())) * 1000)
        embed = discord.Embed(colour=discord.Color.blurple(), title="kit")
        embed.set_thumbnail(url=str(ctx.bot.user.display_avatar).replace(".webp", ".png"))
        embed.add_field(name="Developer", value="@cofuefest", inline=True)
        embed.add_field(name="Server", value=len(ctx.bot.guilds), inline=True)
        embed.add_field(name="Users", value=len(ctx.bot.users), inline=True)
        embed.add_field(name="Commands", value=len(ctx.bot.commands), inline=True)
        embed.add_field(name="Uptime", value=f"{uptime} hrs", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency*1000, 2)} ms", inline=True)
        embed.add_field(name="Library", value=f"discord.py@{discord.__version__}", inline=True)
        embed.add_field(name="Version", value="0.1.0", inline=True)
        embed.add_field(name="Python", value=sys.version.split(' ')[0], inline=True)
        embed.add_field(name="Platform", value=sys.platform, inline=True)
        await ctx.send(embed=embed)

async def setup(bot: KitBot):
    await bot.add_cog(Developer(bot))