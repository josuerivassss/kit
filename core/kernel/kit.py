import datetime, os, discord
from discord.ext import commands
from core.kernel.context import KitContext
from core.toolkit import ToolKit
from core.managers.LanguageManager import LanguageManager
from core.managers.DatabaseManager import MongoDatabaseManager
from core.managers.SQLDatabaseManager import SQLDatabaseManager
from typing import List

class KitBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs
        )
        self.start_time = datetime.datetime.now()
        # Slash cache
        self.slash_cache: List[discord.app_commands.AppCommand] = []
        # Toolkit instance
        self.toolkit = ToolKit(self)
        # Database manager (MongoDB)
        self.db = MongoDatabaseManager(url=os.getenv("MONGO_URL"), db_name="kitdb")
        # Database manager (DuckDB)
        self.sql = SQLDatabaseManager(
            db_name="kitbot",
            db_directory="./database",
            strict_tables=True,
            auto_create_tables=True
        )
        # Language manager
        self.language = LanguageManager(
            locales_path="locales",
            default_language="es"
        )
    
    # Override get_context to use KitContext
    async def get_context(self, origin, *, cls=KitContext):
        return await super().get_context(origin, cls=cls)

    # Load cogs on startup
    async def setup_hook(self):
        await self.toolkit.setup()
        await self.load_extension("jishaku") # Jishaku for debugging
        for file in os.listdir("./cogs"):
            if file.endswith(".py"):
                await self.load_extension(f"cogs.{file[:-3]}") # Load cog
        await self.sql.connect()
        await self.db.connect()
        print("Connected to MongoDB database.")
        self.slash_cache = await self.tree.sync() # Sync slash commands

    
    # Close the aiohttp session on bot close
    async def close(self):
        await self.toolkit.close()
        await super().close()