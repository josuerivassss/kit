"""Developer/owner-only cog: diagnostics, hot-reload, and the /help entry point."""
import discord, sys, datetime
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.help import send_help, send_help_cog, send_help_group, send_help_command
from bcommie.kernel import AnswerType
from bcommie.ui.paginator import Paginator

_BOT_INVITE_URL = "https://discord.com/oauth2/authorize?client_id=1449864932731392223&permissions=8&scope=bot+applications.commands"
_DISCORD_INVITE_URL = "https://discord.gg/SY5D4x3RB3"
_WEB_URL = "https://commie.cofue.space"

class Developer(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: CommieContext):
        """Returns pong"""
        T = await ctx.get_locale()
        await ctx.send(T.get("ping", ms=round(self.bot.latency, 2)))
    
    @commands.hybrid_command(name="invite")
    @discord.app_commands.allowed_installs(guilds=True, users=True)
    @discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def invite(self, ctx: CommieContext):
        """Shows the bot & support server invite"""
        T = await ctx.get_locale()
        view = discord.ui.View().add_item(
            discord.ui.Button(style=discord.ButtonStyle.link, label="Invite bot", url=_BOT_INVITE_URL),
        ).add_item(
            discord.ui.Button(style=discord.ButtonStyle.link, label="Discord server", url=_DISCORD_INVITE_URL)
        ).add_item(
            discord.ui.Button(style=discord.ButtonStyle.link, label="Web", url=_WEB_URL)
        )
        await ctx.answer(T.get("inviteDescription"), type=AnswerType.Ok, view=view, bold=False)
    
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
    @commands.is_owner()
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
    @discord.app_commands.allowed_installs(guilds=True, users=True)
    @discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def info(self, ctx: CommieContext):
        """Shows information about the bot, including shard/cluster placement."""
        uptime = datetime.datetime.now(datetime.UTC) - self.bot.start_time
        shard_id = ctx.guild.shard_id if ctx.guild else 0
        embed = discord.Embed(colour=discord.Color.dark_red())
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
        embed.add_field(name="Version", value="1.0.0", inline=True)
        embed.add_field(name="Python", value=sys.version.split(' ')[0], inline=True)
        embed.add_field(name="Platform", value=sys.platform, inline=True)
        await ctx.send(content="Here's my software specifications! " + CommieEmojis.Developer, embed=embed)
    
    @commands.is_owner()
    @commands.hybrid_group(name="dashboard")
    async def dashboard(self, ctx: CommieContext):
        """Manages web dashboard access (owner-only)"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("dashboard")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.is_owner()
    @dashboard.command(name="grant")
    @discord.app_commands.describe(user="The Discord user to grant dashboard access to")
    async def dashboard_grant(self, ctx: CommieContext, user: discord.User):
        """Grants a user access to the web dashboard"""
        await ctx.defer()
        # Single existence check avoids an unnecessary write when already granted
        if await self.bot.db.exists(table="dashboard_access", id=user.id):
            await ctx.answer(f"**{user}** already has dashboard access.", type=AnswerType.Info)
            return
        await self.bot.db.set(
            table="dashboard_access",
            id=user.id,
            data={"granted_by": ctx.author.id, "granted_at": int(discord.utils.utcnow().timestamp())},
        )
        await ctx.answer(f"Dashboard access granted to **{user}**.", type=AnswerType.Ok)

    @commands.is_owner()
    @dashboard.command(name="revoke")
    @discord.app_commands.describe(user="The Discord user to revoke dashboard access from")
    async def dashboard_revoke(self, ctx: CommieContext, user: discord.User):
        """Revokes a user's access to the web dashboard"""
        await ctx.defer()
        deleted = await self.bot.db.delete(table="dashboard_access", id=user.id)
        if not deleted:
            await ctx.answer(f"**{user}** does not have dashboard access.", type=AnswerType.Info)
            return
        await ctx.answer(f"Dashboard access revoked from **{user}**.", type=AnswerType.Ok)
    
    @commands.is_owner()
    @dashboard.command(name="list")
    async def dashboard_list(self, ctx: CommieContext):
        """Lists every user currently authorized to use the web dashboard"""
        await ctx.defer()
        T = await ctx.get_locale()
        authorized = await self.bot.db.find(table="dashboard_access", filter={}, projection={"_id": 1})
        if not authorized:
            await ctx.answer("No users currently have dashboard access.", type=AnswerType.Info)
            return

        PER_PAGE = 10
        pages: list[list[dict]] = [authorized[i:i + PER_PAGE] for i in range(0, len(authorized), PER_PAGE)]
        embed = discord.Embed(title="Dashboard Access", colour=discord.Color.dark_red())
        embed.set_author(name=ctx.guild.name if ctx.guild else self.bot.user.name, icon_url=self.bot.user.display_avatar)

        def render(page_items: list[dict], page: int, total: int):
            embed.description = "\n".join(f"<@{doc['_id']}> (`{doc['_id']}`)" for doc in page_items)
            embed.set_footer(text=T.get("paginator.footer", page=page + 1, total=total))

        paginator = Paginator(data=pages, ctx=ctx, locale=T, embed=embed, render=render)
        paginator.update_item()
        paginator.message = await ctx.send(embed=embed, view=paginator)

async def setup(bot: CommieBot):
    await bot.add_cog(Developer(bot))