"""Unit tests for bcommie.timeparse."""
from bcommie.timeparse import ms_to_long, ms_to_short, parse_duration


def test_parse_single_unit():
    assert parse_duration("30s") == 30_000


def test_parse_compound_duration():
    assert parse_duration("1h30m") == (60 * 60 + 30 * 60) * 1000


def test_parse_decimal_amount():
    assert parse_duration("1.5h") == 1.5 * 60 * 60 * 1000


def test_parse_invalid_string_returns_none():
    assert parse_duration("not a duration") is None


def test_parse_is_case_insensitive():
    assert parse_duration("2H") == parse_duration("2h")


def test_ms_to_short_picks_largest_unit():
    assert ms_to_short(90_000) == "2m"  # rounds to nearest minute


def test_ms_to_long_pluralizes():
    assert "minutes" in ms_to_long(5 * 60 * 1000)
    assert "minute" in ms_to_long(1 * 60 * 1000)


def test_ms_to_short_zero():
    assert ms_to_short(0) == "0ms"
