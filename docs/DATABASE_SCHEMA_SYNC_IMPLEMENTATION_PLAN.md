# Database Schema Synchronization Implementation Plan

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Architecture Decisions

### 1. Schema Synchronization Method

**Decision**: Compare actual database structure with code schema and apply incremental changes.

**Rationale**:
- More robust than version-based (works even if version table is missing)
- Safer than full recreation (preserves data)
- Allows incremental updates without data loss
- Can detect and handle schema drift

**Implementation**:
1. Query current schema from database (PRAGMA table_info, etc.)
2. Compare with expected schema from `_create_schema()` logic
3. Generate ALTER TABLE / CREATE TABLE statements
4. Create backup before changes
5. Apply changes incrementally

### 2. Backup Strategy

**Decision**: Use BackupManager for database backups.

**Implementation**:
- Add `create_database_backup()` method to BackupManager
- Creates full file copy of database + sidecar files (-wal, -shm, -journal)
- Stores in backup directory from config (default: `{project_root}/backups`)
- Backup is created before ANY schema changes
- Rollback = restore from backup using BackupManager

### 3. Worker Startup Flow

**Decision**: 
- **WorkerManager is passive ONLY for DB worker** (other workers start automatically)
- **main.py does NOT start DB worker automatically** (removed from main.py)
- SQLiteDriverProxy requests DB worker startup via DBWorkerManager on connect()
- DB worker receives database path as initialization string
- DB worker creates empty database without schema if missing
- SQLiteDriver (in worker) receives schema from CodeDatabase and performs schema sync on connect()
- Driver always assumes database exists (worker ensures it)

**Flow**:
```
Server Startup (main.py)
  ↓
WorkerManager reads config
  ↓
WorkerManager starts other workers automatically (file_watcher, vectorization, etc.)
  ↓
WorkerManager does NOT start DB worker (passive for DB worker only)
  ↓
main.py does NOT start DB worker (removed automatic startup)
  ↓
SQLiteDriverProxy.connect() is called (lazy initialization)
  ↓
SQLiteDriverProxy requests worker via DBWorkerManager.get_or_start_worker(db_path)
  ↓
DBWorkerManager starts DB worker process (only if not already running)
  ↓
DB worker creates empty DB if missing (no schema, just empty file)
  ↓
SQLiteDriverProxy establishes connection to worker
  ↓
SQLiteDriverProxy delegates sync_schema() to worker (with schema definition)
  ↓
SQLiteDriver (in worker) connects to DB (assumes DB exists)
  ↓
SQLiteDriver.sync_schema(schema_definition)  # Called automatically on connect
  ↓
  - Check schema version
  - Compare structure using SchemaComparator
  - Validate data compatibility BEFORE changes
  - Create backup if changes needed
  - Apply changes (driver handles data migration)
```

**Key Points**: 
- WorkerManager is passive ONLY for DB worker - it starts other workers (file_watcher, vectorization, etc.) automatically on server startup, but DB worker is started lazily only when SQLiteDriverProxy requests it.
- main.py does NOT automatically start DB worker (removed)
- Worker creates empty DB if missing, driver always assumes DB exists
- Schema is passed to worker at startup, SchemaComparator runs in same process as driver

### 4. Schema Version Management

**Decision**: Store schema version in `db_settings` table.

**Implementation**:
- Create `db_settings` table with key-value structure
- Store `schema_version` key with version number
- Code has `SCHEMA_VERSION` constant
- Always update database schema to match code version
- Always create backup before schema changes (even if DB version is newer)

**Table Structure**:
```sql
CREATE TABLE IF NOT EXISTS db_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL DEFAULT (julianday('now'))
)
```

### 5. Column Type Changes

**Decision**: Use table recreation strategy for type changes.

**Implementation**:
1. Create new table with correct structure
2. Copy data from old table (with type conversion if possible)
3. Drop old table
4. Rename new table to original name
5. Recreate indexes and constraints

**Rationale**:
- SQLite has limited ALTER TABLE support
- Table recreation is safer and more reliable
- Allows proper type conversion
- Preserves data integrity

### 6. Synchronization Scope

**Decision**: Synchronize everything (tables, columns, indexes, constraints, foreign keys).

**Implementation**:
- Tables: CREATE if missing
- Columns: ADD if missing, handle type changes via recreation
- Indexes: CREATE if missing, DROP if obsolete
- Constraints: Recreate with table
- Foreign keys: Recreate with table

### 7. Driver Responsibility

**Decision**: SQLiteDriver (not proxy) performs schema synchronization.

**Implementation**:
- `SQLiteDriver.sync_schema(schema_definition)` method receives schema from CodeDatabase
- SchemaComparator runs in same process as SQLiteDriver (in worker)
- SQLiteDriver uses SchemaComparator to compare and migrate schema
- Driver handles data migration during schema changes
- Called automatically in `SQLiteDriver.connect()`
- DBWorkerManager starts worker on demand (when SQLiteDriverProxy requests connection)
- SQLiteDriverProxy delegates schema sync to worker via special command with schema definition
- If validation fails BEFORE changes - leave database unchanged, block connection and log error

## Implementation Plan

### Phase 1: Database Settings Table and Schema Definition

**Files to modify**:
- `code_analysis/core/database/base.py`

**Steps**:
1. Add `SCHEMA_VERSION` constant (e.g., `"1.0.0"`)
2. Add migration methods registry: `MIGRATION_METHODS: Dict[str, Callable[[BaseDatabaseDriver], None]]`
3. Add `_get_schema_definition() -> Dict[str, Any]` method with **structured schema definition** (not SQL parsing)
4. Add `sync_schema() -> Dict[str, Any]` method in CodeDatabase (delegates to driver)
5. **Remove `_create_schema()` call from `__init__`** - schema creation happens only via `sync_schema()`
6. Keep `_create_schema()` for reference (rename to `_create_schema_sql()` if needed)
7. Note: Version management methods (`_get_schema_version`, `_set_schema_version`) will be in Driver (Phase 4), not in CodeDatabase

**Code**:
```python
# In base.py
from typing import Dict, Any, Optional, Callable
from pathlib import Path

# Schema version constant
SCHEMA_VERSION = "1.0.0"  # Current schema version

# Migration methods registry: version -> migration function
# Each migration function receives driver instance and performs version-specific migrations
# Migration functions are called in order when upgrading from old version to new version
# Example usage:
#   MIGRATION_METHODS["1.0.0"] = lambda driver: driver._migrate_to_uuid_projects()
#   MIGRATION_METHODS["1.1.0"] = lambda driver: driver._migrate_add_datasets_table()
MIGRATION_METHODS: Dict[str, Callable[[Any], None]] = {
    # Register migration methods here
    # Format: "version": lambda driver: driver._migration_method_name()
    # Note: Methods are defined in SQLiteDriver, registry is here for centralization
}

def __init__(self, driver_config: Dict[str, Any]) -> None:
    """
    Initialize database connection.
    
    Schema is NOT created here - use sync_schema() instead.
    """
    # ... existing driver initialization code ...
    self.driver_config = driver_config  # Store for sync_schema()
    
    # DO NOT call _create_schema() here
    # Schema creation happens via sync_schema() in driver

def _get_schema_definition(self) -> Dict[str, Any]:
    """
    Get structured schema definition for synchronization.
    
    This method returns a structured dictionary representation of the schema,
    not SQL statements. This is used by SchemaComparator to compare and migrate schemas.
    
    Returns:
        Dictionary with schema definition:
        {
            "version": str,  # SCHEMA_VERSION
            "tables": {
                "table_name": {
                    "columns": [
                        {
                            "name": str,
                            "type": str,
                            "not_null": bool,
                            "default": Optional[str],
                            "primary_key": bool,
                            "autoincrement": bool (optional)
                        }
                    ],
                    "foreign_keys": [
                        {
                            "columns": List[str],
                            "references_table": str,
                            "references_columns": List[str],
                            "on_delete": str
                        }
                    ],
                    "unique_constraints": [
                        {"columns": List[str]}
                    ],
                    "check_constraints": List[str]
                }
            },
            "indexes": [
                {
                    "name": str,
                    "table": str,
                    "columns": List[str],
                    "unique": bool,
                    "where_clause": Optional[str]
                }
            ],
            "virtual_tables": [
                {
                    "name": str,
                    "type": str,  # "fts5"
                    "columns": List[str],
                    "options": Dict[str, Any]  # content, content_rowid, etc.
                }
            ],
            "migration_methods": Dict[str, Callable]  # version -> migration function
        }
    """
    # Return structured schema definition
    # See DATABASE_SCHEMA_SYNC_SOLUTIONS.md for full implementation
    return {
        "version": SCHEMA_VERSION,
        "tables": {
            # Full table definitions here (see solutions doc for complete structure)
            "db_settings": {
                "columns": [
                    {"name": "key", "type": "TEXT", "not_null": True, "primary_key": True},
                    {"name": "value", "type": "TEXT", "not_null": True},
                    {"name": "updated_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                ],
                "foreign_keys": [],
                "unique_constraints": [],
                "check_constraints": [],
            },
            # ... all other tables ...
        },
        "indexes": [
            # ... all indexes ...
        ],
        "virtual_tables": [
            {
                "name": "code_content_fts",
                "type": "fts5",
                "columns": ["entity_type", "entity_name", "content", "docstring"],
                "options": {
                    "content_rowid": "rowid",
                    "content": "code_content"
                }
            }
        ],
        "migration_methods": MIGRATION_METHODS
    }

def sync_schema(self) -> Dict[str, Any]:
    """
    Synchronize database schema via driver.
    
    Gets schema definition and backup_dir from config, delegates to driver.
    
    Returns:
        Dict with sync results from driver.
    """
    schema_definition = self._get_schema_definition()
    
    # Get backup_dir from driver config (should be set from StoragePaths)
    backup_dir = self.driver_config.get("config", {}).get("backup_dir")
    if not backup_dir:
        # Fallback: infer from db_path
        db_path = self.driver_config.get("config", {}).get("path")
        if db_path:
            db_path_obj = Path(db_path)
            if db_path_obj.parent.name == "data":
                backup_dir = str(db_path_obj.parent.parent / "backups")
            else:
                backup_dir = str(db_path_obj.parent / "backups")
        else:
            raise RuntimeError("Cannot determine backup_dir for schema sync")
    
    return self.driver.sync_schema(schema_definition, Path(backup_dir))
```

---

### Phase 2: Database Backup Support

**Files to modify**:
- `code_analysis/core/backup_manager.py` (add database backup method)
- `code_analysis/core/storage_paths.py` (add backup_dir to StoragePaths)

**Steps**:
1. Add `backup_dir` to `StoragePaths` dataclass
2. Resolve backup directory from config: `code_analysis.storage.backup_dir`
3. Default: `{project_root}/backups` (infer project root from db_path or config_dir)
4. Update `ensure_storage_dirs()` to create backup_dir
5. Add `create_database_backup()` method to BackupManager
6. Backup database file + sidecar files (-wal, -shm, -journal)
7. Only create backup if database is not empty (has tables with data)

**Code in storage_paths.py**:
```python
@dataclass(frozen=True)
class StoragePaths:
    config_dir: Path
    db_path: Path
    faiss_dir: Path
    locks_dir: Path
    queue_dir: Optional[Path]
    backup_dir: Path  # NEW: Directory for database backups

def resolve_storage_paths(...) -> StoragePaths:
    # ... existing code ...
    
    # Resolve backup directory
    backup_dir_val = storage_cfg.get("backup_dir")
    if isinstance(backup_dir_val, str) and backup_dir_val.strip():
        backup_dir = _resolve_path(config_dir, backup_dir_val)
    else:
        # Default: {project_root}/backups
        # Try to infer project root from db_path
        # If db_path is in data/ subdirectory, use parent as project root
        if db_path.parent.name == "data":
            project_root = db_path.parent.parent
        else:
            # Fallback to config_dir
            project_root = config_dir
        backup_dir = project_root / "backups"
    
    return StoragePaths(
        config_dir=config_dir,
        db_path=db_path,
        faiss_dir=faiss_dir,
        locks_dir=locks_dir,
        queue_dir=queue_dir,
        backup_dir=backup_dir,  # NEW
    )

def ensure_storage_dirs(paths: StoragePaths) -> None:
    """
    Ensure that storage directories exist.
    
    Updated to include backup_dir.
    """
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    paths.faiss_dir.mkdir(parents=True, exist_ok=True)
    paths.locks_dir.mkdir(parents=True, exist_ok=True)
    paths.backup_dir.mkdir(parents=True, exist_ok=True)  # NEW
    if paths.queue_dir is not None:
        paths.queue_dir.mkdir(parents=True, exist_ok=True)
```

**Code in backup_manager.py**:
```python
def create_database_backup(
    self,
    db_path: Path,
    backup_dir: Path,
    comment: str = "Schema synchronization backup",
) -> Optional[str]:
    """
    Create backup of database file and sidecar files.
    
    Args:
        db_path: Path to database file
        backup_dir: Directory where to store backups
        comment: Optional comment for backup
        
    Returns:
        UUID of created backup, or None if failed
    """
    try:
        db_path = Path(db_path).resolve()
        if not db_path.exists():
            _get_logger().warning(f"Database file not found: {db_path}")
            return None
        
        # Check if database is empty (no tables with data)
        # If empty, no backup needed
        if self._is_database_empty(db_path):
            _get_logger().info("Database is empty, skipping backup")
            return None
            
        backup_dir = Path(backup_dir).resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_uuid = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        
        # Backup main database file
        backup_filename = f"database-{db_path.stem}-{timestamp}-{backup_uuid}.db"
        backup_path = backup_dir / backup_filename
        shutil.copy2(db_path, backup_path)
        
        # Backup sidecar files if they exist
        sidecar_extensions = [".wal", ".shm", ".journal"]
        sidecar_files = []
        for ext in sidecar_extensions:
            sidecar_path = db_path.with_suffix(db_path.suffix + ext)
            if sidecar_path.exists():
                sidecar_backup = backup_dir / f"{backup_filename}{ext}"
                shutil.copy2(sidecar_path, sidecar_backup)
                sidecar_files.append(str(sidecar_backup.name))
        
        _get_logger().info(f"Database backup created: {backup_path} (UUID: {backup_uuid})")
        return backup_uuid
        
    except Exception as e:
        _get_logger().error(f"Failed to create database backup: {e}", exc_info=True)
        return None

def _is_database_empty(self, db_path: Path) -> bool:
    """
    Check if database is empty (no tables or no data).
    
    Args:
        db_path: Path to database file
        
    Returns:
        True if database is empty, False otherwise
    """
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if any tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = cursor.fetchall()
        
        if not tables:
            conn.close()
            return True
        
        # Check if any table has data
        for (table_name,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            if count > 0:
                conn.close()
                return False
        
        conn.close()
        return True
    except Exception as e:
        _get_logger().warning(f"Failed to check if database is empty: {e}")
        # If we can't check, assume not empty (safer)
        return False
```

---

### Phase 3: Schema Comparison Logic

**Files to create**:
- `code_analysis/core/database/schema_sync.py`

**Steps**:
1. Create `SchemaComparator` class (runs in same process as driver)
2. Implement structure comparison (tables, columns, indexes, constraints, virtual tables)
3. Generate ALTER/CREATE statements
4. Handle table recreation for type changes
5. Handle ALTER TABLE logic (moved from `_create_schema()` - adding missing columns, etc.)
6. Handle virtual tables (FTS5) recreation with data preservation
7. Implement data compatibility validation BEFORE changes

**Index Comparison Strategy**:
- Compare index name, table, columns, unique flag, partial WHERE clause
- For each expected index: check if exists with same definition
- If missing or different: DROP old, CREATE new
- Use `PRAGMA index_list(table)` and `PRAGMA index_info(index)` to get current indexes

**Constraint Comparison Strategy**:
- Primary keys: Compare via `PRAGMA table_info` (pk column)
- Foreign keys: Compare via `PRAGMA foreign_key_list(table)`
- Unique constraints: Compare via `PRAGMA index_list` (unique indexes)
- Check constraints: Extract from `sqlite_master.sql` (CREATE TABLE statement)
- If constraints differ: Recreate table (SQLite limitation)

**Virtual Tables (FTS5) Strategy**:
- Virtual tables cannot be altered - must be dropped and recreated
- Before dropping: backup data to temporary table
- After recreating: restore data from temporary table
- Handle `code_content_fts` virtual table with proper data preservation

**Code Structure**:
```python
@dataclass
class SchemaDiff:
    """Schema differences."""
    missing_tables: Set[str]
    extra_tables: Set[str]
    table_diffs: Dict[str, TableDiff]  # table_name -> TableDiff
    missing_indexes: List[IndexDef]
    extra_indexes: List[str]  # index names
    constraint_diffs: Dict[str, List[str]]  # table_name -> constraint changes
    missing_virtual_tables: Dict[str, Dict[str, Any]]  # virtual table name -> definition
    changed_virtual_tables: Dict[str, Dict[str, Any]]  # virtual table name -> new definition
    
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(
            self.missing_tables or
            self.extra_tables or
            self.table_diffs or
            self.missing_indexes or
            self.extra_indexes or
            self.constraint_diffs or
            self.missing_virtual_tables or
            self.changed_virtual_tables
        )

@dataclass
class TableDiff:
    """Table structure differences."""
    missing_columns: List[ColumnDef]
    extra_columns: List[str]  # column names
    type_changes: List[Tuple[str, str, str]]  # (col_name, old_type, new_type)
    constraint_changes: List[str]

class SchemaComparator:
    """
    Compares database schema with expected schema.
    
    Runs in same process as database driver (in worker process).
    """
    
    def __init__(self, driver: BaseDatabaseDriver, schema_definition: Dict[str, Any]):
        """
        Initialize schema comparator.
        
        Args:
            driver: Database driver instance (SQLiteDriver in worker)
            schema_definition: Schema definition from CodeDatabase.get_schema_definition()
        """
        self.driver = driver
        self.schema_definition = schema_definition
        
    def compare_schemas(self) -> SchemaDiff:
        """Compare current DB schema with expected schema."""
        # Get current schema from DB
        current_tables = self._get_current_tables()
        expected_tables = set(self.schema_definition.get("tables", {}).keys())
        
        # Get virtual tables
        current_virtual_tables = self._get_current_virtual_tables()
        expected_virtual_tables = self.schema_definition.get("virtual_tables", [])
        expected_virtual_table_names = {vt["name"] for vt in expected_virtual_tables}
        
        # Compare tables
        diff = SchemaDiff(
            missing_tables=expected_tables - current_tables,
            extra_tables=current_tables - expected_tables,
            table_diffs={},
            missing_indexes=[],
            extra_indexes=[],
            constraint_diffs={},
            missing_virtual_tables={},
            changed_virtual_tables={}
        )
        
        # Compare columns, indexes, constraints for each table
        for table_name in expected_tables & current_tables:
            table_diff = self._compare_table(table_name)
            if table_diff.has_changes():
                diff.table_diffs[table_name] = table_diff
        
        # Compare virtual tables
        for vt_def in expected_virtual_tables:
            vt_name = vt_def["name"]
            if vt_name not in current_virtual_tables:
                diff.missing_virtual_tables[vt_name] = vt_def
            else:
                # Check if virtual table definition changed
                current_vt = current_virtual_tables[vt_name]
                if self._virtual_table_changed(current_vt, vt_def):
                    diff.changed_virtual_tables[vt_name] = vt_def
        
        # Compare indexes
        diff.missing_indexes = self._compare_indexes()
        diff.extra_indexes = self._find_extra_indexes()
        
        # Compare constraints
        diff.constraint_diffs = self._compare_constraints()
        
        return diff
    
    def _get_current_virtual_tables(self) -> Dict[str, Dict[str, Any]]:
        """Get current virtual tables from database."""
        # Query sqlite_master for virtual tables
        # Return dict: table_name -> definition
        pass
    
    def _virtual_table_changed(
        self, 
        current: Dict[str, Any], 
        expected: Dict[str, Any]
    ) -> bool:
        """Check if virtual table definition changed."""
        # Compare columns, type, options
        return (
            current.get("type") != expected.get("type") or
            current.get("columns") != expected.get("columns") or
            current.get("options") != expected.get("options")
        )
    
    def _compare_table(self, table_name: str) -> TableDiff:
        """Compare table structure."""
        current_cols = self._get_table_columns(table_name)
        expected_cols = self.schema_definition["tables"][table_name]["columns"]
        # ... compare columns, detect type changes ...
        
    def _compare_indexes(self) -> List[IndexDef]:
        """Compare indexes using PRAGMA commands."""
        # Use PRAGMA index_list(table) to get current indexes
        # Compare with expected indexes from schema_definition
        # Return list of missing indexes
        
    def _compare_constraints(self) -> Dict[str, List[str]]:
        """Compare constraints (PK, FK, unique, check)."""
        # Use PRAGMA table_info, foreign_key_list, index_list
        # Compare with expected constraints
        # Return dict of constraint changes per table
        
    def validate_data_compatibility(self, diff: SchemaDiff) -> Dict[str, Any]:
        """
        Validate data compatibility BEFORE making changes.
        
        Returns:
            {
                "compatible": bool,
                "error": Optional[str],
                "warnings": List[str]
            }
        """
        # Check if type changes are compatible
        # Check if NOT NULL constraints can be added to columns with NULLs
        # Check if foreign keys can be added
        # Check if virtual table recreation is safe (data can be preserved)
        # If incompatible: return {"compatible": False, "error": "..."}
        # If compatible: return {"compatible": True}
    
    def _recreate_virtual_table(
        self, 
        table_name: str, 
        virtual_table_def: Dict[str, Any]
    ) -> List[str]:
        """
        Generate SQL to recreate virtual table (FTS5) with data preservation.
        
        Args:
            table_name: Name of virtual table
            virtual_table_def: Virtual table definition from schema
            
        Returns:
            List of SQL statements:
            1. CREATE TEMP TABLE to backup data
            2. DROP TABLE virtual table
            3. CREATE VIRTUAL TABLE with new schema
            4. INSERT data from temp table
            5. DROP TEMP TABLE
        """
        statements = []
        temp_table = f"temp_{table_name}"
        
        # Backup data
        statements.append(f"CREATE TEMP TABLE {temp_table} AS SELECT * FROM {table_name}")
        
        # Drop virtual table
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        
        # Create new virtual table
        columns = ", ".join(virtual_table_def["columns"])
        options = virtual_table_def.get("options", {})
        options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
        if options_str:
            create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns}, {options_str})"
        else:
            create_sql = f"CREATE VIRTUAL TABLE {table_name} USING {virtual_table_def['type']}({columns})"
        statements.append(create_sql)
        
        # Restore data
        statements.append(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
        
        # Drop temp table
        statements.append(f"DROP TABLE {temp_table}")
        
        return statements
        
    def generate_migration_sql(self, diff: SchemaDiff) -> List[str]:
        """
        Generate SQL statements to apply schema changes.
        
        Handles:
        - CREATE TABLE for missing tables
        - ALTER TABLE ADD COLUMN for missing columns (moved from _create_schema())
        - Table recreation for type changes (with data migration)
        - CREATE INDEX for missing indexes
        - DROP INDEX for extra indexes
        - Virtual table (FTS5) recreation with data preservation
        """
        statements = []
        
        # Create missing tables
        for table_name in diff.missing_tables:
            statements.append(self._generate_create_table_sql(table_name))
        
        # Handle table changes (columns, types, constraints)
        for table_name, table_diff in diff.table_diffs.items():
            if table_diff.type_changes:
                # Recreate table with data migration
                statements.extend(self._generate_recreate_table_sql(table_name, table_diff))
            else:
                # Add missing columns (handles ALTER TABLE logic from _create_schema())
                for col_def in table_diff.missing_columns:
                    col_sql = f"{col_def.name} {col_def.type}"
                    if col_def.not_null:
                        col_sql += " NOT NULL"
                    if col_def.default:
                        col_sql += f" DEFAULT {col_def.default}"
                    statements.append(f"ALTER TABLE {table_name} ADD COLUMN {col_sql}")
        
        # Handle virtual tables (FTS5)
        for virtual_table_name, virtual_table_def in diff.missing_virtual_tables.items():
            statements.extend(self._recreate_virtual_table(virtual_table_name, virtual_table_def))
        
        # Recreate virtual tables if schema changed
        for virtual_table_name, virtual_table_def in diff.changed_virtual_tables.items():
            statements.extend(self._recreate_virtual_table(virtual_table_name, virtual_table_def))
        
        # Create missing indexes
        for index_def in diff.missing_indexes:
            statements.append(self._generate_create_index_sql(index_def))
        
        # Drop extra indexes
        for index_name in diff.extra_indexes:
            statements.append(f"DROP INDEX IF EXISTS {index_name}")
        
        return statements
```

---

### Phase 4: SQLiteDriver Schema Sync

**Files to modify**:
- `code_analysis/core/db_driver/sqlite.py`

**Steps**:
1. Add `sync_schema(schema_definition: Dict[str, Any])` method
2. Receive schema definition from CodeDatabase (passed via worker)
3. Use SchemaComparator (runs in same process as driver)
4. Validate data compatibility BEFORE changes (if fails - leave DB unchanged, block connection)
5. Use BackupManager for backup (get backup_dir from config/storage_paths)
6. Apply schema changes (driver handles data migration)
7. Update schema version

**Code**:
```python
def sync_schema(
    self, 
    schema_definition: Dict[str, Any], 
    backup_dir: Path
) -> Dict[str, Any]:
    """
    Synchronize database schema with code schema.
    
    Blocks database during synchronization using file lock.
    Validates data compatibility BEFORE making changes.
    If validation fails - leaves database unchanged, blocks connection, logs error.
    Driver handles data migration during schema changes.
    Rolls back on error.
    
    Args:
        schema_definition: Schema definition from CodeDatabase.get_schema_definition()
        backup_dir: Directory for database backups (from StoragePaths)
    
    Raises:
        RuntimeError: If schema sync fails (blocks connection)
        
    Returns:
        Dict with sync results:
        {
            "success": bool,
            "backup_uuid": Optional[str],
            "changes_applied": List[str],
            "error": Optional[str]
        }
    """
    import fcntl
    from pathlib import Path
    from ..database.schema_sync import SchemaComparator
    from ..backup_manager import BackupManager
    from ..database.base import SCHEMA_VERSION
    
    result = {
        "success": False,
        "backup_uuid": None,
        "changes_applied": [],
        "error": None,
    }
    
    # Lock file for schema synchronization
    lock_file = Path(str(self.db_path) + ".schema_sync.lock")
    lock_fd = None
    
    try:
        # Acquire lock before synchronization
        lock_fd = open(lock_file, "w")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        logger.info("Schema sync lock acquired")
        
        # Get current schema version (defaults to "0.0.0" if not set)
        current_version = self._get_schema_version() or "0.0.0"
        code_version = schema_definition.get("version", SCHEMA_VERSION)
        
        # Compare schemas using SchemaComparator (runs in same process)
        comparator = SchemaComparator(self, schema_definition)
        diff = comparator.compare_schemas()
        
        if not diff.has_changes():
            # Schema is up to date
            if current_version != code_version:
                # Update version only
                self._set_schema_version(code_version)
                self.commit()
            result["success"] = True
            return result
        
        # Validate data compatibility BEFORE making changes
        logger.info("Validating data compatibility before schema changes...")
        validation_result = comparator.validate_data_compatibility(diff)
        if not validation_result["compatible"]:
            error_msg = f"Data compatibility check failed: {validation_result['error']}"
            logger.error(error_msg)
            # Leave database unchanged, block connection
            raise RuntimeError(error_msg)
        
        # Schema changes needed - create backup (only if DB is not empty)
        # CRITICAL: If backup fails, do NOT proceed with migration
        # Get project root for BackupManager
        if self.db_path.parent.name == "data":
            project_root = self.db_path.parent.parent
        else:
            project_root = self.db_path.parent
        
        backup_manager = BackupManager(project_root)
        backup_uuid = backup_manager.create_database_backup(
            self.db_path,
            backup_dir=backup_dir,
            comment=f"Schema sync: {current_version} -> {code_version}"
        )
        
        # If backup failed (returned None) and DB is not empty, block migration
        if backup_uuid is None:
            # Check if DB is actually empty (backup manager skips empty DBs)
            # If DB has data but backup failed, this is an error
            try:
                import sqlite3
                test_conn = sqlite3.connect(str(self.db_path))
                cursor = test_conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                table_count = cursor.fetchone()[0]
                test_conn.close()
                
                if table_count > 0:
                    # DB has tables but backup failed - block migration
                    error_msg = "Database backup failed but database contains data. Migration blocked for safety."
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
            except Exception as e:
                logger.warning(f"Could not verify if database is empty: {e}")
                # If we can't verify, assume it's not empty and block migration
                error_msg = "Database backup failed and could not verify database state. Migration blocked for safety."
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e
        
        result["backup_uuid"] = backup_uuid
        
        # Run version-specific migration methods if needed
        # Migration methods are called in order from current_version to code_version
        from ..database.base import MIGRATION_METHODS
        
        def _version_compare(v1: str, v2: str) -> int:
            """
            Compare version strings (e.g., "1.0.0" vs "1.1.0"). 
            
            Returns: 
                -1 if v1 < v2
                 0 if v1 == v2
                 1 if v1 > v2
            """
            v1_parts = [int(x) for x in v1.split(".")]
            v2_parts = [int(x) for x in v2.split(".")]
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            for a, b in zip(v1_parts, v2_parts):
                if a < b:
                    return -1
                elif a > b:
                    return 1
            return 0
        
        # Get migration versions between current and target version
        migration_versions = sorted([
            v for v in MIGRATION_METHODS.keys() 
            if _version_compare(v, current_version) > 0 and _version_compare(v, code_version) <= 0
        ], key=lambda v: tuple(int(x) for x in v.split(".")))
        
        for migration_version in migration_versions:
            migration_func = MIGRATION_METHODS[migration_version]
            logger.info(f"Running migration for version {migration_version}")
            migration_func(self)
        
        # Begin transaction for atomic schema changes
        self.begin_transaction()
        try:
            # Generate and apply migration SQL (driver handles data migration)
            migration_sql = comparator.generate_migration_sql(diff)
            for sql in migration_sql:
                self.execute(sql)
                result["changes_applied"].append(sql)
            
            # Update schema version
            self._set_schema_version(code_version)
            self.commit()
            
            result["success"] = True
            logger.info(f"Schema synchronized: {len(result['changes_applied'])} changes applied")
            return result
            
        except Exception as e:
            # Rollback on error
            self.rollback()
            raise RuntimeError(f"Schema sync failed during migration: {e}") from e
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Schema sync failed: {e}", exc_info=True)
        # Re-raise to block connection
        raise RuntimeError(f"Schema synchronization failed: {e}") from e
        
    finally:
        # Release lock
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
                logger.info("Schema sync lock released")
            except Exception:
                pass

def _get_schema_version(self) -> Optional[str]:
    """Get current schema version from database."""
    try:
        result = self.fetchone(
            "SELECT value FROM db_settings WHERE key = ?",
            ("schema_version",)
        )
        return result["value"] if result else None
    except Exception:
        return None

def _set_schema_version(self, version: str) -> None:
    """Set schema version in database."""
    self.execute(
        """
        INSERT OR REPLACE INTO db_settings (key, value, updated_at)
        VALUES (?, ?, julianday('now'))
        """,
        ("schema_version", version)
    )
    self.commit()

def connect(self, config: Dict[str, Any]) -> None:
    """
    Connect to database.
    
    Note: Schema sync is called separately via sync_schema() command from worker.
    Driver always assumes database exists (worker ensures it).
    """
    # ... existing connection logic ...
    # DO NOT call sync_schema here - it's called via command from worker
```

---

### Phase 5: DB Worker Empty Database Creation

**Files to modify**:
- `code_analysis/core/db_worker_pkg/runner.py`

**Steps**:
1. Modify worker initialization to create empty DB if missing
2. Do NOT create schema (schema is created by driver via sync_schema)
3. Driver always assumes database exists (worker ensures it)

**Code**:
```python
def run_db_worker(db_path: str, socket_path: str, ...):
    """Run DB worker process."""
    # ... existing setup ...
    
    # Create empty database if missing (without schema)
    # Driver always assumes database exists - worker ensures it
    # Empty DB will be populated by sync_schema() in driver
    db_path_obj = Path(db_path)
    if not db_path_obj.exists():
        logger.info(f"Creating empty database at {db_path}")
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        # Create empty SQLite file (no schema, just empty file)
        import sqlite3
        conn = sqlite3.connect(str(db_path_obj))
        conn.close()
        logger.info(f"Empty database created at {db_path}")
        # Note: No backup needed for empty database - sync_schema() will create schema
    
    # ... rest of worker logic ...
```

---

### Phase 6: SQLiteDriverProxy Schema Sync Delegation and Worker Command Handler

**Files to modify**:
- `code_analysis/core/db_driver/sqlite_proxy.py`
- `code_analysis/core/db_worker_pkg/runner.py`

**Steps**:
1. Add `sync_schema()` method to SQLiteDriverProxy
2. Get schema definition from CodeDatabase
3. Delegate to worker via socket with schema definition
4. Add `sync_schema` command handler in worker's `_handle_client_connection`
5. Worker calls SQLiteDriver.sync_schema() with schema definition

**Code in sqlite_proxy.py**:
```python
def sync_schema(self, database: CodeDatabase) -> Dict[str, Any]:
    """
    Synchronize database schema via worker.
    
    Args:
        database: CodeDatabase instance to get schema definition from
    
    Returns:
        Dict with sync results from worker.
    """
    if not self._worker_initialized or not self._socket_path:
        raise RuntimeError("Worker not initialized")
    
    # Get schema definition from CodeDatabase
    schema_definition = database.get_schema_definition()
    
    # Get backup_dir from storage paths
    # backup_dir should be passed via config or retrieved from StoragePaths
    # For now, infer from db_path (will be improved in Phase 2)
    if self.db_path.parent.name == "data":
        project_root = self.db_path.parent.parent
        backup_dir = project_root / "backups"
    else:
        backup_dir = self.db_path.parent / "backups"
    
    # Ensure backup_dir is passed as string for JSON serialization
    backup_dir_str = str(backup_dir)
    
    request = {
        "command": "sync_schema",
        "params": {
            "schema_definition": schema_definition,
            "backup_dir": backup_dir_str,
        },
    }
    
    response = self._send_request(request)
    if not response.get("success"):
        raise DatabaseOperationError(
            f"Schema sync failed: {response.get('error')}",
            operation="sync_schema"
        )
    
    return response.get("result", {})
```

**Code in runner.py (_handle_client_connection)**:
```python
def _handle_client_connection(
    client_sock: socket.socket,
    db_path: str,
    jobs: Dict[str, Dict[str, Any]],
    jobs_lock: threading.Lock,
    job_timeout: float,
) -> None:
    """Handle client connection and process commands."""
    try:
        request = _receive_request(client_sock, timeout=5.0)
        if not request:
            return

        command = request.get("command")

        if command == "sync_schema":
            # Handle schema synchronization
            params = request.get("params", {})
            schema_definition = params.get("schema_definition")
            backup_dir_str = params.get("backup_dir")
            
            if not schema_definition:
                _send_response(
                    client_sock,
                    {
                        "success": False,
                        "error": "Missing schema_definition",
                    },
                )
                return
            
            # Create SQLiteDriver instance in worker process
            from ..db_driver.sqlite import SQLiteDriver
            from pathlib import Path
            
            driver = SQLiteDriver()
            driver.connect({"path": db_path})
            
            try:
                backup_dir = Path(backup_dir_str) if backup_dir_str else None
                if not backup_dir:
                    # Infer from db_path
                    db_path_obj = Path(db_path)
                    if db_path_obj.parent.name == "data":
                        project_root = db_path_obj.parent.parent
                        backup_dir = project_root / "backups"
                    else:
                        backup_dir = db_path_obj.parent / "backups"
                
                # Call sync_schema in driver (runs in same process)
                sync_result = driver.sync_schema(schema_definition, backup_dir)
                
                _send_response(
                    client_sock,
                    {
                        "success": True,
                        "result": sync_result,
                    },
                )
            except Exception as e:
                logger.error(f"Schema sync failed: {e}", exc_info=True)
                _send_response(
                    client_sock,
                    {
                        "success": False,
                        "error": str(e),
                    },
                )
            finally:
                driver.disconnect()
        
        elif command == "submit":
            # ... existing submit logic ...
```

---

### Phase 7: SQLiteDriverProxy Worker Request and main.py Update

**Files to modify**:
- `code_analysis/core/db_driver/sqlite_proxy.py`
- `code_analysis/main.py`

**Steps**:
1. SQLiteDriverProxy requests worker startup on connect()
2. Worker is started only when needed (lazy initialization)
3. **Remove automatic DB worker startup from main.py**
4. CodeDatabase calls sync_schema() after connection

**Code in sqlite_proxy.py**:
```python
def connect(self, config: Dict[str, Any]) -> None:
    """
    Establish connection to worker process.
    
    Requests worker startup via DBWorkerManager if not already running.
    """
    logger.info("[SQLITE_PROXY] connect() called")
    if "path" not in config:
        raise ValueError("SQLite proxy driver requires 'path' in config")

    self.db_path = Path(config["path"]).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # Get worker config
    worker_config = config.get("worker_config", {})
    self.command_timeout = worker_config.get("command_timeout", 30.0)
    self.poll_interval = worker_config.get("poll_interval", 0.1)
    self.worker_log_path = worker_config.get("worker_log_path")

    # Request worker startup via DBWorkerManager (lazy initialization)
    # WorkerManager does NOT start worker automatically - only on request
    worker_manager = get_db_worker_manager()
    worker_info = worker_manager.get_or_start_worker(
        db_path=str(self.db_path),
        worker_log_path=self.worker_log_path
    )
    
    self._socket_path = worker_info["socket_path"]
    self._worker_initialized = True
    
    logger.info(f"[SQLITE_PROXY] Connected to worker at {self._socket_path}")
    
    # Note: Schema sync is called separately by CodeDatabase, not here
```

**Code in main.py** (REMOVE automatic DB worker startup):
```python
def main() -> None:
    # ... existing code ...
    
    # REMOVE this section (lines ~1092-1113):
    # try:
    #     # Start DB worker first
    #     from code_analysis.core.db_worker_manager import get_db_worker_manager
    #     ...
    #     db_worker_manager = get_db_worker_manager()
    #     worker_info = db_worker_manager.get_or_start_worker(...)
    #     ...
    
    # DB worker is now started lazily by SQLiteDriverProxy.connect()
    # No automatic startup needed
```

**Code in CodeDatabase.__init__** (add schema sync call):
```python
def __init__(self, driver_config: Dict[str, Any]) -> None:
    """Initialize database connection and sync schema."""
    # ... existing driver initialization ...
    
    # Sync schema after connection (replaces _create_schema() call)
    try:
        sync_result = self.sync_schema()
        if sync_result.get("changes_applied"):
            logger.info(f"Schema synchronized: {len(sync_result['changes_applied'])} changes applied")
    except RuntimeError as e:
        # Schema sync failed - connection is blocked
        logger.error(f"Schema sync failed, connection blocked: {e}")
        raise  # Re-raise to prevent database usage

def sync_schema(self) -> Dict[str, Any]:
    """Synchronize database schema via driver."""
    schema_definition = self.get_schema_definition()
    return self.driver.sync_schema(self, schema_definition)
```

**Important**: 
- WorkerManager is passive - it only starts workers when explicitly requested
- **main.py does NOT automatically start DB worker (removed)**
- Worker startup happens lazily when SQLiteDriverProxy.connect() is called
- CodeDatabase calls sync_schema() after connection (replaces _create_schema())

---

## Testing Plan

### Unit Tests

1. **Schema Version Management**
   - Test `_get_schema_version()` and `_set_schema_version()`
   - Test version update on schema sync

2. **Schema Comparison**
   - Test missing tables detection
   - Test missing columns detection
   - Test type changes detection
   - Test index comparison

3. **Backup Creation**
   - Test database backup creation
   - Test sidecar files backup
   - Test backup index entry

4. **Schema Sync**
   - Test sync with empty database
   - Test sync with outdated schema
   - Test sync with newer schema (should update to code version)
   - Test sync with identical schema (no changes)

### Integration Tests

1. **Worker Startup**
   - Test worker creates empty DB if missing
   - Test worker does not create schema

2. **Driver Integration**
   - Test SQLiteDriver syncs schema on connect
   - Test SQLiteDriverProxy delegates sync to worker
   - Test schema changes are applied correctly

3. **Server Startup**
   - Test schema sync on server startup
   - Test backup is created before changes
   - Test version is updated after sync

## Migration Notes

### Existing Databases

1. On first startup after update:
   - Schema sync will detect missing `db_settings` table
   - Will create table and set version
   - Will compare and update schema if needed
   - Will create backup before changes

2. Schema version migration:
   - Old databases without version will be treated as version "0.0.0"
   - Schema sync will update to current version
   - Backup will be created before any changes

3. Rollback Strategy:
   - If schema sync fails, database is left unchanged
   - Backup is created before changes (if DB is not empty)
   - Rollback = restore from backup using BackupManager.restore_file()
   - Backup UUID is returned in sync_schema() result for manual restore if needed

### Data Migration

- Driver (SQLiteDriver) handles data migration during schema changes
- Type changes: table recreation with data conversion
- Column additions: ALTER TABLE ADD COLUMN (SQLite supports this)
- Data validation happens BEFORE changes - if incompatible, changes are not applied

## Important Architecture Notes

### WorkerManager is Passive ONLY for DB Worker
- WorkerManager automatically starts other workers (file_watcher, vectorization, etc.) on server startup
- WorkerManager does NOT automatically start DB worker on server startup
- **main.py does NOT automatically start DB worker (removed)**
- DB worker is started only when SQLiteDriverProxy requests it via `get_or_start_worker()`
- This ensures lazy initialization for DB worker and allows driver to control DB worker lifecycle
- For DB worker, WorkerManager acts as a factory/registry, not an auto-starter
- For other workers, WorkerManager is active and starts them automatically

### Schema Synchronization Flow
1. CodeDatabase.__init__() creates driver (SQLiteDriverProxy)
2. SQLiteDriverProxy.connect() requests worker startup (lazy)
3. Worker creates empty DB if missing (no schema)
4. CodeDatabase.sync_schema() gets schema definition
5. SQLiteDriverProxy.sync_schema() sends command to worker with schema
6. Worker calls SQLiteDriver.sync_schema() in same process
7. SQLiteDriver uses SchemaComparator (same process) to compare and migrate
8. If validation fails BEFORE changes - database unchanged, connection blocked
9. If changes needed - backup created, changes applied, version updated

### Error Handling
- **Validation failure**: Database unchanged, connection blocked, error logged
- **Migration failure**: Transaction rolled back, connection blocked, error logged
- **Backup failure**: 
  - If DB is empty: Migration proceeds (no backup needed)
  - If DB has data but backup failed: Migration blocked, connection blocked, error logged
  - Database unchanged, connection blocked until backup can be created
- All errors block connection (raise RuntimeError) - database cannot be used until fixed

### Virtual Tables (FTS5) Handling
- Virtual tables cannot be altered - must be dropped and recreated
- Before dropping: data is backed up to temporary table
- After recreating: data is restored from temporary table
- This ensures full-text search indexes are preserved during schema changes
- Example: `code_content_fts` virtual table is recreated with data preservation
- SchemaComparator detects missing or changed virtual tables and generates recreation SQL

### Migration Methods Registry
- `MIGRATION_METHODS` dictionary maps version strings to migration functions
- Migration functions receive driver instance and perform version-specific migrations
- Migrations are called in order when upgrading from old version to new version
- Example: `MIGRATION_METHODS["1.0.0"] = lambda driver: driver._migrate_to_uuid_projects()`
- Migration methods run BEFORE schema comparison changes are applied

## Checklist

- [x] Phase 1: Database Settings Table and Schema Definition
  - [x] Added SCHEMA_VERSION constant
  - [x] Added MIGRATION_METHODS registry
  - [x] Added _get_schema_definition() with all tables and indexes
  - [x] Added sync_schema() method in CodeDatabase
  - [x] Removed _create_schema() call from __init__
- [x] Phase 2: BackupManager Database Backup
  - [x] Added backup_dir to StoragePaths
  - [x] Added create_database_backup() to BackupManager
  - [x] Added _is_database_empty() check
- [x] Phase 3: Schema Comparison Logic
  - [x] Created SchemaComparator class
  - [x] Implemented compare_schemas() with all table/index comparisons
  - [x] Implemented validate_data_compatibility()
  - [x] Implemented generate_migration_sql()
  - [x] **FIXED**: Implemented _compare_constraints() method (was returning empty dict)
  - [x] **FIXED**: Fixed _generate_recreate_table_sql() signature to accept current_columns parameter
- [x] Phase 4: SQLiteDriver Schema Sync
  - [x] Added sync_schema() method
  - [x] Added _get_schema_version() and _set_schema_version()
  - [x] Implemented backup creation and validation
  - [x] Implemented migration execution with rollback
- [x] Phase 5: DB Worker Empty Database Creation
  - [x] Worker creates empty DB if missing
  - [x] No schema creation in worker
- [x] Phase 6: SQLiteDriverProxy Schema Sync Delegation
  - [x] Added sync_schema() method to proxy
  - [x] Added sync_schema command handler in worker
- [x] Phase 7: SQLiteDriverProxy Worker Request (lazy initialization)
  - [x] Removed automatic DB worker startup from main.py
  - [x] Proxy requests worker via get_or_start_worker() on connect()
  - [x] Added backup_dir to create_driver_config_for_worker()
- [x] **Code Quality Fixes** (2026-01-10)
  - [x] Fixed _generate_recreate_table_sql() method signature - added current_columns parameter
  - [x] Implemented full _compare_constraints() method with PK, FK, and unique constraint comparison
  - [x] Verified all tables are included in _get_schema_definition()
  - [x] Verified sync_schema() in sqlite.py is fully implemented
- [ ] Unit Tests
- [ ] Integration Tests
- [ ] Documentation Update
