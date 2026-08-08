"""Developer/owner-only cog: diagnostics, hot-reload, API key management, and the /help entry point."""
import discord, sys, datetime, io, json, secrets, hashlib
from datetime import timedelta, timezone
from typing import Literal
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.help import send_help, send_help_cog, send_help_group, send_help_command
from bcommie.kernel import AnswerType
from bcommie.ui.paginator import Paginator
from bcommie.introspection import build_commands_snapshot

_BOT_INVITE_URL = "https://discord.com/oauth2/authorize?client_id=1449864932731392223&permissions=8&scope=bot+applications.commands"
_DISCORD_INVITE_URL = "https://discord.gg/SY5D4x3RB3"
_WEB_URL = "https://commie.cofue.space"

_INTROSPECTION_EXCLUDED_COGS = {"Developer", "Events", "Jishaku"}

_PARTNER_MIN_GUILDS = 2
_PARTNER_MIN_HUMAN_MEMBERS = 5


def _is_key_hash(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _qualifying_guilds(bot: CommieBot, user_id: int) -> list[discord.Guild]:
    qualifying = []
    for g in bot.guilds:
        if g.owner_id != user_id:
            continue
        human_count = sum(1 for m in g.members if not m.bot)
        if human_count > _PARTNER_MIN_HUMAN_MEMBERS:
            qualifying.append(g)
    return qualifying


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
    @commands.hybrid_command(name="interpolate", extras={"supports_placeholders": True})
    @commands.is_owner()
    @discord.app_commands.describe(text="The text to interpolate with locale placeholders")
    async def interpolate(self, ctx: CommieContext, *, text: str):
        """Interpolates a string with locale placeholders"""
        await ctx.send_render(text)

    @commands.cooldown(1, 8, commands.BucketType.member)
    @commands.hybrid_command(name="help")
    async def help_command(self, ctx: CommieContext, *, query: str = None):
        """Get help about the bot
        
        Parameters
        ----
        query: str
            The command or subcommand to get help about.
        """
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

    def _api_keys(self):
        return self.bot.db.db["api_keys"]

    async def _refresh_api_cache(self):
        await self.bot.toolkit.request(
            method="POST",
            url=f"{self.bot.settings.api_base_url}/admin/refresh-keys",
            headers={"X-Internal-Secret": self.bot.settings.api_admin_secret},
        )

    @commands.is_owner()
    @commands.hybrid_group(name="api")
    async def api(self, ctx: CommieContext):
        """Manages API key access (owner-only)"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("api")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.is_owner()
    @api.command(name="grant")
    @discord.app_commands.describe(user="Target user", plan="basic | pro | partner", duration_hours="Pro validity in hours (default 48)")
    async def api_grant(self, ctx: CommieContext, user: discord.User, plan: Literal["basic", "pro", "partner"], duration_hours: int = 48):
        """Grants or updates an API key for a user"""
        await ctx.defer()
        collection = self._api_keys()
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        expires_at = datetime.datetime.now(timezone.utc) + timedelta(hours=duration_hours) if plan == "pro" else None
        data = {"key_hash": key_hash, "discord_id": str(user.id), "plan": plan, "banned": False, "expires_at": expires_at}
        existing = await collection.find_one({"discord_id": str(user.id)})
        if existing:
            await collection.update_one({"_id": existing["_id"]}, {"$set": data})
        else:
            await collection.insert_one(data)
        await self._refresh_api_cache()
        try:
            await user.send(f"Your new API key: `{raw_key}`\nPlan: **{plan}**\nKeep it secret, it won't be shown again.")
            delivered = True
        except discord.Forbidden:
            delivered = False
        msg = f"Granted **{plan}** plan to **{user}**."
        if not delivered:
            msg += " Could not DM the key (DMs closed) -- use `/api regenerate` once they open DMs."
        await ctx.answer(msg, type="success")

    @commands.is_owner()
    @api.command(name="revoke")
    @discord.app_commands.describe(target="User mention/ID or the key's hash")
    async def api_revoke(self, ctx: CommieContext, target: str):
        """Revokes an API key by user or key hash"""
        await ctx.defer()
        target = target.strip("<@!>")
        query = {"key_hash": target} if _is_key_hash(target) else {"discord_id": target}
        result = await self._api_keys().delete_one(query)
        if result.deleted_count == 0:
            raise commands.CommandError("No matching API key found.")
        await self._refresh_api_cache()
        await ctx.answer(f"Revoked API key for `{target}`.", type="success")

    @commands.is_owner()
    @api.command(name="ban")
    @discord.app_commands.describe(user="User to ban from API access")
    async def api_ban(self, ctx: CommieContext, user: discord.User):
        """Bans a user's API key without deleting it"""
        await ctx.defer()
        result = await self._api_keys().update_one({"discord_id": str(user.id)}, {"$set": {"banned": True}})
        if result.matched_count == 0:
            raise commands.CommandError(f"{user} has no API key.")
        await self._refresh_api_cache()
        await ctx.answer(f"Banned API access for **{user}**.", type="success")

    @commands.is_owner()
    @api.command(name="check")
    @discord.app_commands.describe(user="User to check for Partner eligibility")
    async def api_check(self, ctx: CommieContext, user: discord.User):
        """Checks if a user currently qualifies for the Partner plan"""
        await ctx.defer()
        qualifying = _qualifying_guilds(self.bot, user.id)
        eligible = len(qualifying) >= _PARTNER_MIN_GUILDS
        embed = discord.Embed(title=f"Partner eligibility: {user}", colour=discord.Color.green() if eligible else discord.Color.red())
        embed.add_field(name="Qualifying servers", value=str(len(qualifying)))
        embed.add_field(name="Required", value=f"{_PARTNER_MIN_GUILDS} servers, >{_PARTNER_MIN_HUMAN_MEMBERS} humans each")
        embed.add_field(name="Eligible", value="✅" if eligible else "❌")
        if qualifying:
            embed.add_field(name="Servers", value="\n".join(g.name for g in qualifying[:10]), inline=False)
        await ctx.send(embed=embed)

    @commands.is_owner()
    @api.command(name="checkall")
    @discord.app_commands.describe(enforce="Downgrade ineligible partners to basic instead of just reporting")
    async def api_checkall(self, ctx: CommieContext, enforce: bool = False):
        """Audits every Partner key against current ownership/member requirements"""
        await ctx.defer()
        collection = self._api_keys()
        partners = await collection.find({"plan": "partner"}).to_list(length=None)
        ineligible = []
        for doc in partners:
            qualifying = _qualifying_guilds(self.bot, int(doc["discord_id"]))
            if len(qualifying) < _PARTNER_MIN_GUILDS:
                ineligible.append((doc, len(qualifying)))
        if enforce and ineligible:
            for doc, _count in ineligible:
                await collection.update_one({"_id": doc["_id"]}, {"$set": {"plan": "basic"}})
            await self._refresh_api_cache()
        lines = [f"<@{d['discord_id']}> ({count}/{_PARTNER_MIN_GUILDS})" for d, count in ineligible] or ["None"]
        title = "Partner audit (enforced)" if enforce else "Partner audit (report only)"
        embed = discord.Embed(title=title, description="\n".join(lines), colour=discord.Color.dark_red())
        embed.set_footer(text=f"{len(ineligible)} ineligible out of {len(partners)} partners")
        await ctx.send(embed=embed)

    @commands.is_owner()
    @api.command(name="info")
    @discord.app_commands.describe(target="User mention/ID or the key's hash")
    async def api_info(self, ctx: CommieContext, target: str):
        """Shows raw API key data for a user or key hash"""
        await ctx.defer()
        target = target.strip("<@!>")
        query = {"key_hash": target} if _is_key_hash(target) else {"discord_id": target}
        doc = await self._api_keys().find_one(query)
        if not doc:
            raise commands.CommandError("No matching API key found.")
        embed = discord.Embed(title="API Key Info", colour=discord.Color.dark_red())
        embed.add_field(name="Discord ID", value=doc["discord_id"])
        embed.add_field(name="Plan", value=doc["plan"])
        embed.add_field(name="Banned", value="✅" if doc["banned"] else "❌")
        embed.add_field(name="Expires", value=doc["expires_at"].strftime("%Y-%m-%d %H:%M UTC") if doc.get("expires_at") else "Never")
        await ctx.send(embed=embed)

    @commands.is_owner()
    @api.command(name="usage")
    @discord.app_commands.describe(target="User mention/ID or the key's hash")
    async def api_usage(self, ctx: CommieContext, target: str):
        """Shows today's request count for a key, read live from the API"""
        await ctx.defer()
        target = target.strip("<@!>")
        query = {"key_hash": target} if _is_key_hash(target) else {"discord_id": target}
        doc = await self._api_keys().find_one(query)
        if not doc:
            raise commands.CommandError("No matching API key found.")
        response = await self.bot.toolkit.request(
            method="GET",
            url=f"{self.bot.settings.api_base_url}/admin/usage/{doc['key_hash']}",
            headers={"X-Internal-Secret": self.bot.settings.api_admin_secret},
        )
        if not response:
            raise commands.CommandError("Could not reach the API server.")
        usage_data = response.get("data", response)
        limit = usage_data.get("limit")
        embed = discord.Embed(title="API Key Usage", colour=discord.Color.dark_red())
        embed.add_field(name="Discord ID", value=usage_data.get("discord_id"))
        embed.add_field(name="Plan", value=usage_data.get("plan"))
        embed.add_field(name="Used today", value=f"{usage_data.get('used')}/{limit if limit is not None else '∞'}")
        await ctx.send(embed=embed)

    @commands.is_owner()
    @api.command(name="regenerate")
    @discord.app_commands.describe(user="User whose key will be regenerated")
    async def api_regenerate(self, ctx: CommieContext, user: discord.User):
        """Issues a new key for a user, invalidating the previous one"""
        await ctx.defer()
        collection = self._api_keys()
        existing = await collection.find_one({"discord_id": str(user.id)})
        if not existing:
            raise commands.CommandError(f"{user} has no API key.")
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await collection.update_one({"_id": existing["_id"]}, {"$set": {"key_hash": key_hash}})
        await self._refresh_api_cache()
        try:
            await user.send(f"Your regenerated API key: `{raw_key}`\nThe previous key stopped working immediately.")
            delivered = True
        except discord.Forbidden:
            delivered = False
        msg = f"Regenerated API key for **{user}**."
        if not delivered:
            msg += " Could not DM the new key (DMs closed)."
        await ctx.answer(msg, type="success")

    @commands.is_owner()
    @commands.command(name="fetchcommands")
    async def fetch_commands(self, ctx: CommieContext):
        """Dumps every command's metadata (cooldowns, permissions, slash IDs) as JSON"""
        snapshot = build_commands_snapshot(self.bot, _INTROSPECTION_EXCLUDED_COGS)
        payload = json.dumps(snapshot, indent=2, ensure_ascii=False).encode("utf-8")
        file = discord.File(io.BytesIO(payload), filename=f"commands-{int(discord.utils.utcnow().timestamp())}.json")
        await ctx.send(content=f"Serialized **{snapshot['command_count']}** top-level commands.", file=file)

async def setup(bot: CommieBot):
    await bot.add_cog(Developer(bot))