"""Unit tests for bcommie.interpolation.interpreter and interpolator."""
import pytest

from bcommie.interpolation.decorators import PlaceholderType, placeholder
from bcommie.interpolation.interpolator import InterpolationEngine
from bcommie.interpolation.interpreter import MAX_NESTING, Interpreter
from bcommie.interpolation.lexer import lex


class _FakeCtx:
    """Minimal stand-in for CommieContext, just enough for placeholder handlers."""

    def __init__(self, name: str = "Ada"):
        self.author = type("Author", (), {"name": name})()


class _Placeholders:
    @placeholder(use=PlaceholderType.VARIABLE)
    async def user_name(self, ctx):
        return ctx.author.name

    @placeholder(use=PlaceholderType.FUNCTION)
    async def upper(self, ctx, result, text):
        return text.upper()

    @placeholder(use=PlaceholderType.FUNCTION)
    async def boom(self, ctx, result, *_args):
        raise RuntimeError("intentional failure")


@pytest.fixture
def engine():
    return InterpolationEngine(_Placeholders())


async def test_variable_resolution(engine):
    result = await engine.render("Hello {user.name}!", _FakeCtx("Grace"))
    assert result.content == "Hello Grace!"


async def test_function_resolution(engine):
    result = await engine.render("{upper:hello}", _FakeCtx())
    assert result.content == "HELLO"


async def test_unknown_placeholder_falls_back_to_raw_text(engine):
    result = await engine.render("{does.not.exist}", _FakeCtx())
    assert result.content == "{does.not.exist}"


async def test_function_exception_degrades_to_empty_string(engine):
    result = await engine.render("before {boom:x} after", _FakeCtx())
    assert result.content == "before  after"


async def test_depth_guard_prevents_runaway_recursion():
    nodes = lex("{a}")
    interpreter = Interpreter(variables={}, functions={})
    value = await interpreter._eval(nodes[0], _FakeCtx(), MAX_NESTING + 1)
    assert value == nodes[0].raw


def test_get_registered_placeholders_lists_both_kinds(engine):
    registered = engine.get_registered_placeholders()
    assert "user.name" in registered["variables"]
    assert "upper" in registered["functions"]
