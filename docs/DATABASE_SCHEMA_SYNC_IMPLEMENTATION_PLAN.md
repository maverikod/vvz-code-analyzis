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
- Stores in `{root_dir}/old_code/` with UUID and metadata
- Backup is created before ANY schema changes

### 3. Worker Startup Flow

**Decision**: 
- **WorkerManager is passive ONLY for DB worker** (other workers start automatically)
- SQLiteDriverProxy requests DB worker startup via DBWorkerManager on connect()
- DB worker receives database path as initialization string
- DB worker creates empty database without schema if missing
- SQLiteDriver (in worker) performs schema sync on connect()

**Flow**:
```
Server Startup
  ↓
WorkerManager reads config
  ↓
WorkerManager starts other workers automatically (file_watcher, vectorization, etc.)
  ↓
WorkerManager does NOT start DB worker (passive for DB worker only)
  ↓
SQLiteDriverProxy.connect() is called
  ↓
SQLiteDriverProxy requests worker via DBWorkerManager.get_or_start_worker(db_path)
  ↓
DBWorkerManager starts DB worker process (only if not already running)
  ↓
DB worker creates empty DB if missing (no schema)
  ↓
SQLiteDriverProxy establishes connection to worker
  ↓
SQLiteDriverProxy delegates sync_schema() to worker
  ↓
SQLiteDriver (in worker) connects to DB
  ↓
SQLiteDriver.sync_schema()  # Called automatically on connect
  ↓
  - Check schema version
  - Compare structure
  - Create backup if changes needed
  - Apply changes
```

**Key Point**: WorkerManager is passive ONLY for DB worker - it starts other workers (file_watcher, vectorization, etc.) automatically on server startup, but DB worker is started lazily only when SQLiteDriverProxy requests it.

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
- `SQLiteDriver.sync_schema()` method
- Called automatically in `SQLiteDriver.connect()`
- DBWorkerManager starts worker on demand (when SQLiteDriverProxy requests connection)
- SQLiteDriverProxy delegates schema sync to worker via special command

## Implementation Plan

### Phase 1: Database Settings Table

**Files to modify**:
- `code_analysis/core/database/base.py`

**Steps**:
1. Add `db_settings` table to `_create_schema()`
2. Add `SCHEMA_VERSION` constant (e.g., `"1.0.0"`)
3. Add helper methods:
   - `_get_schema_version() -> Optional[str]`
   - `_set_schema_version(version: str) -> None`

**Code**:
```python
# In base.py
SCHEMA_VERSION = "0.0.0"  # Initial version, will be updated after first sync

def _create_schema(self) -> None:
    # ... existing tables ...
    
    # Create db_settings table
    self._execute(
        """
        CREATE TABLE IF NOT EXISTS db_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL DEFAULT (julianday('now'))
        )
        """
    )
    
    # Set initial schema version if not exists
    existing_version = self._get_schema_version()
    if existing_version is None:
        self._set_schema_version(SCHEMA_VERSION)

def _get_schema_version(self) -> Optional[str]:
    """Get current schema version from database."""
    try:
        result = self._fetchone(
            "SELECT value FROM db_settings WHERE key = ?",
            ("schema_version",)
        )
        return result["value"] if result else None
    except Exception:
        return None

def _set_schema_version(self, version: str) -> None:
    """Set schema version in database."""
    self._execute(
        """
        INSERT OR REPLACE INTO db_settings (key, value, updated_at)
        VALUES (?, ?, julianday('now'))
        """,
        ("schema_version", version)
    )
    self._commit()
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
4. Add `create_database_backup()` method to BackupManager
5. Backup database file + sidecar files (-wal, -shm, -journal)
6. Only create backup if database is not empty (has tables with data)

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
1. Create `SchemaComparator` class
2. Implement structure comparison
3. Generate ALTER/CREATE statements
4. Handle table recreation for type changes

**Code Structure**:
```python
class SchemaComparator:
    """Compares database schema with expected schema."""
    
    def __init__(self, database: CodeDatabase):
        self.database = database
        
    def compare_schemas(self) -> SchemaDiff:
        """Compare current DB schema with expected schema."""
        # Get current schema from DB
        current_tables = self._get_current_tables()
        expected_tables = self._get_expected_tables()
        
        # Compare
        diff = SchemaDiff()
        diff.missing_tables = expected_tables - current_tables
        diff.extra_tables = current_tables - expected_tables
        
        # Compare columns for each table
        for table in expected_tables & current_tables:
            current_cols = self._get_table_columns(table)
            expected_cols = self._get_expected_columns(table)
            # ... compare ...
            
        return diff
        
    def generate_migration_sql(self, diff: SchemaDiff) -> List[str]:
        """Generate SQL statements to apply schema changes."""
        statements = []
        # ... generate ALTER TABLE, CREATE TABLE, etc. ...
        return statements
```

---

### Phase 4: SQLiteDriver Schema Sync

**Files to modify**:
- `code_analysis/core/db_driver/sqlite.py`

**Steps**:
1. Add `sync_schema()` method
2. Call in `connect()` after connection established
3. Use BackupManager for backup
4. Apply schema changes
5. Update schema version

**Code**:
```python
def sync_schema(self) -> Dict[str, Any]:
    """
    Synchronize database schema with code schema.
    
    Blocks database during synchronization using file lock.
    Validates data compatibility before making changes.
    Rolls back on error.
    
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
        code_version = SCHEMA_VERSION
        
        # Compare schemas
        comparator = SchemaComparator(self)
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
            raise RuntimeError(error_msg)
        
        # Schema changes needed - create backup (only if DB is not empty)
        if self.db_path.parent.name == "data":
            project_root = self.db_path.parent.parent
            backup_dir = project_root / "backups"
        else:
            backup_dir = self.db_path.parent / "backups"
        
        backup_manager = BackupManager(backup_dir.parent)
        backup_uuid = backup_manager.create_database_backup(
            self.db_path,
            backup_dir=backup_dir,
            comment=f"Schema sync: {current_version} -> {code_version}"
        )
        result["backup_uuid"] = backup_uuid
        
        # Begin transaction for atomic schema changes
        self.begin_transaction()
        try:
            # Generate and apply migration SQL
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

def connect(self, config: Dict[str, Any]) -> None:
    """
    Connect to database and sync schema.
    
    Raises:
        RuntimeError: If schema sync fails (blocks connection)
    """
    # ... existing connection logic ...
    
    # Sync schema after connection (blocks if fails)
    try:
        sync_result = self.sync_schema()
        if sync_result["changes_applied"]:
            logger.info(f"Schema synchronized: {len(sync_result['changes_applied'])} changes applied")
    except RuntimeError as e:
        # Schema sync failed - block connection
        logger.error(f"Schema sync failed, blocking connection: {e}")
        self.disconnect()  # Close connection
        raise  # Re-raise to prevent connection
```

---

### Phase 5: DB Worker Empty Database Creation

**Files to modify**:
- `code_analysis/core/db_worker_pkg/runner.py`

**Steps**:
1. Modify worker initialization to create empty DB if missing
2. Do NOT create schema (schema is created by driver)

**Code**:
```python
def run_db_worker(db_path: str, socket_path: str, ...):
    """Run DB worker process."""
    # ... existing setup ...
    
    # Create empty database if missing (without schema)
    db_path_obj = Path(db_path)
    if not db_path_obj.exists():
        logger.info(f"Creating empty database at {db_path}")
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        # Create empty SQLite file
        import sqlite3
        conn = sqlite3.connect(str(db_path_obj))
        conn.close()
        logger.info(f"Empty database created at {db_path}")
    
    # ... rest of worker logic ...
```

---

### Phase 6: SQLiteDriverProxy Schema Sync Delegation

**Files to modify**:
- `code_analysis/core/db_driver/sqlite_proxy.py`

**Steps**:
1. Add `sync_schema` command to proxy
2. Delegate to worker via socket
3. Return sync results

**Code**:
```python
def sync_schema(self) -> Dict[str, Any]:
    """
    Synchronize database schema via worker.
    
    Returns:
        Dict with sync results from worker.
    """
    if not self._worker_initialized or not self._socket_path:
        raise RuntimeError("Worker not initialized")
    
    request = {
        "command": "sync_schema",
        "params": {},
    }
    
    response = self._send_request(request)
    if not response.get("success"):
        raise DatabaseOperationError(
            f"Schema sync failed: {response.get('error')}",
            operation="sync_schema"
        )
    
    return response.get("result", {})
```

---

### Phase 7: SQLiteDriverProxy Worker Request

**Files to modify**:
- `code_analysis/core/db_driver/sqlite_proxy.py`

**Steps**:
1. SQLiteDriverProxy requests worker startup on connect()
2. Worker is started only when needed (lazy initialization)
3. No automatic startup in main.py or WorkerManager

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
    
    # Delegate schema sync to worker
    try:
        sync_result = self.sync_schema()
        if sync_result.get("changes_applied"):
            logger.info(f"Schema synchronized: {len(sync_result['changes_applied'])} changes")
    except Exception as e:
        logger.warning(f"Schema sync failed (non-critical): {e}")
```

**Important**: 
- WorkerManager is passive - it only starts workers when explicitly requested
- No automatic DB worker startup in main.py
- Worker startup happens lazily when SQLiteDriverProxy.connect() is called

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

## Important Architecture Note

**WorkerManager is Passive ONLY for DB Worker**: 
- WorkerManager automatically starts other workers (file_watcher, vectorization, etc.) on server startup
- WorkerManager does NOT automatically start DB worker on server startup
- DB worker is started only when SQLiteDriverProxy requests it via `get_or_start_worker()`
- This ensures lazy initialization for DB worker and allows driver to control DB worker lifecycle
- For DB worker, WorkerManager acts as a factory/registry, not an auto-starter
- For other workers, WorkerManager is active and starts them automatically

## Checklist

- [ ] Phase 1: Database Settings Table
- [ ] Phase 2: BackupManager Database Backup
- [ ] Phase 3: Schema Comparison Logic
- [ ] Phase 4: SQLiteDriver Schema Sync
- [ ] Phase 5: DB Worker Empty Database Creation
- [ ] Phase 6: SQLiteDriverProxy Schema Sync Delegation
- [ ] Phase 7: SQLiteDriverProxy Worker Request (lazy initialization)
- [ ] Unit Tests
- [ ] Integration Tests
- [ ] Documentation Update
