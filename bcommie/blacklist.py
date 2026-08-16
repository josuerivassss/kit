"""User/guild blacklist: owner-managed ban list enforced on every command
invocation via a bot-wide check (see kernel/bot.py). Backed by the
`blacklist` MongoDB collection, one document per entity:
{"_id": entity_id, "type": "user"|"guild", "reason": str,
 "blacklisted_by": int, "blacklisted_at": int (unix timestamp)}.

The full blacklist is mirrored in two in-memory id sets so the check that
runs on every single command invocation never touches the database --
only add()/remove() mutate Mongo, updating the cache right after.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import discord
from discord.ext import commands

from bcommie.logging_setup import get_logger

if TYPE_CHECKING:
    from bcommie.kernel.bot import CommieBot

logger = get_logger(__name__)

BlacklistType = Literal["user", "guild"]


class BlacklistedError(commands.CheckFailure):
    """Raised by the bot-wide check when the invoking user or guild is
    blacklisted. Handled fully silently in Events.on_command_error, except
    for interaction-based invocations, which get a short ephemeral notice."""


class BlacklistManager:
    """In-memory-cached blacklist, backed by the `blacklist` collection."""

    def __init__(self, bot: CommieBot) -> None:
        self.bot = bot
        self._users: set[int] = set()
        self._guilds: set[int] = set()

    async def load(self) -> None:
        """Populates the in-memory cache from Mongo. Call once at startup."""
        docs = await self.bot.db.find(table="blacklist", filter={})
        self._users = {doc["_id"] for doc in docs if doc.get("type") == "user"}
        self._guilds = {doc["_id"] for doc in docs if doc.get("type") == "guild"}
        logger.info("blacklist_loaded", users=len(self._users), guilds=len(self._guilds))

    def is_blacklisted(self, user_id: int, guild_id: int | None = None) -> bool:
        return user_id in self._users or (guild_id is not None and guild_id in self._guilds)

    def contains(self, entity_id: int, kind: BlacklistType) -> bool:
        return entity_id in (self._users if kind == "user" else self._guilds)

    async def add(self, entity_id: int, kind: BlacklistType, *, reason: str, blacklisted_by: int) -> bool:
        """Adds an entity to the blacklist and purges its stored data.
        Returns False if it was already blacklisted."""
        if self.contains(entity_id, kind):
            return False
        await self.bot.db.set(
            table="blacklist",
            id=entity_id,
            data={
                "type": kind,
                "reason": reason,
                "blacklisted_by": blacklisted_by,
                "blacklisted_at": int(discord.utils.utcnow().timestamp()),
            },
        )
        (self._users if kind == "user" else self._guilds).add(entity_id)
        if kind == "user":
            await self._purge_user_data(entity_id)
        else:
            await self._purge_guild_data(entity_id)
        return True

    async def remove(self, entity_id: int, kind: BlacklistType) -> bool:
        """Removes an entity from the blacklist. Returns False if it wasn't blacklisted."""
        if not self.contains(entity_id, kind):
            return False
        await self.bot.db.delete(table="blacklist", id=entity_id)
        (self._users if kind == "user" else self._guilds).discard(entity_id)
        return True

    async def list_all(self) -> list[dict[str, Any]]:
        return await self.bot.db.find(table="blacklist", filter={}, sort=[("blacklisted_at", -1)])

    # -- data purge -----------------------------------------------------------

    async def _purge_user_data(self, user_id: int) -> None:
        """Wipes every trace of a blacklisted user across Mongo and Postgres,
        including whatever the running cogs still hold in memory."""
        try:
            await self.bot.db.delete(table="dashboard_access", id=user_id)
            await self.bot.db.db["api_keys"].delete_one({"discord_id": str(user_id)})
        except Exception:
            logger.exception("blacklist_purge_user_mongo_failed", user_id=user_id)

        removed_reminder_ids: list[int] = []
        try:
            removed_reminder_ids = [r["id"] for r in await self.bot.sql.find(table="reminders", where={"user_id": user_id})]
            await self.bot.sql.execute('DELETE FROM "reminders" WHERE user_id = $1', user_id)
            await self.bot.sql.execute('DELETE FROM "user_timezones" WHERE id = $1', user_id)
            await self.bot.sql.execute('DELETE FROM "afk_status" WHERE id = $1', user_id)
        except Exception:
            logger.exception("blacklist_purge_user_sql_failed", user_id=user_id)

        reminders_cog = self.bot.get_cog("Reminders")
        if reminders_cog is not None:
            for reminder_id in removed_reminder_ids:
                reminders_cog._reminder_cache.pop(reminder_id, None)
        utility_cog = self.bot.get_cog("Utility")
        if utility_cog is not None:
            utility_cog._afk_cache.pop(user_id, None)

    async def _purge_guild_data(self, guild_id: int) -> None:
        """Wipes every trace of a blacklisted guild across Mongo and Postgres,
        including whatever the running cogs still hold in memory."""
        try:
            await self.bot.db.delete(table="guilds", id=guild_id)
            await self.bot.db.delete(table="tags", id=guild_id)
        except Exception:
            logger.exception("blacklist_purge_guild_mongo_failed", guild_id=guild_id)

        removed_reminder_ids: list[int] = []
        try:
            removed_reminder_ids = [r["id"] for r in await self.bot.sql.find(table="reminders", where={"guild_id": guild_id})]
            await self.bot.sql.execute('DELETE FROM "reminders" WHERE guild_id = $1', guild_id)
            await self.bot.sql.execute('DELETE FROM "giveaways" WHERE guild_id = $1', guild_id)
        except Exception:
            logger.exception("blacklist_purge_guild_sql_failed", guild_id=guild_id)

        reminders_cog = self.bot.get_cog("Reminders")
        if reminders_cog is not None:
            for reminder_id in removed_reminder_ids:
                reminders_cog._reminder_cache.pop(reminder_id, None)