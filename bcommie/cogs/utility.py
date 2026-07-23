"""Utility cog: profile/server info, roles, emojis, currency conversion, translation, image search."""
import time, discord, datetime, calendar as Calendar, asyncio
from typing import Optional
from discord.ext import commands, tasks
from deep_translator import GoogleTranslator
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.ui.paginator import Paginator
from http import HTTPStatus
from ddgs import DDGS

class Utility(commands.Cog):

    def __init__(self, bot: CommieBot):
        self.bot = bot
        self._image_search_semaphore = asyncio.Semaphore(3)  # cap concurrent blocking ddgs calls
        # In-memory set of currently-AFK users -- avoids a Postgres read on
        # every single message (most messages are from non-AFK users and
        # mention nobody AFK). Reconciled periodically to tolerate
        # multi-process clusters where another process's afk/unafk isn't
        # visible locally yet.
        self._afk_cache: dict[int, dict] = {}

    async def cog_load(self):
        await self._reload_afk_cache()
        self.reconcile_afk_cache.start()

    async def cog_unload(self):
        self.reconcile_afk_cache.cancel()

    async def _reload_afk_cache(self):
        try:
            rows = await self.bot.sql.find(table="afk_status", where={})
            self._afk_cache = {row["id"]: row for row in rows}
        except Exception:
            pass  # keep the previous cache on transient DB failure

    @tasks.loop(seconds=60)
    async def reconcile_afk_cache(self):
        await self._reload_afk_cache()

    @reconcile_afk_cache.before_loop
    async def before_reconcile_afk_cache(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def _ddg_image_search(query: str, max_results: int = 15) -> list[dict]:
        # backend="auto" lets ddgs pick/fallback between its supported
        # engines (bing, duckduckgo) automatically on rate limits/errors --
        # source doesn't matter here, only avoiding a hard failure does.
        with DDGS() as ddgs:
            return list(ddgs.images(query, backend="auto", safesearch="moderate", max_results=max_results))

    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.command(name="avatar", aliases=["av"])
    @discord.app_commands.describe(user="The user to show the avatar of")
    async def avatar_alias(self, ctx: CommieContext, user: Optional[discord.User]):
        await self.avatar(ctx, user)

    @commands.hybrid_group(name="user")
    async def user(self, ctx: CommieContext):
        """Related users commands"""
        ...
    
    @commands.cooldown(1, 4, commands.BucketType.member)
    @user.command(name="avatar")
    @discord.app_commands.describe(user="The user to show the avatar of")
    async def avatar(self, ctx: CommieContext, user: Optional[discord.User]):
        """Shows the avatar of an user"""
        await ctx.defer()
        if not user:
            user = ctx.author._user
        
        embed = discord.Embed(colour=discord.Color.dark_red())
        embed.set_author(name=user.name, icon_url=user.display_avatar)
        embed.set_image(url=str(user.display_avatar).replace(".webp", ".png"))
        await ctx.send(embed=embed)

    @commands.cooldown(1, 4, commands.BucketType.member)
    @user.command(name="info")
    @discord.app_commands.describe(user="The user to show the information of")
    async def info(self, ctx: CommieContext, user: Optional[discord.User | discord.Member]):
        """Shows information about an user"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not user:
            user = ctx.author
        
        embed = discord.Embed(colour=discord.Color.dark_red(), title=user.display_name)
        embed.set_thumbnail(url=str(user.display_avatar).replace(".webp", ".png"))
        embed.set_author(name=user.display_name, icon_url=user.display_avatar)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Bot?", value="✅" if user.bot else "❌" , inline=True)
        if isinstance(user, discord.Member):
            embed.add_field(name=T.get("info.nick"), value=user.nick if user.nick else user.display_name, inline=True)
            embed.add_field(name="Roles", value=str(len(user.roles)-1), inline=True)
            embed.add_field(name="Top Role", value=user.top_role.mention, inline=True)
            embed.add_field(name=T.get("info.joined"), value=f"<t:{round(user.joined_at.timestamp())}:D>", inline=False)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(user.created_at.timestamp())}:D>", inline=False)
        await ctx.send(embed=embed)
    
    @commands.hybrid_group(name="server")
    async def server(self, ctx: CommieContext):
        """Related server commands"""
        ...
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="icon")
    async def icon(self, ctx: CommieContext):
        """Shows the server icon"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not ctx.guild or not ctx.guild.icon:
            raise commands.CommandError(T.get("errors.noIcon"), T.get("errors.noIconHint"))
        guild = ctx.guild
        embed = discord.Embed(colour=discord.Color.dark_red(), title=guild.name)
        embed.set_image(url=str(guild.icon).replace(".webp", ".png"))
        embed.set_author(name=guild.name, icon_url=guild.icon)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="info")
    async def server_info(self, ctx: CommieContext):
        """Shows information about the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        guild = ctx.guild
        
        embed = discord.Embed(colour=discord.Color.dark_red(), title=guild.name)
        embed.set_thumbnail(url=str(guild.icon).replace(".webp", ".png") if guild.icon else ctx.author.display_avatar)
        embed.set_author(name=guild.name, icon_url=guild.icon)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name=T.get("info.members"), value=guild.member_count, inline=True)
        embed.add_field(name=T.get("info.owner"), value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name=T.get("info.roles"), value=len(guild.roles), inline=True)
        embed.add_field(name=T.get("info.channels"), value=f"**`{len(guild.channels)}`** ({T.get('info.text')}: `{len(guild.text_channels)}`, {T.get('info.voice')}: `{len(guild.voice_channels)}`, {T.get('info.other')}: `{len(ctx.guild.channels) - len(ctx.guild.text_channels) - len(ctx.guild.voice_channels)}`)", inline=True)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(guild.created_at.timestamp())}:D>", inline=False)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="banner")
    async def banner(self, ctx: CommieContext):
        """Shows the server banner"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not ctx.guild or not ctx.guild.banner:
            raise commands.CommandError(T.get("errors.noBanner"), T.get("errors.noBannerHint"))
        guild = ctx.guild
        embed = discord.Embed(colour=discord.Color.dark_red(), title=guild.name)
        embed.set_image(url=str(guild.banner).replace(".webp", ".png"))
        embed.set_author(name=guild.name, icon_url=guild.icon)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="roles")
    async def roles(self, ctx: CommieContext):
        """Shows the server roles"""
        await ctx.defer()
        guild = ctx.guild
        roles = [role.mention for role in guild.roles]
        roles.reverse()
        
        embed = discord.Embed(colour=discord.Color.dark_red(), title=guild.name)
        embed.set_author(name=guild.name, icon_url=guild.icon)
        roles_display = ", ".join(roles)
        if len(roles_display) > 2045:
            roles_display = roles_display[:2045] + "..."
        embed.description = roles_display
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="members")
    async def members(self, ctx: CommieContext):
        """Shows the server member count"""
        await ctx.defer()
        T = await ctx.get_locale()
        guild = ctx.guild
        
        embed = discord.Embed(colour=discord.Color.dark_red(), title=guild.name)
        embed.set_author(name=guild.name, icon_url=ctx.guild.icon)
        embed.add_field(name=T.get("info.members"), value=guild.member_count, inline=True)
        embed.add_field(name=T.get("info.humans"), value=len([m for m in guild.members if not m.bot]), inline=True)
        embed.add_field(name=T.get("info.bots"), value=len([m for m in guild.members if m.bot]), inline=True)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="role")
    @discord.app_commands.describe(role="The role to show information about")
    async def role(self, ctx: CommieContext, *, role: discord.Role):
        """Shows information about a role"""
        await ctx.defer()
        T = await ctx.get_locale()
        
        embed = discord.Embed(colour=role.color, title=role.name)
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.add_field(name="ID", value=role.id, inline=True)
        embed.add_field(name=T.get("info.color"), value=str(role.color), inline=True)
        embed.add_field(name=T.get("info.position"), value=role.position, inline=True)
        embed.add_field(name=T.get("info.membersWithRole"), value=len(role.members), inline=True)
        embed.add_field(name=T.get("info.mentionable"), value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(role.created_at.timestamp())}:D>", inline=False)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="channel")
    @discord.app_commands.describe(channel="The channel to show information about")
    async def channel(self, ctx: CommieContext, *, channel: Optional[discord.abc.GuildChannel]):
        """Shows information about a channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not channel:
            channel = ctx.channel
        embed = discord.Embed(colour=discord.Color.dark_red(), title=channel.name)
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.add_field(name="ID", value=channel.id, inline=True)
        embed.add_field(name=T.get("info.type"), value=str(channel.type).split(".")[-1], inline=True)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(channel.created_at.timestamp())}:D>", inline=False)
        
        if isinstance(channel, discord.TextChannel):
            embed.add_field(name="NSFW?", value="✅" if channel.is_nsfw() else "❌", inline=True)
            embed.add_field(name=T.get("info.topic"), value=channel.topic if channel.topic else "No topic", inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.hybrid_command(name="calendar")
    async def calendar(self, ctx: CommieContext):
        """Shows a calendar"""
        await ctx.defer()

        now = datetime.datetime.now()
        cal = Calendar.TextCalendar()
        cal_str = cal.formatmonth(now.year, now.month)
        await ctx.send(f"```\n{cal_str}\n```")
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command(name="rate", description="Convert a currency to another")
    @discord.app_commands.describe(
        source_code="The currency code, ex: USD",
        target_code="The currency code to convert to, ex: EUR",
        amount="The amount to convert, ex: 2"
    )
    async def rate(self, ctx: CommieContext, source_code: str, target_code: str, amount: float):
        """Converts an amount from a source currency to a target currency"""
        await ctx.defer()
        T = await ctx.get_locale()
        source_code = source_code.upper()
        target_code = target_code.upper()

        res: dict | None = await self.bot.toolkit.request(url=f"https://api.exchangerate-api.com/v4/latest/{source_code}")

        if not res or "rates" not in res:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))
        rate = res["rates"].get(target_code)
        if not rate:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))

        result = round(rate * amount, 6)

        message = f"💱 **`{str(amount).upper()}`** **{source_code}** ➜ **`{result}`** **{target_code}**"
        await ctx.send(message)
    
    @commands.hybrid_group(name="emoji")
    async def emoji(self, ctx: CommieContext):
        """Related emoji commands"""
        ...
    
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.member)
    @emoji.command(name="info")
    @discord.app_commands.describe(emoji="The emoji to show information about")
    async def emoji_info(self, ctx: CommieContext, *, emoji: discord.Emoji):
        """Shows information about an emoji"""
        await ctx.defer()
        T = await ctx.get_locale()
        
        embed = discord.Embed(colour=discord.Color.dark_red(), title=emoji.name)
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.set_image(url=str(emoji.url).replace(".webp", ".png"))
        embed.add_field(name="ID", value=emoji.id, inline=True)
        embed.add_field(name=T.get("info.animated"), value="✅" if emoji.animated else "❌", inline=True)
        embed.add_field(name="Raw:", value=f"```<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>```", inline=False)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(emoji.created_at.timestamp())}:D>", inline=False)
        await ctx.send(embed=embed)
    
    @emoji_info.error
    async def emoji_info_error(self, ctx: CommieContext, error):
        T = await ctx.get_locale()
        if isinstance(error, commands.BadArgument):
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
    
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.member)
    @emoji.command(name="image", aliases=["url", "jumbo"])
    @discord.app_commands.describe(emoji="The emoji to show the image of")
    async def emoji_image(self, ctx: CommieContext, emoji: str):
        """Shows the image of an emoji"""
        await ctx.defer()
        T = await ctx.get_locale()
        try:
            emoji_obj = await commands.EmojiConverter().convert(ctx, emoji)
        except commands.BadArgument:
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
        
        message = f"**{emoji_obj.name}** (`{emoji_obj.id}`)\n{emoji_obj.url.replace('.webp', '.png')}"
        await ctx.send(message)
    
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.bot_has_permissions(manage_emojis=True)
    @commands.has_permissions(manage_emojis=True)
    @emoji.command(name="add")
    @discord.app_commands.describe(url="The URL of the emoji to add", name="The name of the emoji to add")
    async def emoji_add(self, ctx: CommieContext, url: str, name: Optional[str] = "unknown"):
        """Adds an emoji to the server from a URL"""
        await ctx.defer()
        T = await ctx.get_locale()
        emojis = await ctx.guild.fetch_emojis()
        if len(emojis) >= ctx.guild.emoji_limit:
            raise commands.CommandError(T.get("errors.emojiLimitReached"), T.get("errors.emojiLimitReachedHint"))
        try:
            img_data = await self.bot.toolkit.request(url=url, extract="bytes")
            if not img_data:
                raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
            new_emoji = await ctx.guild.create_custom_emoji(name=name, image=img_data)
            message = f"{T.get('utility.emojiAdded')}\n**{new_emoji.name}** (`{new_emoji.id}`)\n{new_emoji.url.replace('.webp', '.png')}"
            await ctx.send(message)
        except commands.CommandError:
            raise
        except Exception:
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
    
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.bot_has_permissions(manage_emojis=True)
    @commands.has_permissions(manage_emojis=True)
    @emoji.command(name="remove")
    @discord.app_commands.describe(emoji="The emoji to remove from the server")
    async def emoji_remove(self, ctx: CommieContext, emoji: discord.Emoji):
        """Removes an emoji from the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        try:
            await emoji.delete()
            await ctx.send(T.get('utility.emojiRemoved'))
        except Exception:
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="quote")
    @discord.app_commands.describe(message="The message to quote")
    async def quote(self, ctx: CommieContext, *, message: discord.Message):
        """Quotes a message"""
        await ctx.defer()
        T = await ctx.get_locale()
        file_list = [await attachment.to_file() for attachment in message.attachments] if len(message.attachments) else []
        try:
            await ctx.send(content=message.content, embeds=message.embeds, files=file_list, stickers=message.stickers)
        except Exception:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="image", aliases=["img"])
    @discord.app_commands.describe(query="The search query to find an image for")
    async def image(self, ctx: CommieContext, *, query: str):
        """Searches for an image using DuckDuckGo"""
        await ctx.defer()
        T = await ctx.get_locale()
        async with self._image_search_semaphore:
            try:
                results = await asyncio.to_thread(self._ddg_image_search, query)
            except Exception:
                raise commands.CommandError(T.get("errors.noImageResults"), T.get("errors.noImageResultsHint"))
        if not results:
            raise commands.CommandError(T.get("errors.noImageResults"), T.get("errors.noImageResultsHint"))

        links = [r["image"] for r in results]
        embed = discord.Embed(color=discord.Color.dark_red())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.set_image(url=links[0])

        def render(item: str, page: int, total: int):
            embed.set_image(url=item)
            embed.set_footer(text=T.get("paginator.footer", page=page + 1, total=total), icon_url=self.bot.user.display_avatar)

        view = Paginator(data=links, ctx=ctx, locale=T, embed=embed, render=render)
        view.message = await ctx.send(embed=embed, view=view)
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command(name="color", aliases=["hex"])
    @discord.app_commands.describe(hex_code="The hex code of the color to show information about")
    async def color(self, ctx: CommieContext, hex_code: str):
        """Shows information about a color given its hex code"""
        await ctx.defer()
        T = await ctx.get_locale()
        if hex_code.startswith("#"):
            hex_code = hex_code[1:]
        try:
            rgb = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))
        
        r, g, b = rgb
        c = 1 - r / 255
        m = 1 - g / 255
        y = 1 - b / 255
        k = min(c, m, y)
        c = round((c - k) / (1 - k) * 100) if (1 - k) != 0 else 0
        m = round((m - k) / (1 - k) * 100) if (1 - k) != 0 else 0
        y = round((y - k) / (1 - k) * 100) if (1 - k) != 0 else 0
        k = round(k * 100)
        h = round(((60 * ((g - b) / (max(rgb) - min(rgb))) + 360) % 360)) if max(rgb) != min(rgb) else 0
        s = round((0 if max(rgb) == 0 else (max(rgb) - min(rgb)) / max(rgb)) * 100)
        l = round(((max(rgb) + min(rgb)) / 2) / 255 * 100)

        int_value = int(hex_code, 16)

        embed = discord.Embed(color=int_value, title=f"#{hex_code.upper()}")
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.add_field(name="HEX", value=f"#{hex_code.upper()}", inline=True)
        embed.add_field(name="RGB", value=f"rgb({r}, {g}, {b})", inline=True)
        embed.add_field(name="CMYK", value=f"cmyk({c}%, {m}%, {y}%, {k}%)", inline=True)
        embed.add_field(name="INT", value=str(int_value), inline=True)
        embed.add_field(name="HSL", value=f"hsl({h}, {s}%, {l}%)", inline=True)
        embed.set_image(url=f"https://singlecolorimage.com/get/{hex_code.upper()}/400x200")
        await ctx.send(embed=embed)
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="translate", aliases=["translator"])
    @discord.app_commands.describe(target="The target language code", text="The text to translate")
    async def translate(self, ctx: CommieContext, target: str, *, text: str):
        """Translates a text to a target language using Google Translate"""
        await ctx.defer()
        T = await ctx.get_locale()
        target = target.lower().replace("zh-cn", "zh-CN").replace("zh-tw", "zh-TW").replace("ch", "zh-CN")
        translator = GoogleTranslator(source="auto", target="en")
        if target not in translator.get_supported_languages(as_dict=True).values():
            raise commands.CommandError(T.get("errors.invalidLanguage"), T.get("errors.invalidLanguageHint"))
        translator.target = target
        try:
            embed = discord.Embed(color=discord.Color.dark_red(), title=f"**__{translator.source.upper()}__ ➜ __{translator.target.upper()}__**", description=translator.translate(text))
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
            await ctx.send(embed=embed)
        except Exception:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))

    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="httpstatus", aliases=["httpcode", "http"])
    @discord.app_commands.describe(code="The HTTP status code to get information about")
    async def httpstatus(self, ctx: CommieContext, code: int):
        """Shows information about an HTTP status code"""
        await ctx.defer()
        T = await ctx.get_locale()
        try:
            status = HTTPStatus(code)
            await ctx.send(content=f"## **`{status.value}` {status.phrase} {CommieEmojis.Developer}**\n{status.description}\nhttps://http.cat/{status.value}.jpg")
        except ValueError:
            raise commands.CommandError(T.get("errors.invalidHTTPCode"), T.get("errors.invalidHTTPCodeHint"))

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command(name="afk")
    @discord.app_commands.describe(reason="Why you're going AFK (optional)")
    async def afk(self, ctx: CommieContext, *, reason: str = "AFK"):
        """Marks you as AFK; mentioning you will show your reason"""
        await ctx.defer()
        T = await ctx.get_locale()
        reason = reason[:200]
        data = {"reason": reason, "since": int(time.time())}
        await self.bot.sql.set(table="afk_status", id=ctx.author.id, data=data)
        self._afk_cache[ctx.author.id] = {"id": ctx.author.id, **data}
        await ctx.answer(T.get("afk.set", reason=reason), type="success", bold=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        T = self.bot.language.get_locale(await self._guild_language(message.guild.id))

        # Author was AFK and just spoke -- welcome them back.
        if message.author.id in self._afk_cache:
            self._afk_cache.pop(message.author.id, None)
            await self.bot.sql.delete(table="afk_status", id=message.author.id)
            await message.channel.send(T.get("afk.welcomeBack", user=message.author.mention), delete_after=8)

        if not message.mentions:
            return
        # Cap to 3 replies -- avoids a wall of messages on mass-mention spam.
        afk_mentions = [u for u in message.mentions if u.id in self._afk_cache and u.id != message.author.id]
        for user in afk_mentions[:3]:
            data = self._afk_cache[user.id]
            await message.reply(T.get("afk.userIsAfk", user=user.mention, reason=data["reason"]), mention_author=False)

    async def _guild_language(self, guild_id: int) -> str:
        return await self.bot.db.get(table="guilds", id=guild_id, path="language") or self.bot.language.default_language

async def setup(bot: CommieBot):
    await bot.add_cog(Utility(bot))