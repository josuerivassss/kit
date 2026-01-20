from discord.ext import commands
from core.kernel import KitBot, KitContext
from typing import Annotated
from core.ui.paginator import Paginator
from core.ui.confirmator import Confirmator
import discord

"""
TAGS TABLE:

"_id": Guild ID (int)
"tags": {
    "<normalized_tag_name>": {
        "display": Original tag name (str)
        "content": Tag content (str)
        "created_at": Timestamp of creation (int)
        "author": Author ID (int)
}
"""

class TagName(commands.clean_content):
    def __init__(self, *, lower: bool = False):
        self.lower: bool = lower
        super().__init__()

    async def convert(self, ctx: KitContext, argument: str) -> str:
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()
        if not lower or len(lower) > 100 or len(lower) < 1:
            T = await ctx.get_locale()
            raise commands.CommandError(T.get("errors.tagNameInvalid"), T.get("errors.tagNameInvalidHint"))
        first_word, _, _ = lower.partition(' ')
        root: commands.GroupMixin = ctx.bot.get_command('tag')  # type: ignore
        if first_word in root.all_commands:
            T = await ctx.get_locale()
            raise commands.CommandError(T.get("errors.tagNameReserved"), T.get("errors.tagNameReservedHint"))
        return converted.strip() if not self.lower else lower

class Tags(commands.Cog):
    def __init__(self, bot: KitBot):
        self.bot = bot
    
    @commands.hybrid_group(name="tag", invoke_without_command=True, aliases=["tags", "t"])
    async def tags(self, ctx: KitContext, *, tag_name: str):
        """Fetches and displays a tag by name"""
        await self.tag_view(ctx, tag_name=tag_name)
    
    @commands.guild_only()
    @commands.cooldown(1, 2.5, commands.BucketType.member)
    @tags.command(name="view")
    async def tag_view(self, ctx: KitContext, *, tag_name: str):
        """Views a tag"""
        await ctx.defer()
        T = await ctx.get_locale()
        normalized_name = self.bot.toolkit.normalize(tag_name)
        tag = await self.bot.db.get(table="tags", id=ctx.guild.id, path=f"tags.{normalized_name}")
        if tag is None:
            raise commands.CommandError(T.get("errors.tagNotFound", name=tag_name), T.get("errors.tagNotFoundHint"))
        await ctx.send_render(tag["content"])
    
    @tags.autocomplete(name="tag_name")
    async def tag_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        tags = await self.bot.db.get(table="tags", id=interaction.guild.id, path="tags")
        if not tags:
            return []
        current_norm = self.bot.toolkit.normalize(current)

        choices: list[discord.app_commands.Choice[str]] = []

        for normalized_name, tag_data in tags.items():
            display_name = tag_data.get("display", normalized_name)

            if current_norm in normalized_name:
                choices.append(discord.app_commands.Choice(name=display_name, value=normalized_name))
            if len(choices) >= 25:
                break

        return choices
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.has_permissions(manage_guild=True)
    @tags.command(name="create", aliases=["add"])
    async def tag_create(self, ctx: KitContext, tag_name: Annotated[str, TagName], *, content: str):
        """Creates a new tag"""
        await ctx.defer()
        T = await ctx.get_locale()
        tag_count = await self.bot.db.get(table="tags", id=ctx.guild.id, path="tags")
        if tag_count is not None and len(tag_count) >= 15:
            raise commands.CommandError(T.get("errors.tagLimitReached"), T.get("errors.tagLimitReachedHint"))
        normalized_name = self.bot.toolkit.normalize(tag_name)
        if not normalized_name:
            raise commands.CommandError(T.get("errors.tagNameInvalid"), T.get("errors.tagNameInvalidHint"))
        if len(normalized_name) > 20:
            raise commands.CommandError(T.get("errors.tagNameTooLong"), T.get("errors.tagNameTooLongHint"))
        if len(normalized_name) < 1:
            raise commands.CommandError(T.get("errors.tagNameTooShort"), T.get("errors.tagNameTooShortHint"))
        existing_tag = await self.bot.db.get(table="tags", id=ctx.guild.id, path=f"tags.{normalized_name}")
        if existing_tag is not None:
            raise commands.CommandError(T.get("errors.tagAlreadyExists", name=tag_name), T.get("errors.tagAlreadyExistsHint"))
        tag_data = {
            "display": tag_name,
            "content": content,
            "created_at": int(ctx.message.created_at.timestamp()),
            "author": ctx.author.id
        }
        await self.bot.db.set(
            table="tags",
            id=ctx.guild.id,
            path=f"tags.{normalized_name}",
            value=tag_data,
            upsert=True,
        )
        await ctx.answer(T.get("tags.tagCreated", name=tag_name), type="success")
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @commands.has_permissions(manage_guild=True)
    @tags.command(name="update", aliases=["edit"])
    async def tag_update(self, ctx: KitContext, tag_name: Annotated[str, TagName], *, new_content: str):
        """Updates a tag content"""
        await ctx.defer()
        T = await ctx.get_locale()
        normalized_name = self.bot.toolkit.normalize(tag_name)
        if not normalized_name:
            raise commands.CommandError(T.get("errors.tagNameInvalid"), T.get("errors.tagNameInvalidHint"))
        existing_tag = await self.bot.db.get(table="tags", id=ctx.guild.id, path=f"tags.{normalized_name}")
        if existing_tag is None:
            raise commands.CommandError(T.get("errors.tagDoesntExist", name=tag_name), T.get("errors.tagDoesntExistHint"))
        await self.bot.db.set(
            table="tags",
            id=ctx.guild.id,
            path=f"tags.{normalized_name}.content",
            value=new_content
        )
        await ctx.answer(T.get("tags.tagUpdated", name=tag_name), type="success")
    
    @commands.guild_only()
    @commands.cooldown(1, 4, commands.BucketType.member)
    @tags.command(name="delete", aliases=["remove"])
    async def tag_delete(self, ctx: KitContext, tag_name: Annotated[str, TagName]):
        """Removes a tag"""
        await ctx.defer()
        T = await ctx.get_locale()
        normalized_name = self.bot.toolkit.normalize(tag_name)
        tag = await self.bot.db.get(table="tags", id=ctx.guild.id, path=f"tags.{normalized_name}")
        if tag is None:
            raise commands.CommandError(T.get("errors.tagNotFound", name=tag_name), T.get("errors.tagNotFoundHint"))
        await self.bot.db.delete(table="tags", id=ctx.guild.id, field=f"tags.{normalized_name}")
        await ctx.answer(T.get("tags.tagDeleted", name=tag_name), type="success")
    

    @commands.guild_only()
    @commands.is_owner()
    @commands.cooldown(1, 15, commands.BucketType.member)
    @tags.command(name="prune", aliases=["clear"])
    async def tag_prune(self, ctx: KitContext):
        """Prunes all tags in this server"""
        await ctx.defer()
        T = await ctx.get_locale()
        async def confirm(interaction: discord.Interaction):
            await self.bot.db.delete(
                table="tags",
                id=ctx.guild.id,
                field="tags"
            )
            await ctx.answer(T.get("tags.tagsPruned"), type="success")
        async def cancel(_):
            await ctx.answer(T.get("confirmator.cancelled"), type="info")
        embed = discord.Embed(
            title=T.get("confirmator.title"),
            description=T.get("tags.confirmPrune"),
            color=discord.Color.red()
        )
        view = Confirmator(
            ctx=ctx,
            locale=T,
            on_confirm=confirm,
            on_cancel=cancel
        )
        view.message = await ctx.send(embed=embed, view=view)
    
    @commands.guild_only()
    @tags.command(name="list")
    async def tag_list(self, ctx: KitContext):
        """Lists all tags in this guild"""
        await ctx.defer()
        T = await ctx.get_locale()
        data = await self.bot.db.get(table="tags", id=ctx.guild.id, path="tags")
        if not data:
            raise commands.CommandError(T.get("errors.noTags"))
        tags = list(data.values())

        PER_PAGE = 5
        pages: list[list[dict]] = [
            tags[i:i + PER_PAGE]
            for i in range(0, len(tags), PER_PAGE)
        ]
        embed = discord.Embed(
            title=f"**{ctx.guild.name}** TAGS",
            color=discord.Color.blurple()
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        def render(page_items: list[dict], page: int, total: int):
            embed.description = ""
            start_index = page * PER_PAGE
            lines = []
            for i, tag in enumerate(page_items, start=start_index + 1):
                lines.append(f"**{i}.** `{tag['display']}`\t(<@{tag['author']}>)")
            embed.description = "\n".join(lines)
            embed.set_footer(
                text=T.get("paginator.footer", page=page + 1, total=total)
            )
        paginator = Paginator(
            data=pages,
            ctx=ctx,
            locale=T,
            embed=embed,
            render=render
        )
        paginator.update_item()
        paginator.message = await ctx.send(embed=embed, view=paginator)

async def setup(bot: KitBot):
    await bot.add_cog(Tags(bot))