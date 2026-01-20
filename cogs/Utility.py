import re, discord, datetime, calendar as Calendar
from typing import Optional
from discord.ext import commands
from deep_translator import GoogleTranslator
from core.kernel import KitBot, KitContext
from core.ui.paginator import Paginator

class Utility(commands.Cog):

    def __init__(self, bot: KitBot):
        self.bot = bot

    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.command(name="avatar", aliases=["av"])
    async def avatar_alias(self, ctx: KitContext, user: Optional[discord.User]):
        await self.avatar(ctx, user)

    @commands.hybrid_group(name="user")
    async def user(self, ctx: KitContext):
        """Related users commands"""
        ...
    
    @commands.cooldown(1, 4, commands.BucketType.member)
    @user.command(name="avatar")
    async def avatar(self, ctx: KitContext, user: Optional[discord.User]):
        """Shows the avatar of an user"""
        await ctx.defer()
        if not user:
            user = ctx.author._user
        
        embed = discord.Embed(colour=discord.Color.blurple())
        embed.set_author(name=user.name, icon_url=user.display_avatar)
        embed.set_image(url=str(user.display_avatar).replace(".webp", ".png"))
        await ctx.send(embed=embed)

    @commands.cooldown(1, 4, commands.BucketType.member)
    @user.command(name="info")
    async def info(self, ctx: KitContext, user: Optional[discord.User | discord.Member]):
        """Shows information about an user"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not user:
            user = ctx.author
        
        embed = discord.Embed(colour=discord.Color.blurple(), title=user.display_name)
        embed.set_thumbnail(url=str(user.display_avatar).replace(".webp", ".png"))
        embed.set_author(name="@" + user.global_name, icon_url=user.display_avatar)
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
    async def server(self, ctx: KitContext):
        """Related server commands"""
        ...
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="icon")
    async def icon(self, ctx: KitContext):
        """Shows the server icon"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not ctx.guild or not ctx.guild.icon:
            raise commands.CommandError(T.get("errors.noIcon"), T.get("errors.noIconHint"))
        guild = ctx.guild
        embed = discord.Embed(colour=discord.Color.blurple(), title=guild.name)
        embed.set_image(url=str(guild.icon).replace(".webp", ".png"))
        embed.set_author(name=guild.name, icon_url=guild.icon)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="info")
    async def server_info(self, ctx: KitContext):
        """Shows information about the server"""
        await ctx.defer()
        T = await ctx.get_locale()
        guild = ctx.guild
        
        embed = discord.Embed(colour=discord.Color.blurple(), title=guild.name)
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
    async def banner(self, ctx: KitContext):
        """Shows the server banner"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not ctx.guild or not ctx.guild.banner:
            raise commands.CommandError(T.get("errors.noBanner"), T.get("errors.noBannerHint"))
        guild = ctx.guild
        embed = discord.Embed(colour=discord.Color.blurple(), title=guild.name)
        embed.set_image(url=str(guild.banner).replace(".webp", ".png"))
        embed.set_author(name=guild.name, icon_url=guild.icon)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="roles")
    async def roles(self, ctx: KitContext):
        """Shows the server roles"""
        await ctx.defer()
        T = await ctx.get_locale()
        guild = ctx.guild
        roles = [role.mention for role in guild.roles]
        roles.reverse()
        
        embed = discord.Embed(colour=discord.Color.blurple(), title=guild.name)
        embed.set_author(name=guild.name, icon_url=guild.icon)
        roles_display = ", ".join(roles)
        if len(roles_display) > 2045:
            roles_display = roles_display[:2045] + "..."
        embed.description = roles_display
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="members")
    async def members(self, ctx: KitContext):
        """Shows the server member count"""
        await ctx.defer()
        T = await ctx.get_locale()
        guild = ctx.guild
        
        embed = discord.Embed(colour=discord.Color.blurple(), title=guild.name)
        embed.set_author(name=guild.name, icon_url=ctx.guild.icon)
        embed.add_field(name=T.get("info.members"), value=guild.member_count, inline=True)
        embed.add_field(name=T.get("info.humans"), value=len([m for m in guild.members if not m.bot]), inline=True)
        embed.add_field(name=T.get("info.bots"), value=len([m for m in guild.members if m.bot]), inline=True)
        await ctx.send(embed=embed)
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @server.command(name="role")
    async def role(self, ctx: KitContext, *, role: discord.Role):
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
    async def channel(self, ctx: KitContext, *, channel: Optional[discord.abc.GuildChannel]):
        """Shows information about a channel"""
        await ctx.defer()
        T = await ctx.get_locale()
        if not channel:
            channel = ctx.channel
        embed = discord.Embed(colour=discord.Color.blurple(), title=channel.name)
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
    async def calendar(self, ctx: KitContext):
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
    async def rate(self, ctx: KitContext, source_code: str, target_code: str, amount: float):
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
    async def emoji(self, ctx: KitContext):
        """Related emoji commands"""
        ...
    
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.member)
    @emoji.command(name="info")
    async def emoji_info(self, ctx: KitContext, *, emoji: discord.Emoji):
        """Shows information about an emoji"""
        await ctx.defer()
        T = await ctx.get_locale()
        
        embed = discord.Embed(colour=discord.Color.blurple(), title=emoji.name)
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.set_image(url=str(emoji.url).replace(".webp", ".png"))
        embed.add_field(name="ID", value=emoji.id, inline=True)
        embed.add_field(name=T.get("info.animated"), value="✅" if emoji.animated else "❌", inline=True)
        embed.add_field(name="Raw:", value=f"```<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>```", inline=False)
        embed.add_field(name=T.get("info.created"), value=f"<t:{round(emoji.created_at.timestamp())}:D>", inline=False)
        await ctx.send(embed=embed)
    
    @emoji_info.error
    async def emoji_info_error(self, ctx: KitContext, error):
        T = await ctx.get_locale()
        if isinstance(error, commands.BadArgument):
            raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
    
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.member)
    @emoji.command(name="image")
    async def emoji_image(self, ctx: KitContext, emoji: str):
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
    async def emoji_add(self, ctx: KitContext, url: str, name: Optional[str] = "unknown"):
        """Adds an emoji to the server from a URL"""
        await ctx.defer()
        T = await ctx.get_locale()
        emojis = await ctx.guild.fetch_emojis()
        if len(emojis) >= ctx.guild.emoji_limit:
            raise commands.CommandError(T.get("errors.emojiLimitReached"), T.get("errors.emojiLimitReachedHint"))
        try:
            async with self.bot.toolkit.request(url=url, extract="bytes") as resp:
                if resp.status != 200:
                    raise commands.CommandError(T.get("errors.invalidEmoji"), T.get("errors.invalidEmojiHint"))
                img_data = await resp.read()
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
    async def emoji_remove(self, ctx: KitContext, emoji: discord.Emoji):
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
    async def quote(self, ctx: KitContext, *, message: discord.Message):
        """Quotes a message"""
        await ctx.defer()
        T = await ctx.get_locale()
        file_list = [await attachment.to_file() for attachment in message.attachments] if len(message.attachments) else []
        try:
            await ctx.send(content=message.content, embeds=message.embeds, files=file_list, stickers=message.stickers)
        except:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="image", aliases=["img"])
    async def image(self, ctx: KitContext, *, query: str):
        """Searches for an image using Bing Image Search"""
        T = await ctx.get_locale()
        res: bytes | None = await self.bot.toolkit.request(url=f"https://www.bing.com/images/async?q={query}&adlt=on", extract="bytes")
        if not res:
            raise commands.CommandError(T.get("errors.noImageResults"), T.get("errors.noImageResultsHint"))

        links = re.findall(r'murl&quot;:&quot;(.*?)&quot;', res.decode("utf8"))
        if not links:
            raise commands.CommandError(T.get("errors.noImageResults"), T.get("errors.noImageResultsHint"))

        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.set_image(url=links[0])

        def render(item: str, page: int, total: int):
            embed.set_image(url=item)
            embed.set_footer(text=T.get("paginator.footer", page=page + 1, total=total), icon_url=self.bot.user.display_avatar)

        view = Paginator(data=links, ctx=ctx, locale=T, embed=embed, render=render)
        view.message = await ctx.send(embed=embed, view=view)
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command(name="color", aliases=["hex"])
    async def color(self, ctx: KitContext, hex_code: str):
        """Shows information about a color given its hex code"""
        await ctx.defer()
        T = await ctx.get_locale()
        if hex_code.startswith("#"):
            hex_code = hex_code[1:]
        try:
            rgb = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        except:
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
    
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command(name="country", aliases=["nation"])
    async def country(self, ctx: KitContext, country_code: str):
        """Shows information about a country"""
        await ctx.defer()
        T = await ctx.get_locale()
        res: dict | None = await self.bot.toolkit.request(url=f"https://restcountries.com/v3.1/name/{country_code}")

        if not res or not isinstance(res, list) or len(res) == 0:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))
        
        country = res[0]
        name = country.get("name", {}).get("common", T.get("unknown"))
        capital = ", ".join(country.get("capital", [T.get("unknown")]))
        c = list(country.get("currencies", {}).keys())[0]
        currency = country.get("currencies", {}).get(c, {}).get("name", T.get("unknown")) + f" ({c})"
        emoji_of_flag = country.get("flag", "")
        region = country.get("region", T.get("unknown"))
        population = country.get("population", T.get("unknown"))
        area = country.get("area", T.get("unknown"))
        flag_url = country.get("flags", {}).get("png", "")
        
        embed = discord.Embed(color=discord.Color.blurple(), title=name)
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url=flag_url)
        embed.add_field(name=T.get("utility.capital"), value=capital, inline=True)
        embed.add_field(name=T.get("utility.currency"), value=currency, inline=True)
        embed.add_field(name=T.get("utility.flag"), value=emoji_of_flag, inline=True)
        embed.add_field(name=T.get("utility.region"), value=region, inline=True)
        embed.add_field(name=T.get("utility.population"), value=f"{population:,}", inline=True)
        embed.add_field(name=T.get("utility.area"), value=f"{area} km²", inline=True)
        await ctx.send(embed=embed)
    
    @commands.cooldown(1, 8, commands.BucketType.user)
    @commands.hybrid_command(name="translate", aliases=["translator"])
    async def translate(self, ctx: KitContext, target: str, *, text: str):
        """Translates a text to a target language using Google Translate"""
        await ctx.defer()
        T = await ctx.get_locale()
        target = target.lower().replace("zh-cn", "zh-CN").replace("zh-tw", "zh-TW").replace("ch", "zh-CN")
        translator = GoogleTranslator(source="auto", target="en")
        if target not in translator.get_supported_languages(as_dict=True).values():
            raise commands.CommandError(T.get("errors.invalidLanguage"), T.get("errors.invalidLanguageHint"))
        translator.target = target
        try:
            embed = discord.Embed(color=discord.Color.blurple(), title=f"**__{translator.source.upper()}__ ➜ __{translator.target.upper()}__**", description=translator.translate(text))
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
            await ctx.send(embed=embed)
        except Exception:
            raise commands.CommandError(T.get("errors.notInfo"), T.get("errors.notInfoHint"))

async def setup(bot: KitBot):
    await bot.add_cog(Utility(bot))