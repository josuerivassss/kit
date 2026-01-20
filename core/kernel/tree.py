from typing import List, Optional
import discord

class KitTreeClass(discord.app_commands.CommandTree):
    # we are creating custom sync
    async def sync(cls, *, guild: Optional[discord.abc.Snowflake] = None) -> List[discord.app_commands.AppCommand]:
        """|coro|
        Syncs the application commands to Discord. (Custom method)
        This also runs the translator to get the translated strings necessary for
        feeding back into Discord.
        This must be called for the application commands to show up.
        Parameters
        -----------
        guild: Optional[:class:`~discord.abc.Snowflake`]
            The guild to sync the commands to. If ``None`` then it
            syncs all global commands instead.
        Raises
        -------
        HTTPException
            Syncing the commands failed.
        CommandSyncFailure
            Syncing the commands failed due to a user related error, typically because
            the command has invalid data. This is equivalent to an HTTP status code of
            400.
        Forbidden
            The client does not have the ``applications.commands`` scope in the guild.
        MissingApplicationID
            The client does not have an application ID.
        TranslationError
            An error occurred while translating the commands.
        Returns
        --------
        List[:class:`AppCommand`]
            The application's commands that got synced.
        """

        if cls.client.application_id is None:
            raise discord.app_commands.MissingApplicationID

        commands: List[discord.app_commands.AppCommand] = cls._get_all_commands(guild=guild)

        translator = cls.translator
        if translator:
            payload = [await command.get_translated_payload(translator) for command in commands]
        else:
            payload = [command.to_dict(cls) for command in commands]
        try:
            for i in range(0, len(payload)):
                payload[i]['dm_permission'] = False
            if guild is None:
                data = await cls._http.bulk_upsert_global_commands(cls.client.application_id, payload=payload)
            else:
                data = await cls._http.bulk_upsert_guild_commands(cls.client.application_id, guild.id, payload=payload)
        except discord.HTTPException as e:
            if e.status == 400 and e.code == 50035:
                raise discord.app_commands.CommandSyncFailure(e, commands) from None
            raise
        
        print(f"[{len(data)}] Commands synced!")
        return [discord.app_commands.AppCommand(data=d, state=cls._state) for d in data]