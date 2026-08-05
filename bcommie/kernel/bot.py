"""The bot kernel: wires together sharding, both databases, and all services.

Key v1 -> v2 change: `CommieBot` now extends `commands.AutoShardedBot` instead
of `commands.Bot`. discord.py transparently manages one gateway connection
per shard inside a single process; combined with `Settings.shard_id_list`,
the *same* process image can also be launched multiple times (one per
cluster/host) each owning a disjoint shard range — see main.py and
MIGRATION.md ("Scaling to multiple processes").
"""
from __future__ import annotations

import datetime
from pkgutil import iter_modules

import discord
from discord.ext import commands

import bcommie.cogs as cogs_package
from bcommie.config import Settings
from bcommie.db.mongo import MongoDatabaseManager
from bcommie.db.postgres import PostgresDatabaseManager
from bcommie.kernel.context import CommieContext
from bcommie.logging_setup import get_logger
from bcommie.managers.language import LanguageManager
from bcommie.security import SlidingWindowRateLimiter
from bcommie.error_reporting import ErrorReporter
from bcommie.toolkit import ToolKit

logger = get_logger(__name__)


class CommieBot(commands.AutoShardedBot):
    """Sharded Discord client wiring together persistence, i18n, and utilities."""

    def __init__(self, *args: object, settings: Settings, **kwargs: object) -> None:
        super().__init__(
            *args,
            allowed_installs=discord.app_commands.AppInstallationType(guild=True, user=False),
            allowed_contexts=discord.app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
            **kwargs,
        )
        self.settings = settings # store settings for later use
        self.start_time = datetime.datetime.now(datetime.UTC)
        self.slash_cache: list[discord.app_commands.AppCommand] = []

        self.toolkit = ToolKit(self)
        self.errors = ErrorReporter(self, settings.error_webhook_url) # Webhook for error reporting (in discord.)
        self.db = MongoDatabaseManager(uri=settings.mongo_uri, db_name=settings.mongo_db_name)
        self.sql = PostgresDatabaseManager(
            dsn=settings.postgres_dsn, min_size=settings.postgres_pool_min, max_size=settings.postgres_pool_max
        )
        self.language = LanguageManager(locales_path="locales", default_language="es")
        self.rate_limiter = SlidingWindowRateLimiter(max_calls=settings.command_rate_limit_per_minute)

    async def get_context(
        self, origin: discord.Message | discord.Interaction, *, cls: type[commands.Context] = CommieContext
    ) -> CommieContext:
        return await super().get_context(origin, cls=cls)  # type: ignore[return-value]

    async def setup_hook(self) -> None:
        """discord.py lifecycle hook: run once before the first gateway connection."""
        await self.toolkit.setup()
        self.errors.start()
        await self.load_extension("jishaku")

        for module_info in iter_modules(cogs_package.__path__):
            if module_info.ispkg:
                continue
            await self.load_extension(f"bcommie.cogs.{module_info.name}")
        logger.info("cogs_loaded")

        await self.sql.connect()
        await self.db.connect()

        self.slash_cache = await self.tree.sync()
        logger.info(
            "bot_ready_to_connect",
            shard_count=self.shard_count,
            cluster_id=self.settings.cluster_id,
        )

    async def close(self) -> None:
        """discord.py lifecycle hook: run once on shutdown. Closes every resource
        symmetrically with what setup_hook() opened."""
        await self.errors.stop()
        await self.toolkit.close()
        await self.sql.close()
        await self.db.close()
        await super().close()
