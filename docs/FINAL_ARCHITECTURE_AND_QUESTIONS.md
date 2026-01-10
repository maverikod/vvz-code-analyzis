# Final Architecture and Remaining Questions

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Final Architecture Decisions

### 1. CodeDatabase Remains Unchanged

**Decision**: `CodeDatabase` class stays as is. No renaming to UniversalDriver.

**Implications**:
- No class renaming needed
- All existing code continues to work
- API remains the same

### 2. Transaction Management

**Decision**: Transactions are managed by commands that write to database.

**Architecture**:
- Commands call `CodeDatabase.begin_transaction()`, `commit_transaction()`, `rollback_transaction()`
- CodeDatabase manages high-level transactions
- SpecificDriver (SQLiteDriver) manages database-level transactions
- DBWorker only services queue, knows nothing about transactions

**Example**:
```python
# In command
db = CodeDatabase(driver_config)
db.begin_transaction()  # High-level transaction
try:
    # Form CST
    # Validate
    # Create backup
    # Write temp file
    db.update_file_data_atomic(...)  # Uses database transaction internally
    # Replace file
    db.commit_transaction()
except Exception:
    db.rollback_transaction()
    # Restore backup
```

### 3. DBWorker Role

**Decision**: DBWorker only services queue, knows nothing about transactions.

**Responsibilities**:
- Receive queries from SQLiteDriverProxy
- Execute queries via SQLiteDriver
- Return results
- Manage queue of pending queries

**Does NOT**:
- Understand transactions
- Manage transaction state
- Interpret query semantics

### 4. Schema Synchronization

**Decision**: Add method to CodeDatabase that compares database schema with current schema and updates if needed.

**Requirements**:
- Method compares current DB schema with code schema
- Adds missing tables/columns
- Removes obsolete tables/columns (optional?)
- Updates column types if needed
- Creates backup before applying schema changes
- Called automatically on server startup

### 5. File Operations

**Decision**: File operations remain at command level, not in CodeDatabase.

**Rationale**: Universal mechanism would be too heavy.

### 6. UniversalDriver

**Decision**: Remove UniversalDriver concept. Keep CodeDatabase as is.

## Architecture Chain

**Final Chain**:
```
Command → CodeDatabase → SpecificDriver → DBWorker (for SQLite) → SQLiteDriver
```

**Transaction Flow**:
```
Command
  ↓
CodeDatabase.begin_transaction()  # High-level transaction
  ↓
  - Form CST
  - Validate
  - Create backup (command level)
  - Write temp file (command level)
  ↓
  SpecificDriver.begin_transaction()  # Database transaction (internal)
    ↓
    - Execute SQL queries
    ↓
  SpecificDriver.commit_transaction()  # Database transaction commit (internal)
  ↓
  - Replace file (command level)
  - Git commit (command level)
  ↓
CodeDatabase.commit_transaction()  # High-level transaction commit
```

## Remaining Questions

### Q1: Schema Synchronization Method

**Question**: How should schema synchronization work?

**Options**:

**Option A: Compare CREATE TABLE statements**
```python
def sync_schema(self) -> Dict[str, Any]:
    """
    Compare database schema with current schema and update if needed.
    
    Returns:
        Dict with sync results:
        {
            "tables_added": [...],
            "tables_removed": [...],
            "columns_added": {...},
            "columns_removed": {...},
            "columns_modified": {...},
            "backup_path": "..."
        }
    """
    # 1. Get current schema from database (PRAGMA table_info, etc.)
    # 2. Compare with _create_schema() logic
    # 3. Generate ALTER TABLE statements
    # 4. Create backup
    # 5. Apply changes
```

**Option B: Version-based migration**
```python
def sync_schema(self) -> Dict[str, Any]:
    """
    Sync schema based on version number.
    
    Database has schema_version table with version number.
    Code has current schema version.
    Apply migrations if version differs.
    """
```

**Option C: Full schema recreation**
```python
def sync_schema(self) -> Dict[str, Any]:
    """
    Drop all tables and recreate from scratch.
    
    WARNING: Data loss!
    """
```

**Question**: Which approach should we use? Or combination?

**Recommendation**: Option A - Compare and apply incremental changes.

---

### Q2: Schema Backup Strategy

**Question**: How should database backup be created before schema changes?

**Options**:

**Option A: Full database file copy**
```python
def sync_schema(self):
    backup_path = db_path.with_suffix('.db.backup')
    shutil.copy2(db_path, backup_path)
    # Apply schema changes
```

**Option B: SQL dump**
```python
def sync_schema(self):
    backup_path = db_path.with_suffix('.db.sql')
    # Use .dump command to create SQL backup
    # Apply schema changes
```

**Option C: Use existing BackupManager**
```python
def sync_schema(self):
    from ..backup_manager import BackupManager
    backup_manager = BackupManager(...)
    backup_path = backup_manager.create_database_backup(db_path)
    # Apply schema changes
```

**Question**: Which approach?

**Recommendation**: Option A - Simple file copy is sufficient for schema backup.

---

### Q3: Schema Changes on Startup

**Question**: Where should schema sync be called on server startup?

**Options**:

**Option A: In CodeDatabase.__init__**
```python
def __init__(self, driver_config, auto_sync_schema=True):
    # ... existing init ...
    if auto_sync_schema:
        self.sync_schema()
```

**Option B: In main.py after database creation**
```python
# In main()
db = CodeDatabase(driver_config)
db.sync_schema()
```

**Option C: Separate initialization function**
```python
# In main()
db = CodeDatabase(driver_config)
db.ensure_schema_synced()  # Checks and syncs if needed
```

**Question**: Which approach?

**Recommendation**: Option C - Explicit call gives more control.

---

### Q4: Handling Schema Downgrades

**Question**: What if database schema is newer than code schema?

**Scenarios**:
1. Database has table/column that code doesn't know about
2. Database has newer version than code

**Options**:
- A) Ignore (keep extra tables/columns)
- B) Remove (DROP TABLE, ALTER TABLE DROP COLUMN)
- C) Warn but don't change
- D) Error and refuse to start

**Question**: What should happen?

**Recommendation**: Option C - Warn but don't change (safer).

---

### Q5: Schema Version Tracking

**Question**: Should we track schema version in database?

**Options**:
- A) Yes - add `schema_version` table
- B) No - compare actual schema structure
- C) Optional - track version but don't require it

**Question**: Do we need version tracking?

**Recommendation**: Option B - Compare actual structure (more robust, works even if version table is missing).

---

### Q6: Column Type Changes

**Question**: How should we handle column type changes?

**Example**: Column was `TEXT`, now should be `INTEGER`.

**Options**:
- A) ALTER TABLE (SQLite supports limited ALTER TABLE)
- B) Recreate table with new type, copy data
- C) Warn but don't change (data loss risk)

**Question**: How to handle type changes?

**Recommendation**: Option C - Warn but don't auto-change (data loss risk is too high).

---

### Q7: Index and Constraint Changes

**Question**: Should schema sync handle indexes, foreign keys, constraints?

**Options**:
- A) Yes - sync everything
- B) No - only tables and columns
- C) Partial - indexes yes, constraints no

**Question**: What should be synced?

**Recommendation**: Option A - Sync everything for complete schema management.

---

### Q8: Server Startup Integration

**Question**: Where exactly should schema sync be called in server startup?

**Current Flow**:
```
main()
  ↓
Load config
  ↓
Create CodeDatabase instances (in commands, workers, etc.)
  ↓
Start workers
```

**Options**:
- A) Before any CodeDatabase creation
- B) After first CodeDatabase creation
- C) In each CodeDatabase.__init__ (with flag)
- D) Separate initialization step in main()

**Question**: Where should it be called?

**Recommendation**: Option D - Separate step in main() before starting workers.

---

## Updated Implementation Plan Summary

Based on clarifications:

### Phase 1: Add Schema Synchronization to CodeDatabase

**Steps**:
1. Add `sync_schema()` method to CodeDatabase
2. Implement schema comparison logic
3. Implement ALTER TABLE generation
4. Add backup creation before schema changes
5. Add tests

### Phase 2: Integrate Schema Sync in Server Startup

**Steps**:
1. Add schema sync call in main.py
2. Ensure backup is created
3. Handle errors gracefully
4. Add logging

### Phase 3: Refactor DBWorkerManager

**Steps**:
1. DBWorkerManager reads config
2. Starts DB worker for SQLite
3. Registers with WorkerManager

### Phase 4: Unify Worker Startup

**Steps**:
1. Create worker startup helpers
2. Refactor worker startup functions
3. Eliminate code duplication

## Next Steps

Please answer questions Q1-Q8 so I can finalize the implementation plan with exact specifications.
