"""Tokenizer that turns a template string into a list of AST nodes.

Handles escape sequences (\\{, \\}, \\\\, \\;, \\:), arbitrarily nested
placeholders, and semicolon-separated arguments that may themselves
contain nested placeholders.
"""
from __future__ import annotations

from bcommie.interpolation.nodes import Node, PlaceholderNode, TextNode

ESCAPE_CHAR = "\\"
_ESCAPABLE = {"{", "}", "\\", ";", ":"}


def lex(text: str) -> list[Node]:
    """Parse a template string into a flat list of TextNode/PlaceholderNode."""
    if not text:
        return []

    nodes: list[Node] = []
    buffer = ""
    i, length = 0, len(text)

    while i < length:
        char = text[i]

        if char == ESCAPE_CHAR and i + 1 < length and text[i + 1] in _ESCAPABLE:
            buffer += text[i + 1]
            i += 2
            continue

        if char == "{":
            if buffer:
                nodes.append(TextNode(buffer))
                buffer = ""
            node, consumed = _parse_placeholder(text[i:])
            if node:
                nodes.append(node)
            i += consumed
            continue

        buffer += char
        i += 1

    if buffer:
        nodes.append(TextNode(buffer))
    return nodes


def _parse_placeholder(text: str) -> tuple[Node, int]:
    """Parse one `{...}` placeholder (with brace-depth tracking) starting at index 0."""
    depth, i, length, escaped = 0, 0, len(text), False

    while i < length:
        char = text[i]
        if char == ESCAPE_CHAR and not escaped:
            escaped, i = True, i + 1
            continue
        if escaped:
            escaped, i = False, i + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                raw = text[: i + 1]
                inner = raw[1:-1]
                if not inner.strip():
                    return TextNode(raw), i + 1
                name, args = _parse_arguments(inner)
                return PlaceholderNode(raw, name, args), i + 1
        i += 1

    # Unclosed placeholder: degrade to literal text (fail-safe, never raises).
    return TextNode(text), length


def _parse_arguments(inner: str) -> tuple[str, list[list[Node]]]:
    """Split `name:arg1;arg2` into (name, [[nodes-for-arg1], [nodes-for-arg2]])."""
    colon_pos = _find_separator(inner, ":")
    if colon_pos == -1:
        return inner.strip(), []
    name = inner[:colon_pos].strip()
    arg_strings = _split_arguments(inner[colon_pos + 1 :])
    return name, [lex(arg) for arg in arg_strings]


def _split_arguments(args_str: str) -> list[str]:
    """Split on `;` at brace-depth 0, respecting escapes."""
    if not args_str:
        return []
    segments: list[str] = []
    buffer, depth, escaped = "", 0, False
    i, length = 0, len(args_str)

    while i < length:
        char = args_str[i]
        if char == ESCAPE_CHAR and not escaped:
            escaped, buffer, i = True, buffer + char, i + 1
            continue
        if escaped:
            escaped, buffer, i = False, buffer + char, i + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == ";" and depth == 0:
            if buffer:
                segments.append(buffer)
            buffer, i = "", i + 1
            continue
        buffer += char
        i += 1

    if buffer:
        segments.append(buffer)
    return segments


def _find_separator(text: str, sep: str) -> int:
    """Find the first unescaped `sep` at brace-depth 0, or -1."""
    depth, escaped = 0, False
    for i, char in enumerate(text):
        if char == ESCAPE_CHAR and not escaped:
            escaped = True
            continue
        if escaped:
            escaped = False
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == sep and depth == 0:
            return i
    return -1
