"""Marks a command as protected: it can never be disabled via /enable or
/disable, individually or through its cog. Apply directly above the
`@commands.hybrid_command`/`@commands.command` decorator, since it needs
to operate on the constructed Command object, not the raw callback."""
from __future__ import annotations

from discord.ext.commands import Command


def protected(command: Command) -> Command:
    command.extras["protected"] = True
    return command