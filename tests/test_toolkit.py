"""Unit tests for bcommie.toolkit validation/formatting helpers.

These only exercise pure functions; HTTP/emoji-CDN behavior is covered by
integration tests (see README.md).
"""
import pytest

from bcommie.toolkit import ToolKit


@pytest.fixture
def toolkit():
    return ToolKit.__new__(ToolKit)  # bypass __init__: these methods need no state


@pytest.mark.parametrize("value", ["#fff", "#ffffff", "abc123", "#ABC", "123ABC"])
def test_is_hex_accepts_valid_colors(toolkit, value):
    assert toolkit.is_hex(value) is True


@pytest.mark.parametrize("value", ["", "gggggg", "#12345", "notacolor"])
def test_is_hex_rejects_invalid_colors(toolkit, value):
    assert toolkit.is_hex(value) is False


def test_is_url_accepts_http_and_https(toolkit):
    assert toolkit.is_url("https://example.com/image.png")
    assert toolkit.is_url("http://example.com")


def test_is_url_rejects_non_urls(toolkit):
    assert not toolkit.is_url("not a url")
    assert not toolkit.is_url("ftp://example.com")


def test_cut_truncates_long_text(toolkit):
    assert toolkit.cut("hello world", 5) == "hello..."


def test_cut_leaves_short_text_untouched(toolkit):
    assert toolkit.cut("hi", 10) == "hi"


def test_normalize_slugifies_accents_and_spaces(toolkit):
    assert toolkit.normalize("Canción Épica!!") == "cancion_epica"


def test_normalize_collapses_repeated_separators(toolkit):
    assert toolkit.normalize("a   b---c") == "a_b_c"
