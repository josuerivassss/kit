"""Decorator used to register placeholder-manager methods with the engine."""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class PlaceholderType(str, Enum):
    """VARIABLE = no-argument lookup (`{user.name}`); FUNCTION = takes args (`{sum:1;2}`)."""

    VARIABLE = "VARIABLE"
    FUNCTION = "FUNCTION"


def placeholder(*, use: PlaceholderType) -> Callable[[F], F]:
    """Mark a method as a placeholder handler. Name is derived by `_` -> `.`."""

    def decorator(func: F) -> F:
        func.__placeholder_type__ = use  # type: ignore[attr-defined]
        func.__placeholder_name__ = func.__name__.replace("_", ".")  # type: ignore[attr-defined]
        return func

    return decorator
