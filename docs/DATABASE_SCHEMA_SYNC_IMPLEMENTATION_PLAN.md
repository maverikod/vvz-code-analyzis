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
- WorkerManager reads config
- If SQLite driver type, WorkerManager starts DB worker
- DB worker receives database path as initialization string
- DB worker creates empty database without schema if missing
- SQLiteDriver requests worker startup via DBWorkerManager
- SQLiteDriver performs schema sync on connect()

**Flow**:
```
Server Startup
  ↓
WorkerManager reads config
  ↓
If driver_type == "sqlite_proxy":
  ↓
  WorkerManager calls DBWorkerManager.get_or_start_worker(db_path)
  ↓
  DBWorkerManager starts DB worker process
  ↓
  DB worker creates empty DB if missing (no schema)
  ↓
SQLiteDriverProxy.connect()
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
SCHEMA_VERSION = "1.0.0"

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

### Phase 2: BackupManager Database Backup

**Files to modify**:
- `code_analysis/core/backup_manager.py`

**Steps**:
1. Add `create_database_backup()` method
2. Backup database file + sidecar files (-wal, -shm, -journal)
3. Store in `old_code/` directory with UUID
4. Add entry to index with special marker

**Code**:
```python
def create_database_backup(
    self,
    db_path: Path,
    comment: str = "Schema synchronization backup",
) -> Optional[str]:
    """
    Create backup of database file and sidecar files.
    
    Args:
        db_path: Path to database file
        comment: Optional comment for backup
        
    Returns:
        UUID of created backup, or None if failed
    """
    try:
        db_path = Path(db_path).resolve()
        if not db_path.exists():
            _get_logger().warning(f"Database file not found: {db_path}")
            return None
            
        backup_uuid = str(uuid.uuid4())
        
        # Backup main database file
        backup_filename = f"database-{db_path.name}-{backup_uuid}.db"
        backup_path = self.backup_dir / backup_filename
        shutil.copy2(db_path, backup_path)
        
        # Backup sidecar files if they exist
        sidecar_extensions = [".wal", ".shm", ".journal"]
        sidecar_files = []
        for ext in sidecar_extensions:
            sidecar_path = db_path.with_suffix(db_path.suffix + ext)
            if sidecar_path.exists():
                sidecar_backup = self.backup_dir / f"{backup_filename}{ext}"
                shutil.copy2(sidecar_path, sidecar_backup)
                sidecar_files.append(str(sidecar_backup.name))
        
        # Update index
        index = self._load_index()
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        index[backup_uuid] = {
            "file_path": f"[DATABASE]{db_path.name}",
            "timestamp": timestamp,
            "command": "schema_sync",
            "related_files": ",".join(sidecar_files),
            "comment": comment,
        }
        self._save_index(index)
        
        _get_logger().info(f"Database backup created: {backup_uuid}")
        return backup_uuid
        
    except Exception as e:
        _get_logger().error(f"Failed to create database backup: {e}", exc_info=True)
        return None
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
    
    Returns:
        Dict with sync results:
        {
            "success": bool,
            "backup_uuid": Optional[str],
            "changes_applied": List[str],
            "error": Optional[str]
        }
    """
    from ..database.schema_sync import SchemaComparator
    from ..backup_manager import BackupManager
    from ..database.base import SCHEMA_VERSION
    
    result = {
        "success": False,
        "backup_uuid": None,
        "changes_applied": [],
        "error": None,
    }
    
    try:
        # Get current schema version
        current_version = self._get_schema_version()
        code_version = SCHEMA_VERSION
        
        # Compare schemas
        comparator = SchemaComparator(self)
        diff = comparator.compare_schemas()
        
        if not diff.has_changes():
            # Schema is up to date
            if current_version != code_version:
                # Update version only
                self._set_schema_version(code_version)
            result["success"] = True
            return result
        
        # Schema changes needed - create backup
        backup_manager = BackupManager(self.db_path.parent.parent)  # root_dir
        backup_uuid = backup_manager.create_database_backup(
            self.db_path,
            comment=f"Schema sync: {current_version} -> {code_version}"
        )
        result["backup_uuid"] = backup_uuid
        
        # Generate and apply migration SQL
        migration_sql = comparator.generate_migration_sql(diff)
        for sql in migration_sql:
            self.execute(sql)
            result["changes_applied"].append(sql)
        
        # Update schema version
        self._set_schema_version(code_version)
        self.commit()
        
        result["success"] = True
        return result
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Schema sync failed: {e}", exc_info=True)
        return result

def connect(self, config: Dict[str, Any]) -> None:
    """Connect to database and sync schema."""
    # ... existing connection logic ...
    
    # Sync schema after connection
    sync_result = self.sync_schema()
    if not sync_result["success"]:
        logger.warning(f"Schema sync had issues: {sync_result.get('error')}")
    else:
        if sync_result["changes_applied"]:
            logger.info(f"Schema synchronized: {len(sync_result['changes_applied'])} changes applied")
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

### Phase 7: Worker Manager Integration

**Files to modify**:
- `code_analysis/core/db_worker_manager.py`
- `code_analysis/main.py`

**Steps**:
1. WorkerManager reads config
2. If SQLite, starts DB worker
3. SQLiteDriverProxy requests worker via DBWorkerManager

**Code in main.py**:
```python
def startup_database_worker(config_data: Dict[str, Any]) -> None:
    """Start database worker if SQLite driver is configured."""
    from ..core.storage_paths import resolve_storage_paths
    from ..core.db_worker_manager import get_db_worker_manager
    
    storage = resolve_storage_paths(config_data=config_data, ...)
    db_path = storage.db_path
    
    # Check if SQLite driver is used
    driver_type = config_data.get("database", {}).get("driver_type", "sqlite_proxy")
    if driver_type == "sqlite_proxy":
        # Start DB worker
        worker_manager = get_db_worker_manager()
        worker_info = worker_manager.get_or_start_worker(
            db_path=str(db_path),
            worker_log_path=str(storage.log_path / "db_worker.log")
        )
        logger.info(f"Database worker started: {worker_info['socket_path']}")
```

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

## Checklist

- [ ] Phase 1: Database Settings Table
- [ ] Phase 2: BackupManager Database Backup
- [ ] Phase 3: Schema Comparison Logic
- [ ] Phase 4: SQLiteDriver Schema Sync
- [ ] Phase 5: DB Worker Empty Database Creation
- [ ] Phase 6: SQLiteDriverProxy Schema Sync Delegation
- [ ] Phase 7: Worker Manager Integration
- [ ] Unit Tests
- [ ] Integration Tests
- [ ] Documentation Update
