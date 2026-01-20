from typing import Any, Optional, List, Dict
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import UpdateOne, DeleteOne


class MongoDatabaseManager:
    """
    Asynchronous MongoDB manager with consistent API for static/statistical data.
    Compatible with SQLDatabase pattern to facilitate system migration.
    """
    
    def __init__(self, url: str, db_name: str = "kitdb"):
        self.url = url
        self.db_name = db_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    # ========= LIFECYCLE =========
    
    async def connect(self):
        """Initialize connection. Call in bot.setup_hook()"""
        if self.client is None:
            self.client = AsyncIOMotorClient(self.url)
            self.db = self.client[self.db_name]

    async def close(self):
        """Close connection. Call in bot.close()"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    # ========= CORE CRUD =========
    
    async def set(
        self,
        *,
        table: str,
        id: int | str,
        data: Optional[Dict[str, Any]] = None,
        path: Optional[str] = None,
        value: Any = None,
        upsert: bool = True
    ) -> bool:
        """
        Insert or update document data. Supports two modes:
        1. Full document mode: Pass data dict to update multiple fields
        2. Path mode: Pass path and value to update a specific nested field
        
        Args:
            table: Collection name
            id: Document identifier (_id)
            data: Dictionary with fields to set (mode 1)
            path: Dot-notation path to field (mode 2)
            value: Value to set at path (mode 2)
            upsert: If True, creates document if it doesn't exist
        
        Example:
            # Mode 1: Set multiple fields
            await db.set(
                table="users",
                id=123456789,
                data={
                    "name": "John",
                    "stats": {"level": 5, "xp": 1250},
                    "inventory": ["sword", "shield"]
                }
            )
            
            # Mode 2: Set specific nested field
            await db.set(
                table="guilds",
                id=987654321,
                path="config.prefix",
                value="!"
            )
            
            # Mode 2: Set deeply nested field
            await db.set(
                table="users",
                id=123,
                path="stats.combat.wins",
                value=42
            )
        
        Returns:
            True if operation was successful
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        # Validate input
        if data is not None and (path is not None or value is not None):
            raise ValueError("Cannot use both 'data' and 'path/value' parameters")
        
        if data is None and path is None:
            raise ValueError("Must provide either 'data' or 'path' parameter")
        
        # Build update data
        if data is not None:
            update_data = data
        else:
            update_data = {path: value}
        
        try:
            result = await self.db[table].update_one(
                {"_id": id},
                {"$set": update_data},
                upsert=upsert
            )
            return result.acknowledged
        except Exception as e:
            print(f"MongoDB.set error: {e}")
            return False

    async def get(
        self,
        *,
        table: str,
        id: int | str,
        path: Optional[str] = None,
        projection: Optional[Dict[str, int]] = None
    ) -> Optional[Dict[str, Any]] | Any:
        """
        Retrieve document data. Supports two modes:
        1. Document mode: Returns full document or projected fields
        2. Path mode: Returns specific nested field value
        
        Args:
            table: Collection name
            id: Document identifier (_id)
            path: Dot-notation path to extract specific field
            projection: Fields to include/exclude (ignored if path is set)
        
        Example:
            # Mode 1: Get complete document
            user = await db.get(table="users", id=123)
            
            # Mode 1: Get with projection
            stats = await db.get(
                table="users",
                id=123,
                projection={"stats": 1, "inventory": 1}
            )
            
            # Mode 2: Get specific field
            prefix = await db.get(
                table="guilds",
                id=987,
                path="config.prefix"
            )
            # Returns: "!" (just the value)
            
            # Mode 2: Get deeply nested field
            wins = await db.get(
                table="users",
                id=123,
                path="stats.combat.wins"
            )
            # Returns: 42 (just the value)
        
        Returns:
            - If path is specified: The value at that path, or None if not found
            - If path is None: Dictionary with document, or None if not found
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            # Get the document
            doc = await self.db[table].find_one(
                {"_id": id},
                projection=projection if not path else None
            )
            
            if not doc:
                return None
            
            # If path specified, navigate to the field
            if path:
                value = doc
                for key in path.split("."):
                    if not isinstance(value, dict):
                        return None
                    value = value.get(key)
                    if value is None:
                        return None
                return value
            
            return doc
            
        except Exception as e:
            print(f"MongoDB.get error: {e}")
            return None

    async def update(
        self,
        *,
        table: str,
        id: int | str,
        data: Dict[str, Any],
        operator: str = "$set"
    ) -> bool:
        """
        Update specific fields of an existing document.
        
        Args:
            table: Collection name
            id: Document identifier (_id)
            data: Fields to update
            operator: MongoDB operator ($set, $inc, $push, $pull, etc.)
        
        Example:
            # Update fields
            await db.update(
                table="users",
                id=123,
                data={"stats.xp": 1500, "stats.level": 6}
            )
            
            # Increment values
            await db.update(
                table="users",
                id=123,
                data={"stats.xp": 50},
                operator="$inc"
            )
            
            # Add to array
            await db.update(
                table="users",
                id=123,
                data={"inventory": "potion"},
                operator="$push"
            )
        
        Returns:
            True if at least one document was updated
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            result = await self.db[table].update_one(
                {"_id": id},
                {operator: data}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"MongoDB.update error: {e}")
            return False

    async def delete(
        self,
        *,
        table: str,
        id: int | str,
        field: Optional[str] = None
    ) -> bool:
        """
        Delete a document or specific field.
        
        Args:
            table: Collection name
            id: Document identifier (_id)
            field: Field to delete (None = delete entire document)
        
        Example:
            # Delete document
            await db.delete(table="users", id=123)
            
            # Delete specific field
            await db.delete(table="users", id=123, field="temporary_data")
        
        Returns:
            True if something was deleted
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            if field:
                result = await self.db[table].update_one(
                    {"_id": id},
                    {"$unset": {field: ""}}
                )
                return result.modified_count > 0
            else:
                result = await self.db[table].delete_one({"_id": id})
                return result.deleted_count > 0
        except Exception as e:
            print(f"MongoDB.delete error: {e}")
            return False

    # ========= ADVANCED QUERIES =========
    
    async def find(
        self,
        *,
        table: str,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, int]] = None,
        limit: Optional[int] = None,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search with multiple filters.
        
        Args:
            table: Collection name
            filter: MongoDB filters (can use operators $gt, $in, etc.)
            projection: Fields to include/exclude
            limit: Maximum number of results
            sort: List of tuples (field, direction) for sorting
                  Ex: [("created_at", -1)] = descending
        
        Example:
            # Users with level > 10
            results = await db.find(
                table="users",
                filter={"stats.level": {"$gt": 10}},
                projection={"name": 1, "stats.level": 1},
                sort=[("stats.level", -1)],
                limit=10
            )
            
            # Active guilds
            guilds = await db.find(
                table="guilds",
                filter={"active": True, "premium": {"$in": [True, "trial"]}}
            )
        
        Returns:
            List of matching documents
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            cursor = self.db[table].find(filter, projection=projection)
            
            if sort:
                cursor = cursor.sort(sort)
            if limit:
                cursor = cursor.limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            print(f"MongoDB.find error: {e}")
            return []

    async def find_one(
        self,
        *,
        table: str,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, int]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single document with filters.
        
        Example:
            user = await db.find_one(
                table="users",
                filter={"username": "john_doe"}
            )
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            return await self.db[table].find_one(filter, projection=projection)
        except Exception as e:
            print(f"MongoDB.find_one error: {e}")
            return None

    async def count(
        self,
        *,
        table: str,
        filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Count documents with optional filters.
        
        Example:
            # Total users
            total = await db.count(table="users")
            
            # Premium users
            premium = await db.count(
                table="users",
                filter={"premium": True}
            )
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            return await self.db[table].count_documents(filter or {})
        except Exception as e:
            print(f"MongoDB.count error: {e}")
            return 0

    # ========= BULK OPERATIONS =========
    
    async def bulk_insert(
        self,
        *,
        table: str,
        documents: List[Dict[str, Any]],
        ordered: bool = False
    ) -> int:
        """
        Optimized bulk insertion.
        
        Args:
            table: Collection name
            documents: List of documents to insert (each must have _id)
            ordered: If False, continues inserting even if some fail
        
        Example:
            docs = [
                {"_id": 1, "name": "Alice", "score": 100},
                {"_id": 2, "name": "Bob", "score": 200}
            ]
            inserted = await db.bulk_insert(table="leaderboard", documents=docs)
        
        Returns:
            Number of successfully inserted documents
        """
        if self.db is None or not documents:
            return 0
        
        try:
            result = await self.db[table].insert_many(
                documents,
                ordered=ordered
            )
            return len(result.inserted_ids)
        except Exception as e:
            print(f"MongoDB.bulk_insert error: {e}")
            return 0

    async def bulk_update(
        self,
        *,
        table: str,
        updates: List[Dict[str, Any]],
        upsert: bool = False
    ) -> int:
        """
        Optimized bulk update.
        
        Args:
            table: Collection name
            updates: List of dicts with {_id, data}
            upsert: If True, creates documents that don't exist
        
        Example:
            updates = [
                {"_id": 1, "data": {"score": 150}},
                {"_id": 2, "data": {"score": 250}}
            ]
            updated = await db.bulk_update(table="leaderboard", updates=updates)
        
        Returns:
            Number of updated documents
        """
        if self.db is None or not updates:
            return 0
        
        try:
            operations = [
                UpdateOne(
                    {"_id": item["_id"]},
                    {"$set": item["data"]},
                    upsert=upsert
                )
                for item in updates
            ]
            result = await self.db[table].bulk_write(operations, ordered=False)
            return result.modified_count + result.upserted_count
        except Exception as e:
            print(f"MongoDB.bulk_update error: {e}")
            return 0

    async def bulk_delete(
        self,
        *,
        table: str,
        ids: List[int | str]
    ) -> int:
        """
        Bulk deletion by IDs.
        
        Example:
            deleted = await db.bulk_delete(
                table="users",
                ids=[123, 456, 789]
            )
        
        Returns:
            Number of deleted documents
        """
        if self.db is None or not ids:
            return 0
        
        try:
            operations = [DeleteOne({"_id": id}) for id in ids]
            result = await self.db[table].bulk_write(operations, ordered=False)
            return result.deleted_count
        except Exception as e:
            print(f"MongoDB.bulk_delete error: {e}")
            return 0

    # ========= UTILITIES =========
    
    async def exists(self, *, table: str, id: int | str) -> bool:
        """
        Check if a document exists.
        
        Example:
            if await db.exists(table="users", id=123):
                print("User exists")
        """
        if self.db is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        try:
            return await self.db[table].find_one({"_id": id}, projection={"_id": 1}) is not None
        except Exception as e:
            print(f"MongoDB.exists error: {e}")
            return False

    async def increment(
        self,
        *,
        table: str,
        id: int | str,
        field: str,
        amount: int | float = 1
    ) -> bool:
        """
        Increment a numeric field (atomic operation).
        
        Example:
            # Increment XP
            await db.increment(
                table="users",
                id=123,
                field="stats.xp",
                amount=50
            )
        """
        return await self.update(
            table=table,
            id=id,
            data={field: amount},
            operator="$inc"
        )

    async def push(
        self,
        *,
        table: str,
        id: int | str,
        field: str,
        value: Any,
        unique: bool = False
    ) -> bool:
        """
        Add a value to an array.
        
        Args:
            unique: If True, only adds if value doesn't exist ($addToSet)
        
        Example:
            # Add item to inventory
            await db.push(
                table="users",
                id=123,
                field="inventory",
                value="legendary_sword",
                unique=True
            )
        """
        operator = "$addToSet" if unique else "$push"
        return await self.update(
            table=table,
            id=id,
            data={field: value},
            operator=operator
        )

    async def pull(
        self,
        *,
        table: str,
        id: int | str,
        field: str,
        value: Any
    ) -> bool:
        """
        Remove a value from an array.
        
        Example:
            await db.pull(
                table="users",
                id=123,
                field="inventory",
                value="used_potion"
            )
        """
        return await self.update(
            table=table,
            id=id,
            data={field: value},
            operator="$pull"
        )

    # ========= BACKWARD COMPATIBILITY =========
    
    async def get_field(
        self,
        *,
        table: str,
        id: int | str,
        path: str
    ) -> Any:
        """
        DEPRECATED: Use get() with projection instead.
        Retrieve a specific field using dot notation.
        
        Example:
            xp = await db.get_field(table="users", id=123, path="stats.xp")
        """
        doc = await self.get(table=table, id=id)
        if not doc:
            return None
        
        # Navigate through path (e.g., "stats.xp")
        value = doc
        for key in path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(key)
            if value is None:
                return None
        
        return value

    async def set_field(
        self,
        *,
        table: str,
        id: int | str,
        path: str,
        value: Any
    ) -> bool:
        """
        DEPRECATED: Use update() instead.
        Update a specific field using dot notation.
        
        Example:
            await db.set_field(table="users", id=123, path="stats.xp", value=1500)
        """
        return await self.update(
            table=table,
            id=id,
            data={path: value}
        )