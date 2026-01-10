# Architecture Clarification Questions

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Clarified Architecture

**Target Chain**:
```
Command → UniversalDriver → SpecificDriver → DBWorker (for SQLite)
```

**Components**:
- **UniversalDriver**: Unified access for all DBMS (SQLite, PostgreSQL, MySQL, etc.)
- **SpecificDriver**: Special driver for each DB type (SQLiteDriverProxy, MySQLDriver, etc.)
- **DBWorker**: Only for SQLite, manages queue of queries (separate process)
- **WorkerManager**: Starts DBWorker (not driver)

## Questions

### Q1: What happens to CodeDatabase?

**Current State**: 
- `CodeDatabase` contains high-level business logic:
  - Methods for projects: `add_project()`, `get_project()`, `update_project()`
  - Methods for files: `add_file()`, `get_file()`, `update_file_data_atomic()`
  - Methods for entities: `add_class()`, `search_classes()`, `search_methods()`
  - Methods for chunks: `add_code_chunk()`, `get_chunks()`
  - Methods for AST/CST: `get_ast_tree()`, `get_cst_tree()`
  - And many more...

**Question**: 
- Should `CodeDatabase` be removed completely?
- Or should `UniversalDriver` inherit/contain `CodeDatabase` functionality?
- Or should `UniversalDriver` provide the same API as `CodeDatabase` currently does?

**Current Understanding**: 
`CodeDatabase` has ~100+ methods for business logic. If we remove it, where do these methods go?

**Options**:
1. **UniversalDriver replaces CodeDatabase**: UniversalDriver has all business logic methods
2. **UniversalDriver wraps CodeDatabase**: UniversalDriver creates CodeDatabase internally, exposes same API
3. **CodeDatabase becomes internal**: CodeDatabase is used internally by UniversalDriver, not exposed to commands

**Recommendation**: Option 2 - UniversalDriver wraps CodeDatabase internally, but commands use UniversalDriver API (which delegates to CodeDatabase).

---

### Q2: What API should UniversalDriver provide?

**Current State**:
Commands use `CodeDatabase` like this:
```python
db = CodeDatabase(driver_config)
project = db.add_project(...)
files = db.get_project_files(...)
classes = db.search_classes(...)
```

**Question**:
- Should commands use `UniversalDriver` with the same API?
- Or should `UniversalDriver` API be different?

**Current Understanding**:
Commands should use `UniversalDriver` with the same API as `CodeDatabase` currently provides.

**Example**:
```python
# Command code
driver = UniversalDriver(db_config)
project = driver.add_project(...)  # Same API as CodeDatabase
files = driver.get_project_files(...)
classes = driver.search_classes(...)
```

---

### Q3: How does UniversalDriver create SpecificDriver?

**Current State**:
`CodeDatabase` creates driver via `create_driver(driver_type, config)`.

**Question**:
- Should `UniversalDriver` call `create_driver()` directly?
- Or should `UniversalDriver` have its own driver factory?

**Current Understanding**:
UniversalDriver should:
1. Determine database type from config
2. Create appropriate SpecificDriver via `create_driver()`
3. For SQLite: use `SQLiteDriverProxy` (never `SQLiteDriver` directly)
4. For MySQL/PostgreSQL: use direct drivers

**Example**:
```python
class UniversalDriver:
    def _create_specific_driver(self) -> BaseDatabaseDriver:
        """Create specific driver based on database type."""
        if self.db_type == "sqlite":
            # Always use proxy for SQLite
            return create_driver("sqlite_proxy", {...})
        elif self.db_type == "mysql":
            return create_driver("mysql", {...})
        # ...
```

---

### Q4: Where does schema creation happen?

**Current State**:
`CodeDatabase._create_schema()` creates all tables.

**Question**:
- Should `UniversalDriver` call schema creation?
- Or should it be in SpecificDriver?
- Or should it be separate?

**Current Understanding**:
- `UniversalDriver.ensure_database_exists()` - creates file if needed
- `UniversalDriver.initialize_schema()` - creates schema (calls CodeDatabase._create_schema() or similar)
- Schema creation is database-agnostic (same schema for all DB types)

---

### Q5: How does UniversalDriver work with CodeDatabase?

**If CodeDatabase is kept internally**:

```python
class UniversalDriver:
    def __init__(self, db_config):
        self.db_config = db_config
        self._code_database: Optional[CodeDatabase] = None
    
    def get_database(self) -> CodeDatabase:
        """Get CodeDatabase instance (internal use)."""
        if self._code_database is None:
            driver_config = self._create_driver_config()
            self._code_database = CodeDatabase(driver_config, auto_create_schema=False)
            self.initialize_schema()
        return self._code_database
    
    def __getattr__(self, name):
        """Delegate all method calls to CodeDatabase."""
        return getattr(self.get_database(), name)
```

**If CodeDatabase is removed**:

All business logic methods must be moved to UniversalDriver or separate service classes.

---

### Q6: What about transaction management?

**Current State**:
`CodeDatabase` has transaction methods: `begin_transaction()`, `commit_transaction()`, `rollback_transaction()`.

**Question**:
- Should `UniversalDriver` provide transaction API?
- Or should it delegate to CodeDatabase/SpecificDriver?

**Current Understanding**:
UniversalDriver should provide transaction API, delegating to underlying driver.

---

## Proposed Architecture (Pending Answers)

Based on current understanding:

```
Command
  ↓
UniversalDriver (unified API, business logic)
  ↓ (internal)
CodeDatabase (business logic wrapper, uses driver)
  ↓
SpecificDriver (SQLiteDriverProxy, MySQLDriver, etc.)
  ↓ (for SQLite)
DBWorker Process (manages query queue)
  ↓
SQLiteDriver (direct SQLite access)
```

**But user said**: Command → UniversalDriver → SpecificDriver

**So maybe**:
```
Command
  ↓
UniversalDriver (unified API, contains all business logic)
  ↓ (directly uses)
SpecificDriver (SQLiteDriverProxy, MySQLDriver, etc.)
  ↓ (for SQLite)
DBWorker Process
  ↓
SQLiteDriver
```

**Question**: Which architecture is correct?

---

## Summary of Questions

1. **Q1**: What happens to CodeDatabase? Remove, wrap, or inherit?
2. **Q2**: What API should UniversalDriver provide? Same as CodeDatabase?
3. **Q3**: How does UniversalDriver create SpecificDriver?
4. **Q4**: Where does schema creation happen?
5. **Q5**: How does UniversalDriver work with CodeDatabase (if kept)?
6. **Q6**: What about transaction management?

Please clarify these points so I can update the implementation plan correctly.
