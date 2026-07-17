"""Asynchronous MongoDB manager for document-shaped, low-write-frequency data.

Used for: guild configuration, tags, greeting templates, autorole rules,
locale selection. High-write-frequency / time-range data lives in
`bcommie.db.postgres` instead (see MIGRATION.md for the rationale).
"""
from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import DeleteOne, UpdateOne

from bcommie.logging_setup import get_logger

logger = get_logger(__name__)


class MongoDatabaseManager:
    """Thin async wrapper around Motor exposing a consistent CRUD API."""

    def __init__(self, uri: str, db_name: str = "bcommie") -> None:
        self.uri = uri
        self.db_name = db_name
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    # -- lifecycle ------------------------------------------------------

    async def connect(self) -> None:
        """Open the connection pool. Call once during bot startup."""
        if self.client is None:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            await self.client.admin.command("ping")
            logger.info("mongo_connected", db=self.db_name)

    async def close(self) -> None:
        """Close the connection pool. Call once during bot shutdown."""
        if self.client:
            self.client.close()
            self.client, self.db = None, None
            logger.info("mongo_closed")

    def _require_db(self) -> AsyncIOMotorDatabase:
        if self.db is None:
            raise RuntimeError("MongoDatabaseManager.connect() must be called first")
        return self.db

    # -- core CRUD --------------------------------------------------------

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
        """Set full document fields (`data=`) or a single dotted path (`path=`/`value=`)."""
        db = self._require_db()
        if data is not None and (path is not None or value is not None):
            raise ValueError("Provide either 'data' or 'path'/'value', not both")
        if data is None and path is None:
            raise ValueError("Provide either 'data' or 'path'")
        update_data = data if data is not None else {path: value}
        try:
            result = await db[table].update_one({"_id": id}, {"$set": update_data}, upsert=upsert)
            return result.acknowledged
        except Exception:
            logger.exception("mongo_set_failed", table=table, id=id)
            return False

    async def get(
        self,
        *,
        table: str,
        id: int | str,
        path: str | None = None,
        projection: dict[str, int] | None = None,
    ) -> Any:
        """Fetch a full document, a projection, or a single dotted-path value."""
        db = self._require_db()
        try:
            doc = await db[table].find_one({"_id": id}, projection=projection if not path else None)
            if not doc:
                return None
            if not path:
                return doc
            value: Any = doc
            for key in path.split("."):
                if not isinstance(value, dict):
                    return None
                value = value.get(key)
                if value is None:
                    return None
            return value
        except Exception:
            logger.exception("mongo_get_failed", table=table, id=id)
            return None

    async def update(self, *, table: str, id: int | str, data: dict[str, Any], operator: str = "$set") -> bool:
        """Apply a MongoDB update operator ($set, $inc, $push, $pull, ...) to a document."""
        db = self._require_db()
        try:
            result = await db[table].update_one({"_id": id}, {operator: data})
            return result.modified_count > 0
        except Exception:
            logger.exception("mongo_update_failed", table=table, id=id, operator=operator)
            return False

    async def delete(self, *, table: str, id: int | str, field: str | None = None) -> bool:
        """Delete a whole document, or a single field if `field` is given."""
        db = self._require_db()
        try:
            if field:
                result = await db[table].update_one({"_id": id}, {"$unset": {field: ""}})
                return result.modified_count > 0
            result = await db[table].delete_one({"_id": id})
            return result.deleted_count > 0
        except Exception:
            logger.exception("mongo_delete_failed", table=table, id=id)
            return False

    # -- queries ----------------------------------------------------------

    async def find(
        self,
        *,
        table: str,
        filter: dict[str, Any],
        projection: dict[str, int] | None = None,
        limit: int | None = None,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        """Query multiple documents with optional projection/sort/limit."""
        db = self._require_db()
        try:
            cursor = db[table].find(filter, projection=projection)
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)
            return await cursor.to_list(length=limit)
        except Exception:
            logger.exception("mongo_find_failed", table=table)
            return []

    async def find_one(
        self, *, table: str, filter: dict[str, Any], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        """Query a single document matching an arbitrary filter."""
        db = self._require_db()
        try:
            return await db[table].find_one(filter, projection=projection)
        except Exception:
            logger.exception("mongo_find_one_failed", table=table)
            return None

    async def count(self, *, table: str, filter: dict[str, Any] | None = None) -> int:
        """Count documents matching an optional filter."""
        db = self._require_db()
        try:
            return await db[table].count_documents(filter or {})
        except Exception:
            logger.exception("mongo_count_failed", table=table)
            return 0

    # -- bulk operations ----------------------------------------------------

    async def bulk_insert(self, *, table: str, documents: list[dict[str, Any]], ordered: bool = False) -> int:
        """Insert many documents at once; returns the count actually inserted."""
        db = self._require_db()
        if not documents:
            return 0
        try:
            result = await db[table].insert_many(documents, ordered=ordered)
            return len(result.inserted_ids)
        except Exception:
            logger.exception("mongo_bulk_insert_failed", table=table)
            return 0

    async def bulk_update(self, *, table: str, updates: list[dict[str, Any]], upsert: bool = False) -> int:
        """Apply many {_id, data} updates in one round-trip."""
        db = self._require_db()
        if not updates:
            return 0
        try:
            ops = [UpdateOne({"_id": item["_id"]}, {"$set": item["data"]}, upsert=upsert) for item in updates]
            result = await db[table].bulk_write(ops, ordered=False)
            return result.modified_count + result.upserted_count
        except Exception:
            logger.exception("mongo_bulk_update_failed", table=table)
            return 0

    async def bulk_delete(self, *, table: str, ids: list[int | str]) -> int:
        """Delete many documents by _id in one round-trip."""
        db = self._require_db()
        if not ids:
            return 0
        try:
            ops = [DeleteOne({"_id": doc_id}) for doc_id in ids]
            result = await db[table].bulk_write(ops, ordered=False)
            return result.deleted_count
        except Exception:
            logger.exception("mongo_bulk_delete_failed", table=table)
            return 0

    # -- convenience helpers --------------------------------------------------

    async def exists(self, *, table: str, id: int | str) -> bool:
        """Return True if a document with this _id exists."""
        db = self._require_db()
        try:
            return await db[table].find_one({"_id": id}, projection={"_id": 1}) is not None
        except Exception:
            logger.exception("mongo_exists_failed", table=table, id=id)
            return False

    async def increment(self, *, table: str, id: int | str, field: str, amount: int | float = 1) -> bool:
        """Atomically increment a numeric field."""
        return await self.update(table=table, id=id, data={field: amount}, operator="$inc")

    async def push(self, *, table: str, id: int | str, field: str, value: Any, unique: bool = False) -> bool:
        """Append a value to an array field ($addToSet if unique=True)."""
        return await self.update(table=table, id=id, data={field: value}, operator="$addToSet" if unique else "$push")

    async def pull(self, *, table: str, id: int | str, field: str, value: Any) -> bool:
        """Remove a value from an array field."""
        return await self.update(table=table, id=id, data={field: value}, operator="$pull")
