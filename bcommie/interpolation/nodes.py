"""AST node types produced by the lexer and consumed by the interpreter."""
from __future__ import annotations


class Node:
    """Base AST node. `raw` holds the original text, used as a safe fallback."""

    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(raw={self.raw!r})"


class TextNode(Node):
    """Literal text segment, e.g. TextNode("Hello world")."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        super().__init__(value)
        self.value = value

    def __repr__(self) -> str:
        return f"TextNode(value={self.value!r})"


class PlaceholderNode(Node):
    """A `{name}` or `{name:arg1;arg2}` placeholder.

    `args` is a list of argument groups; each group is itself a list of
    nodes, preserving semicolon boundaries even when an argument contains
    nested placeholders (e.g. `{embed.title:Hello {user.name}}`).
    """

    __slots__ = ("name", "args")

    def __init__(self, raw: str, name: str, args: list[list[Node]]) -> None:
        super().__init__(raw)
        self.name = name
        self.args = args

    def __repr__(self) -> str:
        return f"PlaceholderNode(name={self.name!r}, args={self.args!r})"
