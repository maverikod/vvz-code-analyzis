# Clarified Architecture

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Clarified Points

### 1. CodeDatabase = UniversalDriver

**Decision**: `CodeDatabase` will be renamed to `UniversalDriver`. This is primarily a renaming operation.

**Implications**:
- All business logic methods remain in the class (just renamed)
- API stays the same for commands
- Internal structure remains the same
- Only class name and references change

### 2. Schema Creation

**Decision**: Schema is created at the `CodeDatabase` (UniversalDriver) level.

**Current Implementation**: `CodeDatabase._create_schema()` creates all tables.

**After Refactoring**: `UniversalDriver._create_schema()` will create schema.

### 3. Transaction Architecture

**Two-Level Transaction System**:

#### Level 1: Database Transactions (SpecificDriver)
- **Location**: SpecificDriver (SQLiteDriver, MySQLDriver, etc.)
- **Scope**: Database-level operations only
- **Features**: 
  - BEGIN TRANSACTION
  - COMMIT
  - ROLLBACK
  - Database-level atomicity

#### Level 2: High-Level Transactions (UniversalDriver/CodeDatabase)
- **Location**: UniversalDriver (CodeDatabase)
- **Scope**: Multi-step business operations
- **Example**: `compose_cst_module` transaction includes:
  1. Form CST module
  2. Validate file (compilation, linter, type checker, docstrings)
  3. Create backup
  4. Write to temporary file
  5. Write to database (using database transaction)
  6. Replace original file atomically
  7. Create Git commit (if repository exists)
  
- **Features**:
  - Can include multiple database transactions
  - Can include file system operations
  - Can include validation steps
  - Can be rolled back (restore backup, rollback DB transaction)

#### DBWorker Role
- **Purpose**: Only manages query queue and returns responses
- **Does NOT**: Manage transactions, handle business logic
- **Does**: 
  - Receive queries from SQLiteDriverProxy
  - Execute queries via SQLiteDriver
  - Return results
  - Manage queue of pending queries

## Architecture Chain

**Final Chain**:
```
Command → UniversalDriver (CodeDatabase renamed) → SpecificDriver → DBWorker (for SQLite) → SQLiteDriver
```

**Transaction Flow**:
```
Command
  ↓
UniversalDriver.begin_transaction()  # High-level transaction
  ↓
  - Form CST
  - Validate
  - Create backup
  - Write temp file
  ↓
  SpecificDriver.begin_transaction()  # Database transaction
    ↓
    - Execute SQL queries
    ↓
  SpecificDriver.commit_transaction()  # Database transaction commit
  ↓
  - Replace file
  - Git commit
  ↓
UniversalDriver.commit_transaction()  # High-level transaction commit
```

## Remaining Questions

### Q1: Renaming Strategy

**Question**: How should we handle the renaming?

**Options**:
1. **Direct Rename**: Rename `CodeDatabase` to `UniversalDriver` everywhere
2. **Alias Approach**: Keep `CodeDatabase` as alias for backward compatibility
3. **Gradual Migration**: Introduce `UniversalDriver`, deprecate `CodeDatabase`, migrate gradually

**Recommendation**: Option 1 - Direct rename, as this is internal refactoring and commands will use the same API.

**Checklist**:
- [ ] Rename class `CodeDatabase` → `UniversalDriver`
- [ ] Update all imports
- [ ] Update all references
- [ ] Update documentation
- [ ] Update tests

### Q2: High-Level Transaction Implementation

**Question**: How should high-level transactions work with database transactions?

**Current Understanding**:
- High-level transaction can include multiple database transactions
- If high-level transaction fails, all database transactions should rollback
- File operations should be atomic (backup/restore)

**Example**:
```python
# In UniversalDriver
def begin_transaction(self):
    """Begin high-level transaction."""
    self._high_level_transaction_active = True
    # Database transaction will be started when needed

def commit_transaction(self):
    """Commit high-level transaction."""
    # Commit all nested database transactions
    if self._db_transaction_active:
        self.driver.commit()  # Commit database transaction
    self._high_level_transaction_active = False

def rollback_transaction(self):
    """Rollback high-level transaction."""
    # Rollback database transaction
    if self._db_transaction_active:
        self.driver.rollback()
    # Restore backups, etc.
    self._high_level_transaction_active = False
```

**Question**: Is this correct? Should high-level transactions automatically manage database transactions?

### Q3: DBWorker Transaction Support

**Question**: Does DBWorker need to understand transactions, or just pass them through?

**Current Understanding**:
- DBWorker receives transaction commands (begin_transaction, commit_transaction, rollback_transaction)
- DBWorker passes them to SQLiteDriver
- DBWorker manages queue but doesn't interpret transaction semantics
- Transaction ID is used to group queries in queue

**Question**: Is this correct?

### Q4: File Operations in Transactions

**Question**: How should file operations (backup, write, restore) be handled in high-level transactions?

**Current Understanding**:
- Backup is created before transaction starts
- File write happens during transaction
- If transaction fails, backup is restored
- This is handled by BackupManager and command logic, not UniversalDriver

**Question**: Should UniversalDriver provide file operation transaction support, or is it command-level?

### Q5: Database Initialization

**Question**: Where should database file existence check and initialization happen?

**Current Understanding**:
- UniversalDriver should check if database file exists
- UniversalDriver should create file if needed
- UniversalDriver should initialize schema
- This happens before first use

**Question**: Should this be automatic on first `get_database()` call, or explicit `initialize()` method?

## Updated Implementation Plan

Based on clarifications:

### Phase 1: Rename CodeDatabase to UniversalDriver

**Steps**:
1. Rename class `CodeDatabase` → `UniversalDriver`
2. Update all imports and references
3. Update documentation
4. Ensure API remains the same

### Phase 2: Add Database Initialization to UniversalDriver

**Steps**:
1. Add `ensure_database_exists()` method
2. Add `initialize_schema()` method (already exists as `_create_schema()`)
3. Add automatic initialization on first use

### Phase 3: Enhance High-Level Transactions

**Steps**:
1. Document high-level transaction semantics
2. Ensure database transactions are properly nested
3. Add file operation support (if needed)
4. Add rollback support for file operations

### Phase 4: Update DBWorkerManager Integration

**Steps**:
1. DBWorkerManager reads config
2. DBWorkerManager starts DB worker for SQLite
3. DBWorkerManager registers with WorkerManager
4. UniversalDriver uses SQLiteDriverProxy (which connects to DB worker)

### Phase 5: Unify Worker Startup

**Steps**:
1. Create worker startup helpers
2. Refactor worker startup functions
3. Eliminate code duplication

## Next Steps

Please answer the remaining questions (Q1-Q5) so I can finalize the implementation plan.
