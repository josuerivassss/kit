"""Cross-cutting security utilities.

Provides:
- A sliding-window, per-user command rate limiter (defense against spam/abuse).

"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from discord.ext import commands

from bcommie.logging_setup import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


class SlidingWindowRateLimiter:
    """In-memory sliding-window rate limiter, keyed by (user_id, command).

    Sufficient for a single-process shard. In a multi-process deployment,
    swap the in-memory store for a Redis-backed counter (see MIGRATION.md,
    'Extensibility' section) without changing the calling code.
    """

    def __init__(self, max_calls: int, window_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._hits: dict[tuple[int, str], list[float]] = defaultdict(list)

    def check(self, user_id: int, command_name: str) -> bool:
        """Return True if the call is allowed; False if the limit was hit."""
        key = (user_id, command_name)
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[key] if t > window_start]
        hits.append(now)
        self._hits[key] = hits
        return len(hits) <= self.max_calls


# Experimental decorator for applying the bot's shared rate limiter to a command.
def rate_limited(limiter_attr: str = "rate_limiter") -> Callable[[T], T]:
    """Decorator applying the bot's shared rate limiter to a command.

    Usage:
        @commands.hybrid_command()
        @rate_limited()
        async def my_command(self, ctx): ...
    """

    def decorator(func: T) -> T:
        @wraps(func)
        async def wrapper(self: Any, ctx: commands.Context, *args: Any, **kwargs: Any) -> Any:
            limiter: SlidingWindowRateLimiter = getattr(ctx.bot, limiter_attr)
            if not limiter.check(ctx.author.id, ctx.command.qualified_name if ctx.command else "unknown"):
                await ctx.answer("You are doing that too often. Please wait a moment.", type_="error")
                return None
            return await func(self, ctx, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator