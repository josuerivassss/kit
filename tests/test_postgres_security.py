"""Unit tests for the SQL-injection defenses in bcommie.db.postgres.

No real database connection is required: `_validate_*` are pure functions
that run before any query is built.
"""
import pytest

from bcommie.db.postgres import PostgresDatabaseManager


@pytest.fixture
def manager():
    return PostgresDatabaseManager(dsn="postgresql://unused/unused")


def test_allowed_table_passes(manager):
    assert manager._validate_table("reminders") == "reminders"


def test_table_not_in_whitelist_is_rejected(manager):
    with pytest.raises(ValueError, match="ALLOWED_TABLES"):
        manager._validate_table("users")  # not whitelisted, even though it's a valid identifier


@pytest.mark.parametrize("table", ["reminders; DROP TABLE reminders;--", "1reminders", "re minders", ""])
def test_malformed_table_names_are_rejected(manager, table):
    with pytest.raises(ValueError):
        manager._validate_table(table)


def test_overlong_table_name_is_rejected(manager):
    with pytest.raises(ValueError):
        manager._validate_table("a" * 64)


def test_valid_column_passes(manager):
    assert manager._validate_column("remind_at") == "remind_at"


@pytest.mark.parametrize("column", ["remind_at; DROP TABLE reminders;--", "1column", "SELECT", "col umn"])
def test_malformed_or_keyword_columns_are_rejected(manager, column):
    with pytest.raises(ValueError):
        manager._validate_column(column)


def test_valid_json_path_passes(manager):
    assert manager._validate_json_path("welcome.enabled") == ["welcome", "enabled"]


@pytest.mark.parametrize("path", ["", "welcome.; DROP TABLE guilds;", "1.bad", "a..b"])
def test_malformed_json_paths_are_rejected(manager, path):
    with pytest.raises(ValueError):
        manager._validate_json_path(path)


async def test_operations_before_connect_raise_runtime_error(manager):
    with pytest.raises(RuntimeError, match="connect"):
        manager._require_pool()
