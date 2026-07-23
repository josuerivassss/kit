"""Custom application command tree: forces dm_permission=False on every sync."""
from __future__ import annotations

import discord

from bcommie.logging_setup import get_logger

logger = get_logger(__name__)


class CommieTreeClass(discord.app_commands.CommandTree):
    """Slash-command tree that disables DM usage for every command before syncing."""

    async def sync(
        self, *, guild: discord.abc.Snowflake | None = None
    ) -> list[discord.app_commands.AppCommand]:
        if self.client.application_id is None:
            raise discord.app_commands.MissingApplicationID

        commands_ = self._get_all_commands(guild=guild)
        payload = (
            [await cmd.get_translated_payload(self.translator) for cmd in commands_]
            if self.translator
            else [cmd.to_dict(self) for cmd in commands_]
        )
        for entry in payload:
            entry["dm_permission"] = False

        try:
            if guild is None:
                data = await self._http.bulk_upsert_global_commands(self.client.application_id, payload=payload)
            else:
                data = await self._http.bulk_upsert_guild_commands(
                    self.client.application_id, guild.id, payload=payload
                )
        except discord.HTTPException as exc:
            if exc.status == 400 and exc.code == 50035:
                raise discord.app_commands.CommandSyncFailure(exc, commands_) from None
            raise

        logger.info("commands_synced", count=len(data), guild_id=guild.id if guild else None)
        return [discord.app_commands.AppCommand(data=d, state=self._state) for d in data]
