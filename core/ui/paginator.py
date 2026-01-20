"""
Paginator View (core/ui/paginator.py)

Reusable interactive paginator for discord.py based bots.

This paginator is designed to:
- Work with a pre-defined embed (it does NOT create embeds)
- Support custom rendering logic via a render hook
- Support localization through a Locale instance
- Restrict interactions to the command author
- Be reusable across commands and cogs

Typical usage:
- Commands provide the data list
- Commands provide the Locale instance (T)
- Commands optionally provide a render callback
- The paginator handles state, buttons, and rendering

This class is intended to live inside the core UI layer.
"""

from typing import Callable, Any
from core.kernel import KitContext, Locale
import discord


class Paginator(discord.ui.View):
    def __init__(
        self,
        *,
        data: list[Any],
        ctx: KitContext,
        locale: Locale,
        embed: discord.Embed | None = None,
        render: Callable[[Any, int, int], None] | None = None,
        timeout: int = 30
    ):
        super().__init__(timeout=timeout)
        self.data = data
        self.ctx = ctx
        self.t = locale
        self.embed = embed
        self.render = render
        self.page: int = 0
        self.message: discord.Message | None = None
        self.content: str | None = None
        self._apply_locale()
        if len(self.data) <= 1:
            for child in self.children:
                if child.custom_id != "paginator_delete":
                    child.disabled = True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                self.t.get("paginator.notForYou", user=interaction.user.mention),
                ephemeral=True
            )
            return False
        return True

    def _apply_locale(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "paginator_previous":
                    child.label = self.t.get("paginator.previous")
                elif child.custom_id == "paginator_next":
                    child.label = self.t.get("paginator.next")
                elif child.custom_id == "paginator_delete":
                    child.label = self.t.get("paginator.delete")

    def update_item(self):
        if self.render:
            self.render(self.data[self.page], self.page, len(self.data))
            return
        if self.embed:
            self.embed.description = str(self.data[self.page])
            self.embed.set_footer(
                text=self.t.get("paginator.footer", page=self.page + 1, total=len(self.data))
            )

    async def edit(self, interaction: discord.Interaction):
        self.update_item()
        if self.embed:
            await interaction.response.edit_message(embed=self.embed, content=self.content, view=self)
        else:
            await interaction.response.edit_message(content=self.content or str(self.data[self.page]), view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple, custom_id="paginator_previous")
    async def previous(self, interaction: discord.Interaction, _):
        self.page = (self.page - 1) % len(self.data)
        await self.edit(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple, custom_id="paginator_next")
    async def next(self, interaction: discord.Interaction, _):
        self.page = (self.page + 1) % len(self.data)
        await self.edit(interaction)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, custom_id="paginator_delete")
    async def delete(self, interaction: discord.Interaction, _):
        await interaction.response.defer()
        if self.message:
            await self.message.delete()
        self.stop()
