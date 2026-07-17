"""Unit tests for bcommie.interpolation.lexer."""
from bcommie.interpolation.lexer import lex
from bcommie.interpolation.nodes import PlaceholderNode, TextNode


def test_plain_text_produces_single_text_node():
    nodes = lex("Hello world")
    assert len(nodes) == 1
    assert isinstance(nodes[0], TextNode)
    assert nodes[0].value == "Hello world"


def test_simple_variable_placeholder():
    nodes = lex("{user.name}")
    assert len(nodes) == 1
    assert isinstance(nodes[0], PlaceholderNode)
    assert nodes[0].name == "user.name"
    assert nodes[0].args == []


def test_mixed_text_and_placeholder():
    nodes = lex("Hello {user.name}!")
    assert [type(n) for n in nodes] == [TextNode, PlaceholderNode, TextNode]
    assert nodes[0].value == "Hello "
    assert nodes[2].value == "!"


def test_function_with_multiple_arguments():
    nodes = lex("{sum:1;2;3}")
    assert len(nodes) == 1
    node = nodes[0]
    assert node.name == "sum"
    assert len(node.args) == 3
    assert [n.value for group in node.args for n in group] == ["1", "2", "3"]


def test_nested_placeholder_inside_argument():
    nodes = lex("{embed.title:Hello {user.name}}")
    node = nodes[0]
    assert node.name == "embed.title"
    assert len(node.args) == 1
    inner = node.args[0]
    assert isinstance(inner[0], TextNode)
    assert isinstance(inner[1], PlaceholderNode)
    assert inner[1].name == "user.name"


def test_escaped_braces_are_treated_as_literal_text():
    nodes = lex(r"\{literal\}")
    assert len(nodes) == 1
    assert isinstance(nodes[0], TextNode)
    assert nodes[0].value == "{literal}"


def test_escaped_semicolon_does_not_split_argument():
    nodes = lex(r"{join:a\;b;c}")
    node = nodes[0]
    assert len(node.args) == 2
    assert node.args[0][0].value == "a;b"
    assert node.args[1][0].value == "c"


def test_unclosed_placeholder_degrades_to_literal_text():
    nodes = lex("{unterminated")
    assert len(nodes) == 1
    assert isinstance(nodes[0], TextNode)
    assert nodes[0].value == "{unterminated"


def test_empty_placeholder_is_literal():
    nodes = lex("{}")
    assert isinstance(nodes[0], TextNode)
    assert nodes[0].value == "{}"


def test_empty_string_produces_no_nodes():
    assert lex("") == []
