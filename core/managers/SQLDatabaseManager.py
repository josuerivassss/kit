from typing import Any, Optional, List, Dict, Set
import duckdb
from pathlib import Path
import re
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor


class SQLDatabaseManager:
    """
    Asynchronous DuckDB database manager for high-frequency transactional data.
    DuckDB provides PostgreSQL-compatible SQL with zero-installation local files.
    
    Performance: Often FASTER than PostgreSQL for analytical queries.
    Storage: Single file in {db_directory}/{db_name}.duckdb
    
    Security: 
    - Table names validated against whitelist
    - Column names validated with regex
    - Parameterized queries prevent SQL injection
    - Path operations validate JSON structure
    """
    
    # SQL Injection Protection: Whitelist of allowed table names
    ALLOWED_TABLES: Set[str] = {
        "giveaways",
        "reminders"
    }
    
    # Table schemas with JSON support for flexible data
    TABLE_SCHEMAS: Dict[str, str] = {
        "giveaways": """
            CREATE TABLE IF NOT EXISTS giveaways (
                id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                prize VARCHAR NOT NULL,
                winners_count INTEGER DEFAULT 1,
                ends_at TIMESTAMP NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        "reminders": """
            CREATE TABLE IF NOT EXISTS reminders (
                id BIGINT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT,
                channel_id BIGINT,
                message TEXT,
                remind_at TIMESTAMP NOT NULL,
                reminded BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
    }
    
    # Indexes for optimal query performance
    # Note: DuckDB doesn't support partial indexes (WHERE clause)
    # Using composite indexes instead for similar performance
    TABLE_INDEXES: Dict[str, List[str]] = {
        "giveaways": [
            "CREATE INDEX IF NOT EXISTS idx_giveaways_guild_active ON giveaways(guild_id, active)",
            "CREATE INDEX IF NOT EXISTS idx_giveaways_ends_at_active ON giveaways(ends_at, active)"
        ],
        "reminders": [
            "CREATE INDEX IF NOT EXISTS idx_reminders_user_reminded ON reminders(user_id, reminded)",
            "CREATE INDEX IF NOT EXISTS idx_reminders_remind_at_reminded ON reminders(remind_at, reminded)"
        ]
    }
    
    # Validation patterns
    TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    COLUMN_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    JSON_PATH_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_.]*$')
    
    def __init__(
        self,
        db_name: str = "kitbot",
        db_directory: str = "./database",
        strict_tables: bool = True,
        auto_create_tables: bool = True,
        read_only: bool = False
    ):
        """
        Initialize DuckDB database manager.
        
        Args:
            db_name: Database file name (without .duckdb extension)
            db_directory: Directory to store database file
            strict_tables: If True, only allows tables in ALLOWED_TABLES whitelist
            auto_create_tables: If True, creates tables from TABLE_SCHEMAS on connect()
            read_only: If True, opens database in read-only mode
        
        Security:
            - Table names validated against whitelist (if strict_tables=True)
            - Column names validated with regex pattern
            - All queries use parameterized statements
            - JSON paths validated to prevent injection
        
        Example:
            db = SQLDatabase(db_name="kitbot", db_directory="./database")
        """
        self.db_name = db_name
        self.db_directory = Path(db_directory)
        self.db_path = self.db_directory / f"{db_name}.duckdb"
        self.strict_tables = strict_tables
        self.auto_create_tables = auto_create_tables
        self.read_only = read_only
        self.conn: Optional[duckdb.DuckDBPyConnection] = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Create directory if it doesn't exist
        self.db_directory.mkdir(parents=True, exist_ok=True)

    def _validate_table_name(self, table: str) -> str:
        """
        Validate table name to prevent SQL injection.
        
        Security checks:
        1. Length: max 64 characters
        2. Pattern: alphanumeric + underscores, must start with letter/underscore
        3. Whitelist: must be in ALLOWED_TABLES (if strict_tables=True)
        
        Raises:
            ValueError: If validation fails
        """
        if len(table) > 64:
            raise ValueError(f"Table name too long (max 64 chars): {table}")
        
        if not self.TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid table name format: {table}")
        
        if self.strict_tables and table not in self.ALLOWED_TABLES:
            raise ValueError(
                f"Table '{table}' not in allowed tables. "
                f"Add it to ALLOWED_TABLES or set strict_tables=False"
            )
        
        return table

    def _validate_column_name(self, column: str) -> str:
        """
        Validate column name to prevent SQL injection.
        
        Security checks:
        1. Pattern: alphanumeric + underscores
        2. No SQL keywords or special characters
        
        Raises:
            ValueError: If validation fails
        """
        if not self.COLUMN_NAME_PATTERN.match(column):
            raise ValueError(f"Invalid column name: {column}")
        
        # Prevent SQL keywords (basic check)
        if column.upper() in ('SELECT', 'DROP', 'DELETE', 'INSERT', 'UPDATE', 'FROM', 'WHERE'):
            raise ValueError(f"Column name cannot be SQL keyword: {column}")
        
        return column

    def _validate_json_path(self, path: str) -> List[str]:
        """
        Validate JSON path to prevent injection attacks.
        
        Security checks:
        1. Pattern: alphanumeric, underscores, dots only
        2. No special characters or SQL syntax
        3. Split into components for safe traversal
        
        Args:
            path: Dot-notation path (e.g., "config.prefix")
        
        Returns:
            List of path components
        
        Raises:
            ValueError: If validation fails
        """
        if not path:
            raise ValueError("JSON path cannot be empty")
        
        if not self.JSON_PATH_PATTERN.match(path):
            raise ValueError(f"Invalid JSON path format: {path}")
        
        components = path.split('.')
        
        # Validate each component
        for component in components:
            if not component:
                raise ValueError(f"Empty component in path: {path}")
            if not self.COLUMN_NAME_PATTERN.match(component):
                raise ValueError(f"Invalid path component: {component}")
        
        return components

    def add_table_schema(self, table: str, schema: str, indexes: Optional[List[str]] = None):
        """
        Add a table schema definition that will be created on connect().
        
        Args:
            table: Table name
            schema: CREATE TABLE statement
            indexes: Optional list of CREATE INDEX statements
        
        Example:
            db.add_table_schema(
                "custom_commands",
                '''
                CREATE TABLE IF NOT EXISTS custom_commands (
                    id BIGINT PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    name VARCHAR NOT NULL,
                    response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''',
                indexes=[
                    "CREATE INDEX IF NOT EXISTS idx_custom_commands_guild ON custom_commands(guild_id)"
                ]
            )
        """
        if not self.TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid table name format: {table}")
        
        self.ALLOWED_TABLES.add(table)
        self.TABLE_SCHEMAS[table] = schema
        if indexes:
            self.TABLE_INDEXES[table] = indexes

    async def _run_in_executor(self, func, *args):
        """Run blocking DuckDB operations in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    async def connect(self):
        """
        Initialize database connection and auto-create tables.
        Call in bot.setup_hook()
        
        Database file will be created at: {db_directory}/{db_name}.duckdb
        """
        if self.conn is None:
            def _connect():
                conn = duckdb.connect(
                    str(self.db_path),
                    read_only=self.read_only
                )
                # Configure for better performance
                conn.execute("SET memory_limit='1GB'")
                conn.execute("SET threads TO 4")
                return conn
            
            self.conn = await self._run_in_executor(_connect)
            
            print(f"📁 Database: {self.db_path}")
            
            # Auto-create tables from schemas
            if self.auto_create_tables and not self.read_only:
                for table, schema in self.TABLE_SCHEMAS.items():
                    try:
                        await self.execute(schema)
                        print(f"✓ Table '{table}' ready")
                    except Exception as e:
                        print(f"✗ Failed to create table '{table}': {e}")
                
                # Create indexes
                for table, indexes in self.TABLE_INDEXES.items():
                    for index_query in indexes:
                        try:
                            await self.execute(index_query)
                        except Exception as e:
                            print(f"✗ Failed to create index for '{table}': {e}")

    async def close(self):
        """Close database connection. Call in bot.close()"""
        if self.conn:
            def _close():
                self.conn.close()
            await self._run_in_executor(_close)
            self.conn = None
        
        self.executor.shutdown(wait=True)

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
        Insert or update record data. Supports two modes:
        1. Full record mode: Pass data dict to update multiple columns
        2. Path mode: Pass path and value to update a specific JSON field
        
        Args:
            table: Table name (validated against whitelist)
            id: Primary key identifier
            data: Dictionary with column names and values (mode 1)
            path: JSON path to field (mode 2, requires JSON column named 'data')
            value: Value to set at path (mode 2)
            upsert: If True, creates record if it doesn't exist
        
        Security:
            - Table name validated
            - Column names validated
            - Path validated and sanitized
            - All queries use parameterized statements
        
        Example:
            # Mode 1: Set multiple columns
            await db.set(
                table="giveaways",
                id=123,
                data={
                    "guild_id": 456,
                    "prize": "Discord Nitro",
                    "active": True
                }
            )
            
            # Mode 2: Set nested JSON field
            await db.set(
                table="guild_config",
                id=789,
                path="config.prefix",
                value="!"
            )
        
        Returns:
            True if operation was successful
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        # Validate input
        if data is not None and (path is not None or value is not None):
            raise ValueError("Cannot use both 'data' and 'path/value' parameters")
        
        if data is None and path is None:
            raise ValueError("Must provide either 'data' or 'path' parameter")
        
        def _execute_set():
            # Path mode: Update JSON field
            if path is not None:
                path_components = self._validate_json_path(path)
                
                # Get current JSON data
                result = self.conn.execute(
                    f'SELECT data FROM "{table}" WHERE id = ?', [id]
                ).fetchone()
                
                current_data = result[0] if result and result[0] else {}
                
                # Navigate and set nested value
                nested = current_data
                for key in path_components[:-1]:
                    if key not in nested:
                        nested[key] = {}
                    nested = nested[key]
                nested[path_components[-1]] = value
                
                # Upsert with JSON
                if upsert:
                    self.conn.execute(
                        f'''
                        INSERT INTO "{table}" (id, data) VALUES (?, ?)
                        ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                        ''',
                        [id, json.dumps(current_data)]
                    )
                else:
                    self.conn.execute(
                        f'UPDATE "{table}" SET data = ? WHERE id = ?',
                        [json.dumps(current_data), id]
                    )
            else:
                # Data mode: Update regular columns
                for col in data.keys():
                    self._validate_column_name(col)
                
                columns = ["id"] + list(data.keys())
                placeholders = ["?"] * len(columns)
                values = [id] + list(data.values())
                
                if upsert:
                    update_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in data.keys()])
                    query = f"""
                        INSERT INTO "{table}" ({', '.join(f'"{c}"' for c in columns)})
                        VALUES ({', '.join(placeholders)})
                        ON CONFLICT (id) DO UPDATE SET {update_clause}
                    """
                else:
                    query = f"""
                        INSERT INTO "{table}" ({', '.join(f'"{c}"' for c in columns)})
                        VALUES ({', '.join(placeholders)})
                    """
                
                self.conn.execute(query, values)
            
            return True
        
        try:
            return await self._run_in_executor(_execute_set)
        except Exception as e:
            print(f"SQLDatabase.set error: {e}")
            return False

    async def get(
        self,
        *,
        table: str,
        id: int | str,
        path: Optional[str] = None,
        columns: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]] | Any:
        """
        Retrieve record data. Supports two modes:
        1. Record mode: Returns full record or specific columns
        2. Path mode: Returns value from JSON field
        
        Args:
            table: Table name (validated against whitelist)
            id: Primary key identifier
            path: JSON path to extract from 'data' column
            columns: List of columns to return (ignored if path is set)
        
        Security:
            - Table name validated
            - Column names validated
            - Path validated and sanitized
        
        Example:
            # Mode 1: Get all columns
            giveaway = await db.get(table="giveaways", id=123)
            
            # Mode 1: Get specific columns
            data = await db.get(
                table="giveaways",
                id=123,
                columns=["prize", "ends_at", "active"]
            )
            
            # Mode 2: Get nested JSON field
            prefix = await db.get(
                table="guild_config",
                id=789,
                path="config.prefix"
            )
            # Returns: "!" (just the value)
        
        Returns:
            - If path is specified: The value at that path, or None if not found
            - If path is None: Dictionary with record, or None if not found
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        def _execute_get():
            if path:
                # Path mode: Extract from JSON
                path_components = self._validate_json_path(path)
                
                result = self.conn.execute(
                    f'SELECT data FROM "{table}" WHERE id = ?', [id]
                ).fetchone()
                
                if not result or not result[0]:
                    return None
                
                data = result[0]
                
                # Navigate to nested field
                value = data
                for key in path_components:
                    if not isinstance(value, dict) or key not in value:
                        return None
                    value = value[key]
                
                return value
            else:
                # Record mode: Get columns
                if columns:
                    for col in columns:
                        self._validate_column_name(col)
                    select_cols = ", ".join(f'"{col}"' for col in columns)
                else:
                    select_cols = "*"
                
                result = self.conn.execute(
                    f'SELECT {select_cols} FROM "{table}" WHERE id = ?',
                    [id]
                ).fetchone()
                
                if not result:
                    return None
                
                # Get column names
                col_names = [desc[0] for desc in self.conn.description]
                return dict(zip(col_names, result))
        
        try:
            return await self._run_in_executor(_execute_get)
        except Exception as e:
            print(f"SQLDatabase.get error: {e}")
            return None

    async def update(
        self,
        *,
        table: str,
        id: int | str,
        data: Optional[Dict[str, Any]] = None,
        path: Optional[str] = None,
        value: Any = None
    ) -> bool:
        """
        Update specific fields of an existing record.
        Supports both regular columns and JSON paths.
        
        Security:
            - Table name validated
            - Column names validated
            - Path validated and sanitized
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        if data is not None and (path is not None or value is not None):
            raise ValueError("Cannot use both 'data' and 'path/value' parameters")
        
        if data is None and path is None:
            raise ValueError("Must provide either 'data' or 'path' parameter")
        
        def _execute_update():
            if path:
                # JSON path mode
                path_components = self._validate_json_path(path)
                
                result = self.conn.execute(
                    f'SELECT data FROM "{table}" WHERE id = ?', [id]
                ).fetchone()
                
                if not result:
                    return False
                
                current_data = result[0] if result[0] else {}
                
                # Set nested value
                nested = current_data
                for key in path_components[:-1]:
                    if key not in nested:
                        nested[key] = {}
                    nested = nested[key]
                nested[path_components[-1]] = value
                
                self.conn.execute(
                    f'UPDATE "{table}" SET data = ? WHERE id = ?',
                    [json.dumps(current_data), id]
                )
            else:
                # Regular columns mode
                for col in data.keys():
                    self._validate_column_name(col)
                
                set_clause = ", ".join([f'"{col}" = ?' for col in data.keys()])
                values = list(data.values()) + [id]
                
                self.conn.execute(
                    f'UPDATE "{table}" SET {set_clause} WHERE id = ?',
                    values
                )
            
            return True
        
        try:
            return await self._run_in_executor(_execute_update)
        except Exception as e:
            print(f"SQLDatabase.update error: {e}")
            return False

    async def delete(
        self,
        *,
        table: str,
        id: int | str,
        path: Optional[str] = None
    ) -> bool:
        """
        Delete a record or remove a JSON field.
        
        Security:
            - Table name validated
            - Path validated and sanitized
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        def _execute_delete():
            if path:
                # Remove JSON field
                path_components = self._validate_json_path(path)
                
                result = self.conn.execute(
                    f'SELECT data FROM "{table}" WHERE id = ?', [id]
                ).fetchone()
                
                if not result or not result[0]:
                    return False
                
                current_data = result[0]
                
                # Navigate and delete
                nested = current_data
                for key in path_components[:-1]:
                    if key not in nested:
                        return False
                    nested = nested[key]
                
                if path_components[-1] in nested:
                    del nested[path_components[-1]]
                    self.conn.execute(
                        f'UPDATE "{table}" SET data = ? WHERE id = ?',
                        [json.dumps(current_data), id]
                    )
                    return True
                return False
            else:
                # Delete entire record
                self.conn.execute(f'DELETE FROM "{table}" WHERE id = ?', [id])
                return True
        
        try:
            return await self._run_in_executor(_execute_delete)
        except Exception as e:
            print(f"SQLDatabase.delete error: {e}")
            return False

    # ========= ADVANCED QUERIES =========
    
    async def find(
        self,
        *,
        table: str,
        where: Dict[str, Any],
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search with multiple filters."""
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        def _execute_find():
            for col in where.keys():
                self._validate_column_name(col)
            
            if columns:
                for col in columns:
                    self._validate_column_name(col)
                select_cols = ", ".join(f'"{col}"' for col in columns)
            else:
                select_cols = "*"
            
            where_clause = " AND ".join([f'"{col}" = ?' for col in where.keys()])
            
            query = f'SELECT {select_cols} FROM "{table}"'
            if where_clause:
                query += f" WHERE {where_clause}"
            
            if order_by:
                order_parts = order_by.strip().split()
                col_name = order_parts[0]
                self._validate_column_name(col_name)
                query += f' ORDER BY "{col_name}"'
                if len(order_parts) == 2:
                    query += f" {order_parts[1].upper()}"
            
            if limit:
                query += f" LIMIT {int(limit)}"
            
            results = self.conn.execute(query, list(where.values())).fetchall()
            
            if not results:
                return []
            
            col_names = [desc[0] for desc in self.conn.description]
            return [dict(zip(col_names, row)) for row in results]
        
        try:
            return await self._run_in_executor(_execute_find)
        except Exception as e:
            print(f"SQLDatabase.find error: {e}")
            return []

    async def find_one(
        self,
        *,
        table: str,
        where: Dict[str, Any],
        columns: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single record with filters."""
        results = await self.find(table=table, where=where, columns=columns, limit=1)
        return results[0] if results else None

    async def count(self, *, table: str, where: Optional[Dict[str, Any]] = None) -> int:
        """Count records with optional filters."""
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        table = self._validate_table_name(table)
        
        def _execute_count():
            query = f'SELECT COUNT(*) FROM "{table}"'
            values = []
            
            if where:
                for col in where.keys():
                    self._validate_column_name(col)
                where_clause = " AND ".join([f'"{col}" = ?' for col in where.keys()])
                query += f" WHERE {where_clause}"
                values = list(where.values())
            
            result = self.conn.execute(query, values).fetchone()
            return result[0] if result else 0
        
        try:
            return await self._run_in_executor(_execute_count)
        except Exception as e:
            print(f"SQLDatabase.count error: {e}")
            return 0

    # ========= BULK OPERATIONS =========
    
    async def bulk_insert(
        self,
        *,
        table: str,
        records: List[Dict[str, Any]]
    ) -> int:
        """Optimized bulk insertion."""
        if not self.conn or not records:
            return 0
        
        table = self._validate_table_name(table)
        
        def _execute_bulk():
            columns = list(records[0].keys())
            for col in columns:
                self._validate_column_name(col)
            
            placeholders = ", ".join(["?"] * len(columns))
            query = f"""
                INSERT INTO "{table}" ({', '.join(f'"{c}"' for c in columns)})
                VALUES ({placeholders})
            """
            
            self.conn.executemany(
                query,
                [tuple(record[col] for col in columns) for record in records]
            )
            return len(records)
        
        try:
            return await self._run_in_executor(_execute_bulk)
        except Exception as e:
            print(f"SQLDatabase.bulk_insert error: {e}")
            return 0

    async def bulk_delete(
        self,
        *,
        table: str,
        ids: List[int | str]
    ) -> int:
        """Bulk deletion by IDs."""
        if not self.conn or not ids:
            return 0
        
        table = self._validate_table_name(table)
        
        def _execute_bulk_delete():
            placeholders = ", ".join(["?"] * len(ids))
            query = f'DELETE FROM "{table}" WHERE id IN ({placeholders})'
            self.conn.execute(query, ids)
            return len(ids)
        
        try:
            return await self._run_in_executor(_execute_bulk_delete)
        except Exception as e:
            print(f"SQLDatabase.bulk_delete error: {e}")
            return 0

    # ========= UTILITIES =========
    
    async def execute(self, query: str, *args) -> Optional[int]:
        """
        Execute arbitrary SQL queries (DDL, maintenance, etc).
        
        WARNING: Bypasses table name validation.
        Only use with trusted, hardcoded queries.
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        def _execute():
            self.conn.execute(query, args if args else ())
            return True
        
        try:
            return await self._run_in_executor(_execute)
        except Exception as e:
            print(f"SQLDatabase.execute error: {e}")
            return None

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results.
        
        WARNING: Bypasses table name validation.
        Only use with trusted, hardcoded queries.
        """
        if not self.conn:
            raise RuntimeError("Database not initialized. Call connect() first.")
        
        def _fetch():
            results = self.conn.execute(query, args if args else ()).fetchall()
            
            if not results:
                return []
            
            col_names = [desc[0] for desc in self.conn.description]
            return [dict(zip(col_names, row)) for row in results]
        
        try:
            return await self._run_in_executor(_fetch)
        except Exception as e:
            print(f"SQLDatabase.fetch error: {e}")
            return []