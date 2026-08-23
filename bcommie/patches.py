"""Monkeypatches over discord.py CDN assets.

Discord's CDN can flake on the animated `.gif` variant of an avatar/icon/
banner for some accounts (a longstanding platform quirk); the animated
`.webp` variant of the exact same asset always loads. Patching the getters
here, once, at startup means every cog gets the safe format for free --
no call site has to remember to reformat the asset itself.
"""
from __future__ import annotations

import discord

_PATCHED = "_commie_patched_asset"


def _safe(asset: discord.Asset | None) -> discord.Asset | None:
    if asset is None or not asset.is_animated():
        return asset
    return asset.with_format("webp")


def _patch(cls: type, name: str) -> None:
    original = getattr(cls, name, None)
    if original is None or getattr(original.fget, _PATCHED, False):
        return  # not present on this class, or already patched

    def getter(self, _original=original):
        return _safe(_original.fget(self))

    setattr(getter, _PATCHED, True)
    setattr(cls, name, property(getter))


def apply() -> None:
    """Call once at startup, before the bot connects."""
    for cls in (discord.User, discord.ClientUser, discord.Member):
        _patch(cls, "display_avatar")
    _patch(discord.Member, "guild_avatar")
    _patch(discord.Guild, "icon")
    _patch(discord.Guild, "banner")