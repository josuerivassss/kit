"""Evaluates a list of AST nodes into a RenderResult."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from bcommie.interpolation.nodes import Node, PlaceholderNode, TextNode
from bcommie.interpolation.render_result import RenderResult

MAX_NESTING = 15  # hard cap: protects against maliciously/accidentally deep templates


class Interpreter:
    """Stateful, single-use evaluator: one instance renders one template call."""

    def __init__(
        self,
        variables: dict[str, Callable[[Any], Awaitable[Any]]],
        functions: dict[str, Callable[..., Awaitable[Any]]],
    ) -> None:
        self.variables = variables
        self.functions = functions
        self.result = RenderResult(content="", embeds=[], emojis=[])

    async def render(self, nodes: list[Node], ctx: Any) -> RenderResult:
        """Evaluate every top-level node, appending to `self.result.content`."""
        i = 0
        while i < len(nodes):
            node = nodes[i]
            try:
                value = await self._eval(node, ctx, 0)
            except Exception:  # noqa: BLE001 - templates must never crash the caller
                value = node.raw
            # A placeholder that occupies an entire line by itself and resolves
            # to nothing (e.g. {embed.title:...}) shouldn't leave a blank line
            # behind -- absorb the following line break along with it.
            if (
                isinstance(node, PlaceholderNode)
                and value == ""
                and (self.result.content == "" or self.result.content.endswith("\n"))
                and i + 1 < len(nodes)
                and isinstance(nodes[i + 1], TextNode)
                and nodes[i + 1].value.startswith("\n")
            ):
                nodes[i + 1] = TextNode(nodes[i + 1].value[1:])
            self.result.content += value
            i += 1
        return self.result

    async def _eval(self, node: Node, ctx: Any, depth: int) -> str:
        if depth > MAX_NESTING:
            return node.raw
        if isinstance(node, TextNode):
            return node.value
        if isinstance(node, PlaceholderNode):
            return await self._eval_placeholder(node, ctx, depth)
        return node.raw

    async def _eval_placeholder(self, node: PlaceholderNode, ctx: Any, depth: int) -> str:
        # Variable placeholder: no arguments, direct lookup.
        if not node.args and node.name in self.variables:
            try:
                value = await self.variables[node.name](ctx)
                return str(value) if value is not None else ""
            except Exception:  # noqa: BLE001 - fail-safe degradation to empty string
                return ""

        # Function placeholder: evaluate each argument group, then invoke.
        if node.name in self.functions:
            try:
                evaluated_args = []
                for arg_group in node.args:
                    arg_value = ""
                    for arg_node in arg_group:
                        arg_value += await self._eval(arg_node, ctx, depth + 1)
                    evaluated_args.append(arg_value)
                value = await self.functions[node.name](ctx, self.result, *evaluated_args)
                return str(value) if value is not None else ""
            except Exception:  # noqa: BLE001
                return ""

        # Unknown placeholder name: degrade to the original literal text.
        return node.raw
