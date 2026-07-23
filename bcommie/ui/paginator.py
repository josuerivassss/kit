"""Reusable previous/next/delete paginator over an arbitrary data list."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import discord

from bcommie.locale import Locale
from bcommie.ui.base import BaseView

if TYPE_CHECKING:
    from bcommie.kernel.context import CommieContext


class Paginator(BaseView):
    """Paginates over `data`, either via a caller-supplied `render` hook or by
    stringifying each item into a provided embed's description."""

    def __init__(
        self,
        *,
        data: list[Any],
        ctx: CommieContext,
        locale: Locale,
        embed: discord.Embed | None = None,
        render: Callable[[Any, int, int], None] | None = None,
        timeout: int = 30,
    ) -> None:
        super().__init__(ctx=ctx, locale=locale, timeout=timeout)
        self.data = data
        self.embed = embed
        self.render = render
        self.page = 0
        self.content: str | None = None
        self._apply_locale()
        if len(self.data) <= 1:
            for child in self.children:
                if getattr(child, "custom_id", None) != "paginator_delete":
                    child.disabled = True  # type: ignore[attr-defined]

    def _apply_locale(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "paginator_previous":
                    child.label = self.t.get("paginator.previous")
                elif child.custom_id == "paginator_next":
                    child.label = self.t.get("paginator.next")
                elif child.custom_id == "paginator_delete":
                    child.label = self.t.get("paginator.delete")

    def update_item(self) -> None:
        if self.render:
            self.render(self.data[self.page], self.page, len(self.data))
            return
        if self.embed:
            self.embed.description = str(self.data[self.page])
            self.embed.set_footer(text=self.t.get("paginator.footer", page=self.page + 1, total=len(self.data)))

    async def edit(self, interaction: discord.Interaction) -> None:
        self.update_item()
        if self.embed:
            await interaction.response.edit_message(embed=self.embed, content=self.content, view=self)
        else:
            await interaction.response.edit_message(content=self.content or str(self.data[self.page]), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple, custom_id="paginator_previous")
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.page = (self.page - 1) % len(self.data)
        await self.edit(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple, custom_id="paginator_next")
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.page = (self.page + 1) % len(self.data)
        await self.edit(interaction)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, custom_id="paginator_delete")
    async def delete(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        if self.message:
            await self.message.delete()
        self.stop()
