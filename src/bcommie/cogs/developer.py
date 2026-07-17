"""Developer/owner-only cog: diagnostics, hot-reload, and the /help entry point."""
import discord, sys, datetime
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.help import send_help, send_help_cog, send_help_group, send_help_command
from bcommie.kernel import AnswerType

class Developer(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: CommieContext):
        """Returns pong"""
        T = await ctx.get_locale()
        await ctx.send(T.get("ping", ms=round(self.bot.latency, 2)))
    
    @commands.is_owner()
    @commands.hybrid_command(name="reload")
    @discord.app_commands.describe(name="Cog name to reload (e.g. 'moderation')", sync_too="Whether to sync slash commands after reloading")
    async def dev_reload(self, ctx: CommieContext, name: str, sync_too: bool = False):
        """Hot-reloads a cog by name, without restarting the process/shard."""
        extension = f"bcommie.cogs.{name.lower()}"
        old = ctx.bot.commands
        try:
            await ctx.bot.reload_extension(extension)
        except commands.ExtensionNotFound as exc:
            raise commands.CommandError(f"No cog named **{name}**.") from exc
        except commands.ExtensionError as exc:
            raise commands.CommandError(f"Failed to reload **{name}**: {exc}") from exc
        view = (
            discord.ui.View()
            .add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label="Commands", custom_id="general", disabled=True))
            .add_item(discord.ui.Button(style=discord.ButtonStyle.red, label=f"Before: {len(old)}", custom_id="before", disabled=True))
            .add_item(discord.ui.Button(style=discord.ButtonStyle.green, label=f"After: {len(ctx.bot.commands)}", custom_id="after", disabled=True))
        )
        if sync_too:
            self.bot.slash_cache = await self.bot.tree.sync()
        await ctx.answer(f"**{name}** successfully reloaded!", bold=False, view=view, type=AnswerType.Ok)
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="interpolate")
    @discord.app_commands.describe(text="The text to interpolate with locale placeholders")
    async def interpolate(self, ctx: CommieContext, *, text: str):
        """Interpolates a string with locale placeholders"""
        await ctx.send_render(text)

    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.hybrid_command(name="help")
    @discord.app_commands.describe(query="The command or cog to get help about")
    async def help_command(self, ctx: CommieContext, *, query: str = None):
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
                    await ctx.send(T.get("help.notFound", query=query))
    
    @commands.hybrid_command(name="uptime")
    async def uptime(self, ctx: CommieContext):
        """Shows bot uptime"""
        uptime = datetime.datetime.now(datetime.UTC) - self.bot.start_time
        await ctx.send(f"Uptime: {uptime} hrs")

    # This command won't be translated
    @commands.hybrid_command(name="info", aliases=["software", "botinfo"])
    async def info(self, ctx: CommieContext):
        """Shows information about the bot, including shard/cluster placement."""
        uptime = datetime.datetime.now(datetime.UTC) - self.bot.start_time
        shard_id = ctx.guild.shard_id if ctx.guild else 0
        embed = discord.Embed(colour=discord.Color.dark_red(), description="Here's my software specifications! " + CommieEmojis.Developer)
        embed.set_thumbnail(url=str(ctx.bot.user.display_avatar).replace(".webp", ".png"))
        embed.add_field(name="Developer", value="@cofue", inline=True)
        embed.add_field(name="Servers", value=len(ctx.bot.guilds), inline=True)
        embed.add_field(name="Users", value=len(ctx.bot.users), inline=True)
        embed.add_field(name="Commands", value=len(ctx.bot.commands), inline=True)
        embed.add_field(name="Uptime", value=f"{uptime}", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000, 2)} ms", inline=True)
        embed.add_field(name="Shard", value=f"{shard_id} / {self.bot.shard_count or 1}", inline=True)
        embed.add_field(name="Cluster", value=str(self.bot.settings.cluster_id), inline=True)
        embed.add_field(name="Library", value=f"discord.py@{discord.__version__}", inline=True)
        embed.add_field(name="Version", value="2.0.0", inline=True)
        embed.add_field(name="Python", value=sys.version.split(' ')[0], inline=True)
        embed.add_field(name="Platform", value=sys.platform, inline=True)
        await ctx.send(embed=embed)

async def setup(bot: CommieBot):
    await bot.add_cog(Developer(bot))