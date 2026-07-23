"""Reusable confirm/cancel dialog restricted to the invoking user."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from bcommie.locale import Locale
from bcommie.ui.base import BaseView

if TYPE_CHECKING:
    from bcommie.kernel.context import CommieContext


class Confirmator(BaseView):
    """Two-button (confirm/cancel) view with optional async callbacks."""

    def __init__(
        self,
        *,
        ctx: CommieContext,
        locale: Locale,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        on_cancel: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        timeout: int = 30,
    ) -> None:
        super().__init__(ctx=ctx, locale=locale, timeout=timeout)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._apply_locale()

    def _apply_locale(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "confirm_cancel":
                    child.label = self.t.get("confirmator.cancel")
                elif child.custom_id == "confirm_confirm":
                    child.label = self.t.get("confirmator.confirm")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, custom_id="confirm_cancel")
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        if self.on_cancel:
            await self.on_cancel(interaction)
        await self._finalize()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red, custom_id="confirm_confirm")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        if self.on_confirm:
            await self.on_confirm(interaction)
        await self._finalize()
