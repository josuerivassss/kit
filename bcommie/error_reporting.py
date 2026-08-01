"""Structured error reporting: sends unhandled command/gateway errors to a
Discord webhook, so the bot owner sees them without exposing anything to
end users (who already get their own localized error message).

Only truly unexpected errors should ever call `report()` -- anything with
its own user-facing message (cooldowns, missing args, permission checks,
explicit `commands.CommandError`) is already handled and must not reach
this reporter, to keep the channel free of noise.
"""
from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import discord

from bcommie.logging_setup import get_logger

if TYPE_CHECKING:
    from bcommie.kernel.bot import CommieBot

logger = get_logger(__name__)

_MAX_QUEUE_SIZE = 50          # drop reports past this instead of growing memory unbounded
_MIN_SEND_INTERVAL = 2.0      # seconds of self-imposed pacing between webhook sends
_DEDUPE_WINDOW = 60.0         # seconds an identical error is suppressed after first report
_DEDUPE_CACHE_MAX = 200       # cap on tracked fingerprints before pruning stale ones
_TRACEBACK_CHAR_LIMIT = 3500  # stays well under Discord's 4096 embed description limit


@dataclass(slots=True)
class _ErrorReport:
    title: str
    error: BaseException
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Recent:
    first_seen: float
    repeats: int = 0


class ErrorReporter:
    """Queues unhandled errors and flushes them to a Discord webhook one at
    a time. Deduplicates repeats and self-throttles independently of the
    rate-limit handling `discord.py` already performs on webhook requests."""

    def __init__(self, bot: CommieBot, webhook_url: str) -> None:
        self.bot = bot
        self.enabled = bool(webhook_url)
        self._webhook_url = webhook_url
        self._webhook: discord.Webhook | None = None
        self._queue: asyncio.Queue[_ErrorReport] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._recent: dict[str, _Recent] = {}
        self._worker_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Builds the webhook (bound to the bot's own HTTP session) and
        starts the background dispatcher. No-op if no URL was configured."""
        if not self.enabled or self._worker_task is not None:
            return
        self._webhook = discord.Webhook.from_url(self._webhook_url, client=self.bot)
        self._worker_task = asyncio.create_task(self._worker(), name="error-reporter-worker")
        logger.info("error_reporter_started")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None

    def report(self, title: str, error: BaseException, **context: Any) -> None:
        """Fire-and-forget: enqueues an error for background delivery.
        Never raises or blocks -- error-handling paths must stay fast."""
        if not self.enabled:
            return
        fingerprint = self._fingerprint(title, error)
        now = time.monotonic()
        recent = self._recent.get(fingerprint)
        if recent is not None and now - recent.first_seen < _DEDUPE_WINDOW:
            recent.repeats += 1
            return  # identical error reported recently -- suppress to avoid channel spam

        repeats = recent.repeats if recent is not None else 0
        self._recent[fingerprint] = _Recent(first_seen=now)
        self._prune_recent(now)

        if repeats:
            context = {**context, "repeated": f"{repeats}x suppressed in the last {int(_DEDUPE_WINDOW)}s"}
        try:
            self._queue.put_nowait(_ErrorReport(title=title, error=error, context=context))
        except asyncio.QueueFull:
            logger.warning("error_reporter_queue_full", title=title)

    @staticmethod
    def _fingerprint(title: str, error: BaseException) -> str:
        frames = traceback.extract_tb(error.__traceback__)
        location = f"{frames[-1].filename}:{frames[-1].lineno}" if frames else "unknown"
        return f"{title}|{type(error).__name__}|{location}"

    def _prune_recent(self, now: float) -> None:
        if len(self._recent) <= _DEDUPE_CACHE_MAX:
            return
        stale = [key for key, entry in self._recent.items() if now - entry.first_seen > _DEDUPE_WINDOW]
        for key in stale:
            self._recent.pop(key, None)

    async def _worker(self) -> None:
        while True:
            report = await self._queue.get()
            try:
                await self._deliver(report)
            except Exception:
                logger.exception("error_reporter_delivery_failed")
            finally:
                self._queue.task_done()
            await asyncio.sleep(_MIN_SEND_INTERVAL)

    async def _deliver(self, report: _ErrorReport) -> None:
        if self._webhook is None:
            return
        try:
            await self._webhook.send(embed=self._build_embed(report), username="Commie Errors")
        except discord.NotFound:
            # Webhook was deleted -- stop trying, avoids an infinite failure loop.
            logger.critical("error_reporter_webhook_missing")
            self.enabled = False
            self._webhook = None
        except discord.HTTPException:
            logger.warning("error_reporter_webhook_send_failed", status=getattr(report, "status", None))

    def _build_embed(self, report: _ErrorReport) -> discord.Embed:
        tb = "".join(traceback.format_exception(type(report.error), report.error, report.error.__traceback__))
        tb = tb[-_TRACEBACK_CHAR_LIMIT:]
        embed = discord.Embed(
            title=report.title[:256],
            description=f"```py\n{tb}\n```",
            colour=discord.Colour.red(),
            timestamp=discord.utils.utcnow(),
        )
        for key, value in report.context.items():
            if value is None:
                continue
            embed.add_field(name=key.replace("_", " ").title(), value=str(value)[:1024], inline=True)
        return embed