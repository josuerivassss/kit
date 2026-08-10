"""Command-tree introspection: serializes every hybrid command/group into a
JSON-friendly structure combining ext.commands metadata (cooldowns, checks,
aliases) with the synced app_commands data (Discord-assigned IDs, slash
option schema). Powers the owner-only `fetchcommands` command, whose output
feeds the public /commands page on the dashboard.

Permission extraction from `has_permissions`/`bot_has_permissions` checks
relies on inspecting the check predicate's closure -- discord.py exposes no
public API for this. It's tied to the library's internal implementation
(the `perms` free variable name in `ext.commands.core`) and may need
updating if that changes; it fails safe (empty list) rather than raising,
since this tool is invoked manually by the developer, never at runtime.
"""
from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands

from bcommie import __version__
from bcommie.help import parse_params
from bcommie.command_registry import COG_IDS, COMMAND_IDS

_PERMISSION_LABELS: dict[str, str] = {
    "administrator": "Administrator",
    "manage_guild": "Manage Server",
    "manage_channels": "Manage Channels",
    "manage_roles": "Manage Roles",
    "manage_messages": "Manage Messages",
    "manage_emojis": "Manage Emojis",
    "manage_threads": "Manage Threads",
    "ban_members": "Ban Members",
    "kick_members": "Kick Members",
    "moderate_members": "Timeout Members",
    "send_messages": "Send Messages",
    "embed_links": "Embed Links",
    "read_message_history": "Read Message History",
    "create_private_threads": "Create Private Threads",
    "send_messages_in_threads": "Send Messages in Threads",
    "view_channel": "View Channel",
}


def _label(perm: str) -> str:
    return _PERMISSION_LABELS.get(perm, perm.replace("_", " ").title())


def _closure_value(predicate: Any, var_name: str) -> Any | None:
    """Best-effort extraction of a free variable from a check predicate's
    closure. Returns None for custom checks or an unexpected shape."""
    code = getattr(predicate, "__code__", None)
    closure = getattr(predicate, "__closure__", None)
    if code is None or closure is None:
        return None
    try:
        index = code.co_freevars.index(var_name)
    except ValueError:
        return None
    return closure[index].cell_contents


def _extract_checks(command: commands.Command) -> dict[str, Any]:
    result: dict[str, Any] = {"user": [], "bot": [], "guild_only": False, "owner_only": False}
    for check in command.checks:
        qualname = getattr(check, "__qualname__", "")
        if "guild_only" in qualname:
            result["guild_only"] = True
        elif "is_owner" in qualname:
            result["owner_only"] = True
        elif qualname.startswith(("bot_has_permissions", "bot_has_guild_permissions")):
            perms = _closure_value(check, "perms") or {}
            result["bot"].extend(_label(p) for p, granted in perms.items() if granted)
        elif qualname.startswith(("has_permissions", "has_guild_permissions")):
            perms = _closure_value(check, "perms") or {}
            result["user"].extend(_label(p) for p, granted in perms.items() if granted)
    return result


def _extract_cooldown(command: commands.Command) -> dict[str, Any] | None:
    cooldown = command.cooldown
    if cooldown is None:
        return None
    bucket = getattr(command._buckets, "type", None)
    return {"uses": cooldown.rate, "per_seconds": cooldown.per, "bucket": bucket.name if bucket else None}


def _serialize_options(options: list[Any] | None) -> list[dict[str, Any]]:
    if not options:
        return []
    return [
        {"name": o.name, "description": o.description, "type": o.type.name, "required": getattr(o, "required", False)}
        for o in options
        if o.type not in (discord.AppCommandOptionType.subcommand, discord.AppCommandOptionType.subcommand_group)
    ]


def _prefix_usage(command: commands.Command) -> str:
    parent = f"{command.full_parent_name} " if command.full_parent_name else ""
    return f"{parent}{command.name} {parse_params(command.params)}".strip()


def _serialize_command(
    command: commands.Command,
    app_command_id: int | None,
    app_options: list[Any] | None,
) -> dict[str, Any]:
    checks = _extract_checks(command)
    node: dict[str, Any] = {
        "name": command.name,
        "aliases": list(command.aliases),
        "description": command.help or command.short_doc or "",
        "cooldown": _extract_cooldown(command),
        "guild_only": checks["guild_only"],
        "owner_only": checks["owner_only"],
        "permissions": {"user": checks["user"], "bot": checks["bot"]},
        "usage": {"prefix": _prefix_usage(command)},
        "id_slash": str(app_command_id) if app_command_id else None,
        "options": _serialize_options(app_options),
        "supports_placeholders": bool(command.extras.get("supports_placeholders")),
        "protected": bool(command.extras.get("protected")),
        "toggle_id": COMMAND_IDS.get(command.qualified_name),
        "children": [],
    }
    if isinstance(command, commands.HybridGroup):
        for child in command.commands:
            child_app_options = discord.utils.get(app_options or [], name=child.name)
            node["children"].append(
                _serialize_command(child, app_command_id, getattr(child_app_options, "options", None))
            )
    return node


def build_commands_snapshot(bot: commands.Bot, excluded_cogs: set[str]) -> dict[str, Any]:
    """Walks every loaded cog's top-level commands and returns a JSON-ready
    snapshot combining ext.commands metadata with the last-synced app
    command schema (`bot.slash_cache`, populated by tree.sync() in setup_hook)."""
    commands_out: list[dict[str, Any]] = []
    for command in bot.commands:
        cog_name = command.cog_name or "Uncategorized"
        if cog_name in excluded_cogs:
            continue
        app_command = discord.utils.get(bot.slash_cache, name=command.name)
        node = _serialize_command(command, app_command.id if app_command else None, getattr(app_command, "options", None))
        node["category"] = cog_name
        node["category_id"] = COG_IDS.get(cog_name)
        commands_out.append(node)
    return {
        "generated_at": discord.utils.utcnow().isoformat(),
        "bot_version": __version__,
        "command_count": len(commands_out),
        "commands": commands_out,
    }