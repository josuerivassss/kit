"""Configuration cog: per-guild prefix and language settings."""
from discord.ext import commands
from bcommie.kernel import CommieBot, CommieContext, Locale, CommieEmojis, AnswerType
from bcommie.ui.base import BaseView
import discord

class LanguageMenu(discord.ui.Select):
    def __init__(self, *, ctx: CommieContext, locale: Locale):
        self.ctx = ctx
        self.t = locale
        super().__init__(placeholder=self.t.get("info.selectLanguage"), max_values=1, min_values=1, options=[
            discord.SelectOption(label="English", value="en", description="Your adventure starts here!", emoji="🇺🇸"),
            discord.SelectOption(label="Español", value="es", description="Tu aventura comienza aquí!", emoji="🇲🇽")])
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_language = self.values[0]
        await self.ctx.bot.db.set(table="guilds", id=self.ctx.guild.id, path="language", value=selected_language)
        T = self.ctx.bot.language.get_locale(selected_language) # Access the new locale for the selected language without awaiting
        await interaction.followup.send(T.get("success.languageSet", language=selected_language) + " " + CommieEmojis.Heart, ephemeral=True)

class Configuration(commands.Cog):
    def __init__(self, bot: CommieBot):
        self.bot = bot
    
    @commands.hybrid_command(name="prefix")
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    @discord.app_commands.describe(prefix="The new prefix for the bot, or 'reset' to use the default one")
    async def prefix(self, ctx: CommieContext, *, prefix: str):
        """Sets a new prefix for the bot in this server"""
        await ctx.defer()
        T = await ctx.get_locale()
        if len(prefix) > 15:
            raise commands.CommandError(T.get("errors.prefixTooLong", max=15))
        if prefix.lower() == "default" or prefix == "reset":
            # Remove from database to save space cuz yeah
            await self.bot.db.delete(table="guilds", id=ctx.guild.id, field="prefix")
            await ctx.answer(T.get("success.prefixReset", prefix=ctx.clean_prefix), type="success")
        else:
            await self.bot.db.set(table="guilds", id=ctx.guild.id, path="prefix", value=prefix)
            await ctx.answer(T.get("success.prefixSet", prefix=prefix), type="success")
    
    @commands.hybrid_command(name="language", aliases=["locale"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.has_permissions(manage_guild=True)
    async def language(self, ctx: CommieContext):
        """Sets a new language for the bot in this server"""
        try:
            T = await ctx.get_locale()
            v = BaseView(ctx=ctx, locale=T)
            v.add_item(LanguageMenu(ctx=ctx, locale=T))
            v.message = await ctx.answer(T.get("info.selectLanguage"), view=v, ephemeral=True, type=AnswerType.Ok)
        except Exception as e:
            await ctx.answer("An error occurred", type="error")
            raise e

async def setup(bot: CommieBot):
    await bot.add_cog(Configuration(bot))