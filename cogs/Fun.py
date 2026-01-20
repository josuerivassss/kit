from discord.ext import commands
from core.kernel import KitBot, KitContext
from core.help import send_help_group
from typing import Optional
import discord, re, random
from PIL import Image, ImageEnhance, ImageOps, ImageFilter

class Fun(commands.Cog):

    def __init__(self, bot: KitBot):
        self.bot = bot
        self.show = "-# Magic Edit 🪄"
    
    @commands.hybrid_command(name="reverse")
    async def text_reverse(self, ctx: KitContext, *, text: str):
        """Reverses a text"""
        await ctx.send(content=text[::-1])
    
    @commands.hybrid_command(name="emojify")
    async def text_emojify(self, ctx: KitContext, *, text: str):
        """Emojifys a text"""
        m = re.sub("([a-zA-Z])", ":regional_indicator_\\1:", text.replace(" ", "  "))
        await ctx.send(m[:2000 - len(":regional_indicator_x:")].lower())

    # Image Manipulation Commands
    @commands.hybrid_group(name="edit")
    async def edit(self, ctx: KitContext):
        """Image manipulation commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("edit")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="communism", aliases=["communist"])
    async def image_communism(self, ctx: KitContext, user: Optional[discord.User]):
        """Makes a communist image of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("communism")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="communist.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="simp")
    async def image_simp(self, ctx: KitContext, user: Optional[discord.User]):
        """Makes a simp image of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("simp")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="simp.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="delete")
    async def image_delete(self, ctx: KitContext, user: Optional[discord.User]):
        """Makes a delete image of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        background = self.bot.toolkit.images.fetch("delete")
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((180, 180))
        background.paste(avatar, (135, 135), avatar)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="delete.png"))
        
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="gay", aliases=["pride", "rainbow"])
    async def image_rainbow(self, ctx: KitContext, user: Optional[discord.User]):
        """Makes a pride-gay image of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("rainbow")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="rainbow.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="deepfry", aliases=["contrast"])
    async def image_deepfry(self, ctx: KitContext, user: Optional[discord.User]):
        """Applies a deepfry filter to the avatar of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageEnhance.Contrast(avatar).enhance(5), filename="deepfry.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="gray", aliases=["bw", "grayscale"])
    async def image_gray(self, ctx: KitContext, user: Optional[discord.User]):
        """Applies a gray-scale filter to the avatar of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageOps.grayscale(avatar), filename="grayscale.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="mirror", aliases=["invert"])
    async def image_mirror(self, ctx: KitContext, user: Optional[discord.User]):
        """Applies a gray-scale filter to the avatar of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageOps.mirror(avatar), filename="deepfry.png"))
    
    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="pixel")
    async def image_pixel(self, ctx: KitContext, user: Optional[discord.User]):
        """Pixelates the avatar of an user"""
        await ctx.defer()
        if user is None:
            user = ctx.author
        avatar = self.bot.toolkit.images.from_bytes(await user.display_avatar.read()).resize((512, 512))
        org_size = avatar.size
        amount = 10
        avatar = avatar.resize(size=(org_size[0] // amount, org_size[1] // amount), resample=0)
        avatar = avatar.resize(org_size, resample=0)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="pixel.png"))
    
    @commands.cooldown(1, 7, commands.BucketType.user)
    @edit.command(name="sonic")
    async def image_sonic(self, ctx: KitContext, *, text: str):
        """Make a sonic says image"""
        await ctx.defer()
        font = self.bot.toolkit.fonts.fetch("Chirp", size=18)
        background = self.bot.toolkit.images.fetch("sonic")
        text = self.bot.toolkit.images.wrap_text(text, font, 350)
        await self.bot.toolkit.images.render_text(background, (365, 65), text, font, fill="White")

        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="sonic.png"))
    
    @commands.cooldown(1, 7, commands.BucketType.user)
    @edit.command(name="titan")
    async def image_titan(self, ctx: KitContext, text1: str, text2: str):
        """Make a titan attack image"""
        await ctx.defer()
        font = self.bot.toolkit.fonts.fetch("Chirp", size=40)
        background = self.bot.toolkit.images.fetch("titan")
        text1 = self.bot.toolkit.images.wrap_text(text1, font, 280)
        text2 = self.bot.toolkit.images.wrap_text(text2, font, 280)
        await self.bot.toolkit.images.render_text(background, (360, 250), text1, font, fill="White")
        await self.bot.toolkit.images.render_text(background, (160, 855), text2, font, fill="White")

        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="titan.png"))
    
    @commands.cooldown(1, 7, commands.BucketType.user)
    @edit.command(name="twoways", aliases=["2ways"])
    async def image_twoways(self, ctx: KitContext, text1: str, text2: str):
        """Make a two ways image"""
        await ctx.defer()
        font = self.bot.toolkit.fonts.fetch("GGsans", size=33, style="bold")
        background = self.bot.toolkit.images.fetch("twoways")
        text1 = self.bot.toolkit.images.wrap_text(text1, font, 300)
        text2 = self.bot.toolkit.images.wrap_text(text2, font, 300)
        await self.bot.toolkit.images.render_text(background, (35, 210), text1, font, stroke_fill="Black", stroke_width=2, align="center", max_width=300)
        await self.bot.toolkit.images.render_text(background, (380, 210), text2, font, stroke_fill="Black", stroke_width=2, align="center", max_width=300)

        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="twoways.png"))
    
    @commands.cooldown(1, 7, commands.BucketType.user)
    @commands.hybrid_command(name="ship")
    async def image_ship(self, ctx: KitContext, user1: discord.User, user2: Optional[discord.User] = None):
        """Ships two users together"""
        await ctx.defer()
        if user2 is None:
            user2 = user1
            user1 = ctx.author
        if user1.id == user2.id:
            return await ctx.send("????")

        r = random.randint(1, 101)
        content = f"**{user1.name}** & **{user2.name}** = **{r}%** compatible! :heart:"
        base = Image.new("RGBA", (750, 250))

        av1 = self.bot.toolkit.images.from_bytes(await user1.display_avatar.read())
        av2 = self.bot.toolkit.images.from_bytes(await user2.display_avatar.read())

        def cover(img: Image.Image, w: int, h: int) -> Image.Image:
            scale = max(w / img.width, h / img.height)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
            left = (img.width - w) // 2
            top = (img.height - h) // 2
            return img.crop((left, top, left + w, top + h))

        bg1 = cover(av1, 375, 250).filter(ImageFilter.GaussianBlur(18))
        bg2 = cover(av2, 375, 250).filter(ImageFilter.GaussianBlur(18))

        base.paste(bg1, (0, 0))
        base.paste(bg2, (375, 0))

        img1 = self.bot.toolkit.images.round_corners(av1.resize((135, 135), Image.Resampling.LANCZOS), 22)
        img2 = self.bot.toolkit.images.round_corners(av2.resize((135, 135), Image.Resampling.LANCZOS), 22)

        base.paste(img1, (135, 58), img1)
        base.paste(img2, (480, 58), img2)

        style = "fire" if r > 80 else "normal" if r > 20 else "broken"
        overlay = self.bot.toolkit.images.fetch(f"heart_{style}").resize((120, 120), Image.Resampling.LANCZOS)
        base.paste(overlay, (base.width // 2 - overlay.width // 2, 65), overlay)

        await ctx.send(content=content+"\n"+self.show, file=self.bot.toolkit.images.to_file(base, "ship.png"))    

async def setup(bot: KitBot):
    await bot.add_cog(Fun(bot))