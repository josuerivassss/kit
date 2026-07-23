"""Asynchronous PostgreSQL manager for high-frequency, time-ranged, relational data.

Replaces the v1 embedded DuckDB file. DuckDB only supports a single writer
process, which blocked horizontal scaling (sharding / multi-process
clusters): every shard process would have needed its own file, fragmenting
reminders/giveaways state across processes. PostgreSQL is a proper client-
server database, so every shard/cluster process shares one consistent
connection pool and one source of truth.

Used for: reminders, giveaways, user timezones
Security model is unchanged from v1: table names come from an explicit
whitelist, column names are regex-validated, and every value is bound as a
query parameter (asyncpg never interpolates values into SQL text).
"""
from __future__ import annotations

import json
import re
from typing import Any

import asyncpg

from bcommie.logging_setup import get_logger

logger = get_logger(__name__)

TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
COLUMN_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
JSON_PATH_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_SQL_KEYWORDS = {"SELECT", "DROP", "DELETE", "INSERT", "UPDATE", "FROM", "WHERE"}

ALLOWED_TABLES: set[str] = {"reminders", "giveaways", "user_timezones"}


class PostgresDatabaseManager:
    """Thin async wrapper around an asyncpg connection pool with a CRUD API
    intentionally mirroring `MongoDatabaseManager` (see db/mongo.py)."""

    def __init__(self, dsn: str, *, min_size: int = 2, max_size: int = 10, strict_tables: bool = True) -> None:
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self.strict_tables = strict_tables
        self.pool: asyncpg.Pool | None = None

    # -- lifecycle ------------------------------------------------------

    async def connect(self) -> None:
        """Open the connection pool and run migrations. Call once at startup."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=self.min_size, max_size=self.max_size)
            logger.info("postgres_connected", pool_size=f"{self.min_size}-{self.max_size}")

    async def close(self) -> None:
        """Close the connection pool. Call once at shutdown."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("postgres_closed")

    def _require_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("PostgresDatabaseManager.connect() must be called first")
        return self.pool

    # -- validation (ported 1:1 from the v1 DuckDB security model) --------

    def _validate_table(self, table: str) -> str:
        if len(table) > 63:  # Postgres identifier limit
            raise ValueError(f"Table name too long: {table}")
        if not TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid table name: {table}")
        if self.strict_tables and table not in ALLOWED_TABLES:
            raise ValueError(f"Table '{table}' is not in ALLOWED_TABLES")
        return table

    def _validate_column(self, column: str) -> str:
        if not COLUMN_NAME_PATTERN.match(column) or column.upper() in _SQL_KEYWORDS:
            raise ValueError(f"Invalid column name: {column}")
        return column

    def _validate_json_path(self, path: str) -> list[str]:
        if not path or not JSON_PATH_PATTERN.match(path):
            raise ValueError(f"Invalid JSON path: {path}")
        parts = path.split(".")
        for part in parts:
            self._validate_column(part)
        return parts

    # -- core CRUD --------------------------------------------------------

    async def insert(self, table: str, data: dict[str, Any]) -> bool:
        """Insert a single row. Column names are taken from `data` keys."""
        pool = self._require_pool()
        table = self._validate_table(table)
        columns = [self._validate_column(c) for c in data]
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        query = f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({placeholders})'
        try:
            async with pool.acquire() as conn:
                await conn.execute(query, *data.values())
            return True
        except Exception:
            logger.exception("postgres_insert_failed", table=table)
            return False

    async def set(
        self,
        *,
        table: str,
        id: int | str,
        data: dict[str, Any] | None = None,
        path: str | None = None,
        value: Any = None,
        upsert: bool = True,
    ) -> bool:
        """Upsert full columns (`data=`) or a JSONB path within a `data` column (`path=`/`value=`)."""
        pool = self._require_pool()
        table = self._validate_table(table)
        if data is not None and (path is not None or value is not None):
            raise ValueError("Provide either 'data' or 'path'/'value', not both")
        if data is None and path is None:
            raise ValueError("Provide either 'data' or 'path'")
        if data is not None and "id" in data:
            raise ValueError("'id' must be passed as the 'id' parameter, not inside 'data'")

        try:
            async with pool.acquire() as conn:
                if path is not None:
                    parts = self._validate_json_path(path)
                    pg_path = "{" + ",".join(parts) + "}"
                    if upsert:
                        query = f'''
                            INSERT INTO "{table}" (id, data) VALUES ($1, jsonb_build_object())
                            ON CONFLICT (id) DO NOTHING
                        '''
                        await conn.execute(query, id)
                    update_query = f'UPDATE "{table}" SET data = jsonb_set(coalesce(data, \'{{}}\'::jsonb), $2, $3::jsonb, true) WHERE id = $1'
                    await conn.execute(update_query, id, pg_path, json.dumps(value))
                else:
                    assert data is not None
                    columns = [self._validate_column(c) for c in data]
                    values = list(data.values())
                    col_list = ", ".join(f'"{c}"' for c in ["id", *columns])
                    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns) + 1))
                    if upsert:
                        update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns)
                        query = (
                            f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
                            f'ON CONFLICT (id) DO UPDATE SET {update_clause}'
                        )
                    else:
                        query = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
                    await conn.execute(query, id, *values)
            return True
        except Exception:
            logger.exception("postgres_set_failed", table=table, id=id)
            return False

    async def update(
        self,
        *,
        table: str,
        id: int | str,
        data: dict[str, Any] | None = None,
        path: str | None = None,
        value: Any = None,
    ) -> bool:
        """Update existing columns (`data=`) or a JSONB path (`path=`/`value=`) without inserting."""
        pool = self._require_pool()
        table = self._validate_table(table)
        if data is not None and (path is not None or value is not None):
            raise ValueError("Provide either 'data' or 'path'/'value', not both")
        if data is None and path is None:
            raise ValueError("Provide either 'data' or 'path'")
        try:
            async with pool.acquire() as conn:
                if path is not None:
                    parts = self._validate_json_path(path)
                    pg_path = "{" + ",".join(parts) + "}"
                    query = f'UPDATE "{table}" SET data = jsonb_set(coalesce(data, \'{{}}\'::jsonb), $2, $3::jsonb, true) WHERE id = $1'
                    await conn.execute(query, id, pg_path, json.dumps(value))
                else:
                    assert data is not None
                    columns = [self._validate_column(c) for c in data]
                    set_clause = ", ".join(f'"{c}" = ${i + 2}' for i, c in enumerate(columns))
                    await conn.execute(f'UPDATE "{table}" SET {set_clause} WHERE id = $1', id, *data.values())
            return True
        except Exception:
            logger.exception("postgres_update_failed", table=table, id=id)
            return False

    async def get(
        self, *, table: str, id: int | str, path: str | None = None, columns: list[str] | None = None
    ) -> Any:
        """Fetch a full row, selected columns, or a JSONB path value."""
        pool = self._require_pool()
        table = self._validate_table(table)
        try:
            async with pool.acquire() as conn:
                if path is not None:
                    parts = self._validate_json_path(path)
                    pg_path = "{" + ",".join(parts) + "}"
                    row = await conn.fetchrow(f'SELECT data #> $2 AS value FROM "{table}" WHERE id = $1', id, pg_path)
                    if row is None or row["value"] is None:
                        return None
                    return json.loads(row["value"])
                select_cols = "*" if not columns else ", ".join(f'"{self._validate_column(c)}"' for c in columns)
                row = await conn.fetchrow(f'SELECT {select_cols} FROM "{table}" WHERE id = $1', id)
                return dict(row) if row else None
        except Exception:
            logger.exception("postgres_get_failed", table=table, id=id)
            return None

    async def delete(self, *, table: str, id: int | str) -> bool:
        """Delete a row by id."""
        pool = self._require_pool()
        table = self._validate_table(table)
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(f'DELETE FROM "{table}" WHERE id = $1', id)
            return result.endswith("1")
        except Exception:
            logger.exception("postgres_delete_failed", table=table, id=id)
            return False

    # -- queries ----------------------------------------------------------

    async def find(
        self,
        *,
        table: str,
        where: dict[str, Any],
        columns: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query multiple rows matching an equality filter dict."""
        pool = self._require_pool()
        table = self._validate_table(table)
        select_cols = "*" if not columns else ", ".join(f'"{self._validate_column(c)}"' for c in columns)
        where_keys = [self._validate_column(c) for c in where]
        where_clause = " AND ".join(f'"{c}" = ${i + 1}' for i, c in enumerate(where_keys))
        query = f'SELECT {select_cols} FROM "{table}"'
        if where_clause:
            query += f" WHERE {where_clause}"
        if order_by:
            col, *direction = order_by.strip().split()
            self._validate_column(col)
            query += f' ORDER BY "{col}"'
            if direction and direction[0].upper() in {"ASC", "DESC"}:
                query += f" {direction[0].upper()}"
        if limit:
            query += f" LIMIT {int(limit)}"
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *where.values())
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("postgres_find_failed", table=table)
            return []

    async def find_one(
        self, *, table: str, where: dict[str, Any], columns: list[str] | None = None
    ) -> dict[str, Any] | None:
        """Query a single row matching an equality filter dict."""
        rows = await self.find(table=table, where=where, columns=columns, limit=1)
        return rows[0] if rows else None

    async def count(self, *, table: str, where: dict[str, Any] | None = None) -> int:
        """Count rows matching an optional equality filter dict."""
        pool = self._require_pool()
        table = self._validate_table(table)
        where = where or {}
        where_keys = [self._validate_column(c) for c in where]
        where_clause = " AND ".join(f'"{c}" = ${i + 1}' for i, c in enumerate(where_keys))
        query = f'SELECT COUNT(*) FROM "{table}"'
        if where_clause:
            query += f" WHERE {where_clause}"
        try:
            async with pool.acquire() as conn:
                return await conn.fetchval(query, *where.values())
        except Exception:
            logger.exception("postgres_count_failed", table=table)
            return 0

    # -- bulk operations ----------------------------------------------------

    async def bulk_insert(self, *, table: str, records: list[dict[str, Any]]) -> int:
        """Insert many rows in a single round-trip via COPY-like executemany."""
        pool = self._require_pool()
        if not records:
            return 0
        table = self._validate_table(table)
        columns = [self._validate_column(c) for c in records[0]]
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        query = f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({placeholders})'
        rows = [tuple(record[c] for c in columns) for record in records]
        try:
            async with pool.acquire() as conn:
                await conn.executemany(query, rows)
            return len(records)
        except Exception:
            logger.exception("postgres_bulk_insert_failed", table=table)
            return 0

    async def bulk_delete(self, *, table: str, ids: list[int | str]) -> int:
        """Delete many rows by id in one round-trip."""
        pool = self._require_pool()
        if not ids:
            return 0
        table = self._validate_table(table)
        try:
            async with pool.acquire() as conn:
                result = await conn.execute(f'DELETE FROM "{table}" WHERE id = ANY($1::bigint[])', ids)
            return int(result.split()[-1])
        except Exception:
            logger.exception("postgres_bulk_delete_failed", table=table)
            return 0

    # -- escape hatch for hardcoded, trusted queries -----------------------

    async def execute(self, query: str, *args: Any) -> str | None:
        """Run a trusted, hardcoded, non-SELECT statement. Bypasses table whitelisting."""
        pool = self._require_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception:
            logger.exception("postgres_execute_failed")
            return None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Run a trusted, hardcoded SELECT statement. Bypasses table whitelisting."""
        pool = self._require_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("postgres_fetch_failed")
            return []
