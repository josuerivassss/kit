"""Base view: author-only interaction lock + disable-on-timeout, shared by all UI."""
from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bcommie.kernel.emojis import CommieEmojis
from bcommie.locale import Locale

if TYPE_CHECKING:
    from bcommie.kernel.context import CommieContext


class BaseView(discord.ui.View):
    """Common view behavior: locks interactions to the invoking user and
    disables all components once the view times out or finalizes."""

    def __init__(self, ctx: CommieContext, locale: Locale, timeout: float | None = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None
        self.t = locale
        self.ctx = ctx

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self.message:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        expected_user_id = self.ctx.author.id
        if self.message and self.message.interaction_metadata:
            expected_user_id = self.message.interaction_metadata.user.id

        if interaction.user.id != expected_user_id:
            message = f"{self.t.get('errors.viewNotForYou', user=interaction.user.mention)} {CommieEmojis.Angry}"
            await interaction.response.send_message(message, ephemeral=True)
            return False
        return True

    async def _finalize(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        if self.message:
            await self.message.edit(view=self)
        self.stop()
