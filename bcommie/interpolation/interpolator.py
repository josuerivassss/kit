"""Stateless entry point: discovers placeholder handlers and renders templates."""
from __future__ import annotations

from typing import Any

from bcommie.interpolation.decorators import PlaceholderType
from bcommie.interpolation.interpreter import Interpreter
from bcommie.interpolation.lexer import lex
from bcommie.interpolation.render_result import RenderResult


class InterpolationEngine:
    """Reflects over a placeholder-manager object once, then renders many templates.

    Usage:
        engine = InterpolationEngine(PlaceholderManager())
        result = await engine.render("Hello {user.name}", ctx)
    """

    def __init__(self, placeholder_manager: Any) -> None:
        self._variables: dict[str, Any] = {}
        self._functions: dict[str, Any] = {}
        for attr_name in dir(placeholder_manager):
            if attr_name.startswith("_"):
                continue
            attr = getattr(placeholder_manager, attr_name)
            ptype = getattr(attr, "__placeholder_type__", None)
            if ptype == PlaceholderType.VARIABLE:
                self._variables[attr.__placeholder_name__] = attr
            elif ptype == PlaceholderType.FUNCTION:
                self._functions[attr.__placeholder_name__] = attr

    async def render(self, text: str, ctx: Any) -> RenderResult:
        """Render `text` against `ctx`, returning content + any collected embeds/emojis."""
        if not text:
            return RenderResult(content="", embeds=[], emojis=[])
        nodes = lex(text)
        return await Interpreter(self._variables, self._functions).render(nodes, ctx)

    def get_registered_placeholders(self) -> dict[str, list[str]]:
        """List all discovered placeholder names, grouped by kind (for /help, docs)."""
        return {"variables": list(self._variables), "functions": list(self._functions)}
