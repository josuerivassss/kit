from discord.ext import commands
from core.kernel import KitBot, KitContext
from typing import Literal

class Configuration(commands.Cog):
    def __init__(self, bot: KitBot):
        self.bot = bot
    
    @commands.hybrid_command(name="prefix")
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx: KitContext, *, prefix: str):
        """Sets a new prefix for the bot in this server"""
        await ctx.defer()
        T = await ctx.get_locale()
        if len(prefix) > 15:
            raise commands.CommandError(T.get("errors.prefixTooLong", max=15))
        if prefix.lower() == "default" or prefix == "reset":
            # Remove from database to save space
            await self.bot.db.delete(table="guilds", id=ctx.guild.id, field="prefix")
            await ctx.answer(T.get("success.prefixReset", prefix=ctx.clean_prefix), type="success")
        else:
            await self.bot.db.set(table="guilds", id=ctx.guild.id, path="prefix", value=prefix)
            await ctx.answer(T.get("success.prefixSet", prefix=prefix), type="success")
    
    @commands.hybrid_command(name="language", aliases=["locale"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    async def language(self, ctx: KitContext, *, language: Literal["en", "es", "reset"]):
        """Sets a new language for the bot in this server"""
        try:
            await ctx.defer()
            T = await ctx.get_locale()
            if language.lower() == "reset" or language.lower() == "default" or language.lower() == self.bot.language.default_language:
                # Remove from database to save space
                await self.bot.db.delete(table="guilds", id=ctx.guild.id, field="language")
                await ctx.answer(T.get("success.languageReset", language=self.bot.language.default_language), type="success")
            else:
                await self.bot.db.set(table="guilds", id=ctx.guild.id, path="language", value=language)
                await ctx.answer(T.get("success.languageSet", language=language), type="success")
        except Exception as e:
            await ctx.answer("An error occurred while setting the language.", type="error")
            raise e
    

async def setup(bot: KitBot):
    await bot.add_cog(Configuration(bot))