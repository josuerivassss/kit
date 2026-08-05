"""Process entrypoint. `python -m bcommie.main` or the `bcommie` console script.
It spins up a single CommieBot instance, which may be sharded across multiple.

Scaling to multiple processes
------------------------------
For a single process, leave SHARD_COUNT/SHARD_IDS unset: discord.py's
AutoShardedBot computes Discord's recommended shard count and runs every
shard's gateway connection inside this one process/event loop.

To split shards across multiple processes/hosts (a "cluster"), set the same
SHARD_COUNT on every process but give each one a disjoint SHARD_IDS range,
e.g.:

    # process A (owns shards 0-3)
    SHARD_COUNT=8 SHARD_IDS=0,1,2,3 CLUSTER_ID=0 python -m bcommie.main
    # process B (owns shards 4-7)
    SHARD_COUNT=8 SHARD_IDS=4,5,6,7 CLUSTER_ID=1 python -m bcommie.main

Every process shares the same MongoDB and PostgreSQL backends, so state
(reminders, tags, config) is consistent cluster-wide regardless
of which process owns a given guild's shard.
"""
from __future__ import annotations

import asyncio
import os

import discord
from discord.ext import commands

from bcommie.config import get_settings
from bcommie.kernel.bot import CommieBot
from bcommie.kernel.tree import CommieTreeClass
from bcommie.logging_setup import configure_logging, get_logger

os.environ.setdefault("JISHAKU_NO_UNDERSCORE", "True")
os.environ.setdefault("JISHAKU_NO_DM_TRACEBACK", "True")
os.environ.setdefault("JISHAKU_HIDE", "True")

logger = get_logger(__name__)

BOT_DOMAIN = "commie.cofue.space"  # used in bot activity and help command footer

def _build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.presences = False
    intents.message_content = True
    intents.members = True
    intents.dm_reactions = False
    return intents


async def _get_prefix(bot: CommieBot, message: discord.Message) -> list[str] | str:
    if message.guild is None:
        return commands.when_mentioned(bot, message)
    prefix = await bot.db.get(table="guilds", id=message.guild.id, path="prefix")
    if prefix is None:
        return commands.when_mentioned_or("commie!", "c!", "c?")(bot, message)
    return commands.when_mentioned_or(prefix)(bot, message)


def build_bot() -> CommieBot:
    """Construct a fully configured (but not yet connected) CommieBot."""
    settings = get_settings()
    configure_logging(settings)

    bot = CommieBot(
        command_prefix=_get_prefix,
        owner_ids=set(settings.owner_id_list),
        case_insensitive=True,
        allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True),
        strip_after_prefix=True,
        intents=_build_intents(),
        help_command=None,
        tree_cls=CommieTreeClass,
        activity=discord.Game(name=BOT_DOMAIN),
        shard_count=settings.shard_count or None,
        shard_ids=settings.shard_id_list,
        settings=settings,
    )
    return bot


async def _amain() -> None:
    bot = build_bot()
    async with bot:
        await bot.start(bot.settings.token)


def run() -> None:
    """Synchronous entrypoint used by the `bcommie` console script."""
    try:
        asyncio.run(_amain()) # type: ignore[arg-type]
    except KeyboardInterrupt:
        logger.info("shutdown_requested")


if __name__ == "__main__":
    run()
