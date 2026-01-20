from core.kernel import KitBot, KitTreeClass
import discord, os, asyncio, dotenv
from discord.ext import commands

dotenv.load_dotenv()

os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True" 
os.environ["JISHAKU_HIDE"] = "True"

intents = discord.Intents.default()
intents.presences = False
intents.message_content = True
intents.members = True
intents.dm_reactions = False

async def get_prefix(bot: KitBot, message: discord.Message):
    if message.guild is None:
        return commands.when_mentioned(bot, message)
    prefix = await bot.db.get(table="guilds", id=message.guild.id, path="prefix")
    if prefix is None:
        return commands.when_mentioned_or("hey kit", "kit!")(bot, message)
    return commands.when_mentioned_or(prefix)(bot, message)

bot = KitBot(
    command_prefix=get_prefix,
    owner_ids=[931037124336164957],
    case_insensitive=True,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True),
    strip_after_prefix=True,
    intents=intents,
    help_command=None,
    tree_cls=KitTreeClass,
    activity=discord.Game(name="hey kit")
    )

async def main():
    async with bot:
        await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())