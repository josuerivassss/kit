"""Fun cog: Pillow-based avatar/image editing commands (memes, filters, ship, caption, gif)."""
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, CommieEmojis
from bcommie.help import send_help_group
from typing import Optional
import discord, re, random
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageDraw
from assets.gifs import Collection

_CAPTION_MAX_LENGTH = 200
_CAPTION_MAX_DIMENSION = 700
_CAPTION_IDEAL_WIDTH = 500
_CAPTION_MIN_FONT_SIZE = 18
_CAPTION_MAX_FONT_SIZE = 60
_CAPTION_PADDING = 20

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_GIF_HISTORY_SCAN_LIMIT = 20


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    """True if an attachment is an image, by content-type or filename fallback."""
    if attachment.content_type and attachment.content_type.startswith("image/"):
        return True
    return attachment.filename.lower().endswith(_IMAGE_EXTENSIONS)


async def _image_bytes_from_message(ctx: CommieContext, message: discord.Message) -> Optional[bytes]:
    """Attachment first (read directly, no extra HTTP hop), then embed image/thumbnail
    (covers link unfurls like Tenor gifs)."""
    for attachment in message.attachments:
        if _is_image_attachment(attachment):
            return await attachment.read()
    for embed in message.embeds:
        url = embed.image.url if embed.image else None
        url = url or (embed.thumbnail.url if embed.thumbnail else None)
        if url:
            data = await ctx.bot.toolkit.request(method="GET", url=url, extract="bytes")
            if data:
                return data
    return None


async def _referenced_message(ctx: CommieContext) -> Optional[discord.Message]:
    """Resolves the message being replied to, if any (fetching it if not cached)."""
    reference = ctx.message.reference
    if reference is None:
        return None
    if isinstance(reference.resolved, discord.Message):
        return reference.resolved
    try:
        return await ctx.channel.fetch_message(reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def _read_static_avatar(user: discord.User) -> bytes:
    """Reads a user's display avatar, forcing a static frame for GIF
    avatars -- PIL edits only ever touch a single frame, and feeding it the
    raw animated asset wasn't rendering at all."""
    asset = user.display_avatar
    if asset.is_animated():
        asset = asset.with_static_format("png")
    return await asset.read()


async def resolve_image_bytes(
    ctx: CommieContext,
    user: Optional[discord.User] = None,
    *,
    search_history: bool = False,
    history_limit: int = _GIF_HISTORY_SCAN_LIMIT,
    fallback_avatar: bool = True,
) -> Optional[bytes]:
    if user is not None:
        return await _read_static_avatar(user)

    replied = await _referenced_message(ctx)
    if replied is not None:
        data = await _image_bytes_from_message(ctx, replied)
        if data:
            return data

    data = await _image_bytes_from_message(ctx, ctx.message)
    if data:
        return data

    if search_history:
        async for message in ctx.channel.history(limit=history_limit, before=ctx.message):
            data = await _image_bytes_from_message(ctx, message)
            if data:
                return data

    if fallback_avatar:
        return await _read_static_avatar(ctx.author)
    return None


class Fun(commands.Cog):

    def __init__(self, bot: CommieBot):
        self.bot = bot
        self.show = "-# Magic Edit 🪄" + CommieEmojis.Art

    @commands.hybrid_command(name="reverse")
    @discord.app_commands.describe(text="The text to reverse")
    async def text_reverse(self, ctx: CommieContext, *, text: str):
        """Reverses a text"""
        await ctx.send(content=text[::-1])

    @commands.hybrid_command(name="emojify")
    @discord.app_commands.describe(text="The text to emojify")
    async def text_emojify(self, ctx: CommieContext, *, text: str):
        """Emojifys a text"""
        m = re.sub("([a-zA-Z])", ":regional_indicator_\\1:", text.replace(" ", "  "))
        await ctx.send(m[:2000 - len(":regional_indicator_x:")].lower())

    # Image Manipulation Commands
    @commands.hybrid_group(name="edit")
    async def edit(self, ctx: CommieContext):
        """Image manipulation commands"""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command("edit")
            await send_help_group(ctx, cmd, self.bot.slash_cache, await ctx.get_locale())

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="communism", aliases=["communist"])
    @discord.app_commands.describe(user="The user to make a communist image of")
    async def image_communism(self, ctx: CommieContext, user: Optional[discord.User]):
        """Makes a communist image of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("communism")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="communist.png", flatten=True))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="simp")
    @discord.app_commands.describe(user="The user to make a simp image of")
    async def image_simp(self, ctx: CommieContext, user: Optional[discord.User]):
        """Makes a simp image of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("simp")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="simp.png", flatten=True))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="delete")
    @discord.app_commands.describe(user="The user to make a delete image of")
    async def image_delete(self, ctx: CommieContext, user: Optional[discord.User]):
        """Makes a delete image of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        background = self.bot.toolkit.images.fetch("delete")
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((180, 180))
        background.paste(avatar, (135, 135), avatar)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="delete.png"))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="gay", aliases=["pride", "rainbow"])
    @discord.app_commands.describe(user="The user to make a pride-gay image of")
    async def image_rainbow(self, ctx: CommieContext, user: Optional[discord.User]):
        """Makes a pride-gay image of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        overlay = self.bot.toolkit.images.fetch("rainbow")
        avatar.paste(overlay, (0, 0), overlay)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="rainbow.png", flatten=True))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="deepfry", aliases=["contrast"])
    @discord.app_commands.describe(user="The user to make a deepfry image of")
    async def image_deepfry(self, ctx: CommieContext, user: Optional[discord.User]):
        """Applies a deepfry filter to the avatar of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageEnhance.Contrast(avatar).enhance(5), filename="deepfry.png"))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="gray", aliases=["bw", "grayscale"])
    @discord.app_commands.describe(user="The user to make a grayscale image of")
    async def image_gray(self, ctx: CommieContext, user: Optional[discord.User]):
        """Applies a gray-scale filter to the avatar of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageOps.grayscale(avatar), filename="grayscale.png"))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="mirror", aliases=["invert"])
    @discord.app_commands.describe(user="The user to make a mirror image of")
    async def image_mirror(self, ctx: CommieContext, user: Optional[discord.User]):
        """Applies a gray-scale filter to the avatar of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(ImageOps.mirror(avatar), filename="deepfry.png"))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @edit.command(name="pixel")
    @discord.app_commands.describe(user="The user to make a pixelated image of")
    async def image_pixel(self, ctx: CommieContext, user: Optional[discord.User]):
        """Pixelates the avatar of an user"""
        await ctx.defer()
        image_bytes = await resolve_image_bytes(ctx, user)
        avatar = self.bot.toolkit.images.from_bytes(image_bytes).resize((512, 512))
        org_size = avatar.size
        amount = 10
        avatar = avatar.resize(size=(org_size[0] // amount, org_size[1] // amount), resample=0)
        avatar = avatar.resize(org_size, resample=0)
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(avatar, filename="pixel.png"))

    @commands.cooldown(1, 7, commands.BucketType.user)
    @edit.command(name="sonic")
    @discord.app_commands.describe(text="The text to make sonic say")
    async def image_sonic(self, ctx: CommieContext, *, text: str):
        """Make a sonic says image"""
        await ctx.defer()
        font = self.bot.toolkit.fonts.fetch("Chirp", size=18)
        background = self.bot.toolkit.images.fetch("sonic")
        text = self.bot.toolkit.images.wrap_text(text, font, 350)
        await self.bot.toolkit.images.render_text(background, (365, 65), text, font, fill="White")

        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(background, filename="sonic.png"))

    @commands.cooldown(1, 7, commands.BucketType.user)
    @edit.command(name="titan")
    @discord.app_commands.describe(text1="The text for the titan", text2="The text for the person")
    async def image_titan(self, ctx: CommieContext, text1: str, text2: str):
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
    @discord.app_commands.describe(text1="The text for the left side", text2="The text for the right side")
    async def image_twoways(self, ctx: CommieContext, text1: str, text2: str):
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
    @discord.app_commands.describe(user1="The first user to ship", user2="The second user to ship")
    async def image_ship(self, ctx: CommieContext, user1: discord.User, user2: Optional[discord.User] = None):
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

        av1 = self.bot.toolkit.images.from_bytes(await _read_static_avatar(user1))
        av2 = self.bot.toolkit.images.from_bytes(await _read_static_avatar(user2))

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

        await ctx.send(content=content+"\n"+self.show, file=self.bot.toolkit.images.to_file(base, "ship.png", flatten=True))

    async def _build_caption_bar(self, text: str, width: int) -> Image.Image:
        """Renders the white, black bold-text bar shown above the image,
        shrinking the font until the wrapped text fits the target width.
        Uses the emoji-aware text pipeline (measure_text/render_text) so the
        measured height always matches what actually gets drawn, and so
        emoji in the caption render as glyphs instead of tofu boxes.
        Sizes the bar from the text's actual ink (not the font's em box), so
        the padding above and below the text ends up visually equal."""
        max_text_width = width - _CAPTION_PADDING * 2
        font, lines = None, text
        for font_size in range(_CAPTION_MAX_FONT_SIZE, _CAPTION_MIN_FONT_SIZE - 1, -4):
            font = self.bot.toolkit.fonts.fetch("GGsans", size=font_size, style="bold")
            wrapped = self.bot.toolkit.images.wrap_text(text, font, max_text_width)
            text_width, _ = await self.bot.toolkit.images.measure_text(font, wrapped)
            if text_width <= max_text_width:
                lines = wrapped
                break

        split_lines = lines.split("\n")
        spacing = 4
        ink_top = font.getbbox(split_lines[0])[1]
        ink_bottom = font.getbbox(split_lines[-1])[3]
        ink_height = (len(split_lines) - 1) * (font.size + spacing) + ink_bottom - ink_top

        bar = Image.new("RGBA", (width, ink_height + _CAPTION_PADDING * 2), "white")
        await self.bot.toolkit.images.render_text(
            bar, (0, _CAPTION_PADDING - ink_top), lines, font,
            fill=(0, 0, 0, 255), align="center", max_width=width, spacing=spacing,
        )
        return bar

    @commands.cooldown(1, 7, commands.BucketType.user)
    @commands.hybrid_command(name="caption")
    @discord.app_commands.describe(user="Whose image to caption (optional)", text="The caption text")
    async def caption(self, ctx: CommieContext, user: Optional[discord.User], *, text: str):
        """Adds a meme-style caption bar (black text on white) above an image"""
        await ctx.defer()
        T = await ctx.get_locale()
        text = text.strip()
        if not text:
            raise commands.CommandError(T.get("errors.captionEmpty"))
        if len(text) > _CAPTION_MAX_LENGTH:
            raise commands.CommandError(T.get("errors.captionTooLong"), T.get("errors.captionTooLongHint", max=_CAPTION_MAX_LENGTH))

        image_bytes = await resolve_image_bytes(ctx, user)
        base = self.bot.toolkit.images.from_bytes(image_bytes)
        if max(base.size) > _CAPTION_MAX_DIMENSION:
            scale = _CAPTION_MAX_DIMENSION / max(base.size)
            base = base.resize((max(1, int(base.width * scale)), max(1, int(base.height * scale))), Image.Resampling.LANCZOS)
        if base.width < _CAPTION_IDEAL_WIDTH:
            # small sources (most avatars) otherwise cramp even a short caption into a tiny font
            scale = _CAPTION_IDEAL_WIDTH / base.width
            base = base.resize((_CAPTION_IDEAL_WIDTH, max(1, int(base.height * scale))), Image.Resampling.LANCZOS)

        bar = await self._build_caption_bar(text, base.width)
        canvas = Image.new("RGBA", (base.width, base.height + bar.height), "white")
        canvas.paste(bar, (0, 0))
        canvas.paste(base, (0, bar.height), base)

        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(canvas, filename="caption.png"))

    @commands.cooldown(1, 6, commands.BucketType.user)
    @commands.hybrid_command(name="gif")
    async def to_gif(self, ctx: CommieContext):
        """Converts an image into a single-frame GIF, handy for saving to favorites"""
        await ctx.defer()
        T = await ctx.get_locale()
        image_bytes = await resolve_image_bytes(ctx, search_history=True, fallback_avatar=False)
        if image_bytes is None:
            raise commands.CommandError(T.get("errors.noImageFound"), T.get("errors.noImageFoundHint"))

        image = self.bot.toolkit.images.from_bytes(image_bytes).convert("RGB")
        await ctx.send(content=self.show, file=self.bot.toolkit.images.to_file(image, filename="image.gif", format="GIF"))


async def setup(bot: CommieBot):
    await bot.add_cog(Fun(bot))