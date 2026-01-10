# Technical Specification: Database Driver Architecture Refactoring

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10  
**Status**: Draft - Questions for clarification

## 1. Executive Summary

This document specifies the refactoring of database access architecture to:
1. Eliminate code duplication in worker initialization
2. Implement unified database driver layer for multi-database support
3. Centralize worker management through a single manager
4. Ensure proper database initialization and file management

## 2. Current Architecture Analysis

### 2.1 Current State

**Database Access Chain**:
```
Command → CodeDatabase → create_driver() → SQLiteDriverProxy → DB Worker → SQLiteDriver
```

**Components**:
- `CodeDatabase`: High-level database API, creates schema on init
- `BaseDatabaseDriver`: Abstract interface for database drivers
- `SQLiteDriver`: Direct SQLite driver (only in DB worker process)
- `SQLiteDriverProxy`: Proxy driver communicating with DB worker via Unix socket
- `DBWorkerManager`: Manages DB worker processes (separate from WorkerManager)
- `WorkerManager`: Manages all other workers (vectorization, file_watcher, repair)

**Problems**:
1. Code duplication in worker startup (83 lines duplicated)
2. No unified driver layer - commands directly use CodeDatabase
3. Database initialization scattered (in CodeDatabase._create_schema)
4. DBWorkerManager separate from WorkerManager
5. File watcher worker bypasses worker_launcher

## 3. Target Architecture

### 3.1 Database Access Chain

**New Chain**:
```
Command → UniversalDriver → CodeDatabase → SQLiteDriverProxy → DB Worker Process → SQLiteDriver
                                    ↓
                            DBWorkerManager (manages DB worker)
                                    ↓
                            WorkerManager (unified worker management)
```

**Important**: 
- Commands NEVER use SQLiteDriver directly
- SQLiteDriver is ONLY used inside DB worker process
- Commands use SQLiteDriverProxy which communicates with DB worker via Unix socket
- For future databases (MySQL, PostgreSQL), direct drivers may be used (no worker needed)

### 3.2 Component Responsibilities

#### 3.2.1 UniversalDriver (New Component)

**Purpose**: Unified interface for all database operations, independent of specific database type.

**Responsibilities**:
- Provide unified API for commands (same interface for SQLite, MySQL, PostgreSQL, etc.)
- Handle database file existence checks
- Initialize database schema (delegate to CodeDatabase)
- Manage database lifecycle (create, migrate, validate)
- Route requests to appropriate specific driver via CodeDatabase

**Location**: `code_analysis/core/database/universal_driver.py`

**Interface**:
```python
class UniversalDriver:
    """Unified database driver interface for all database types."""
    
    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize universal driver.
        
        Args:
            db_config: Database configuration with 'type' and connection details
        """
    
    def ensure_database_exists(self) -> bool:
        """Ensure database file/connection exists, create if needed."""
    
    def initialize_schema(self) -> None:
        """Initialize database schema if not exists."""
    
    def get_database(self) -> CodeDatabase:
        """Get CodeDatabase instance for operations."""
    
    def close(self) -> None:
        """Close database connection."""
```

#### 3.2.2 CodeDatabase (Refactored)

**Changes**:
- Remove schema creation from `__init__` (move to UniversalDriver)
- Keep high-level API methods
- Delegate schema creation to UniversalDriver
- Focus on query execution and data operations

**New Interface**:
```python
class CodeDatabase:
    """Database for code analysis data using pluggable drivers."""
    
    def __init__(self, driver_config: Dict[str, Any], auto_create_schema: bool = False):
        """
        Initialize database connection.
        
        Args:
            driver_config: Driver configuration
            auto_create_schema: If True, create schema on init (default: False)
        """
```

#### 3.2.3 Specific Drivers (SQLiteDriver, SQLiteDriverProxy, etc.)

**SQLite Architecture**:
- `SQLiteDriver`: Direct SQLite access **ONLY inside DB worker process**
  - Used by DB worker to execute actual SQL queries
  - Never used directly by commands or other processes
  - Communicates with SQLite file directly
  
- `SQLiteDriverProxy`: Proxy driver for client processes
  - Used by commands, workers, and all non-DB-worker processes
  - Communicates with DB worker via Unix socket
  - Translates driver calls to worker requests

**Responsibilities**:
- Implement BaseDatabaseDriver interface
- Handle database-specific operations
- Provide connection management
- **Do NOT** handle file existence or schema creation (handled by UniversalDriver)

**Current Drivers**:
- `SQLiteDriver`: Direct SQLite access (only in DB worker process)
- `SQLiteDriverProxy`: Proxy to DB worker (for all client processes)

**Future Drivers**:
- `MySQLDriver`: Direct MySQL access (may not need worker)
- `PostgreSQLDriver`: Direct PostgreSQL access (may not need worker)
- Other database drivers as needed

#### 3.2.4 DBWorkerManager (Refactored)

**Changes**:
- Read database configuration from config
- Start DB worker process automatically for SQLite databases
- Integrate with WorkerManager for unified management
- Handle worker lifecycle (start, stop, restart)

**New Responsibilities**:
- Parse config to determine database type
- For SQLite: start DB worker process if not running
- For other DB types: may start connection pool workers if needed
- Register with WorkerManager

**Location**: `code_analysis/core/db_worker_manager.py` (refactored)

#### 3.2.5 WorkerManager (Enhanced)

**Changes**:
- Accept DB worker registration from DBWorkerManager
- Provide unified interface for all worker types
- Handle graceful shutdown of all workers including DB workers

**New Methods**:
```python
def register_db_worker(self, db_path: str, worker_info: Dict[str, Any]) -> None:
    """Register DB worker from DBWorkerManager."""
```

### 3.3 Worker Startup Flow

**New Flow**:
```
1. Server Startup
   ↓
2. WorkerManager.get_instance() - Initialize unified manager
   ↓
3. DBWorkerManager.get_instance() - Initialize DB worker manager
   ↓
4. DBWorkerManager reads config → determines DB type
   ↓
5. For SQLite: DBWorkerManager starts DB worker process
   ↓
6. DB Worker Process:
   - Sets CODE_ANALYSIS_DB_WORKER=1 environment variable
   - Uses SQLiteDriver (direct driver) to access SQLite file
   - Listens on Unix socket for requests from SQLiteDriverProxy
   ↓
7. DBWorkerManager registers DB worker with WorkerManager
   ↓
8. WorkerManager starts other workers (vectorization, file_watcher)
   ↓
9. All workers use worker_launcher functions
   ↓
10. All workers registered with WorkerManager
   ↓
11. Commands use UniversalDriver → CodeDatabase → SQLiteDriverProxy → DB Worker
```

## 4. Implementation Plan

### 4.1 Phase 1: Create UniversalDriver

**Tasks**:
1. Create `code_analysis/core/database/universal_driver.py`
2. Implement `UniversalDriver` class with:
   - Database file existence check
   - Database initialization (create file if needed)
   - Schema initialization (call CodeDatabase._create_schema)
   - CodeDatabase instance management
3. Add configuration parsing for database type
4. Add unit tests

**Files to Create**:
- `code_analysis/core/database/universal_driver.py`

**Files to Modify**:
- `code_analysis/core/database/base.py` - Remove schema creation from `__init__`, add `auto_create_schema` parameter

### 4.2 Phase 2: Refactor CodeDatabase

**Tasks**:
1. Modify `CodeDatabase.__init__` to accept `auto_create_schema` parameter
2. Move `_create_schema()` call to conditional (only if `auto_create_schema=True`)
3. Update all CodeDatabase instantiations to use new signature
4. Ensure backward compatibility where possible

**Files to Modify**:
- `code_analysis/core/database/base.py`
- All files that create CodeDatabase instances

### 4.3 Phase 3: Refactor DBWorkerManager

**Tasks**:
1. Add config reading capability to DBWorkerManager
2. Add automatic DB worker startup for SQLite
3. Integrate with WorkerManager (register DB workers)
4. Add database type detection from config
5. Handle non-SQLite databases (future support)

**Files to Modify**:
- `code_analysis/core/db_worker_manager.py`

**New Methods**:
```python
def initialize_from_config(self, config: Dict[str, Any]) -> None:
    """Initialize DB workers from configuration."""
    
def get_db_type(self, db_config: Dict[str, Any]) -> str:
    """Determine database type from config."""
    
def ensure_worker_running(self, db_path: str, db_type: str) -> Dict[str, Any]:
    """Ensure DB worker is running for given database."""
```

### 4.4 Phase 4: Unify Worker Management

**Tasks**:
1. Ensure all workers use `worker_launcher` functions
2. Refactor `startup_file_watcher_worker()` to use `worker_launcher.start_file_watcher_worker()`
3. Remove direct `multiprocessing.Process` creation from `main.py`
4. Ensure all workers register with WorkerManager
5. Create worker startup helpers to eliminate duplication

**Files to Create**:
- `code_analysis/core/worker_startup_helpers.py` (from analysis document)

**Files to Modify**:
- `code_analysis/main.py` - Use worker_launcher for all workers
- `code_analysis/core/worker_launcher.py` - Ensure consistency

### 4.5 Phase 5: Update Commands to Use UniversalDriver

**Tasks**:
1. Update `BaseMCPCommand._open_database()` to use UniversalDriver
2. Update all commands that directly create CodeDatabase
3. Ensure UniversalDriver handles database initialization
4. Update tests

**Files to Modify**:
- `code_analysis/commands/base_mcp_command.py`
- All command files that create database connections

### 4.6 Phase 6: Testing and Validation

**Tasks**:
1. Unit tests for UniversalDriver
2. Integration tests for database initialization
3. Tests for worker startup flow
4. Tests for multi-database support (SQLite first)
5. Performance tests

## 5. Configuration Structure

### 5.1 Database Configuration

**New Config Structure**:
```json
{
  "code_analysis": {
    "database": {
      "type": "sqlite",
      "path": "data/code_analysis.db",
      "worker": {
        "enabled": true,
        "log_path": "logs/db_worker.log"
      }
    }
  }
}
```

**Future Support**:
```json
{
  "code_analysis": {
    "database": {
      "type": "mysql",
      "host": "localhost",
      "port": 3306,
      "database": "code_analysis",
      "user": "user",
      "password": "password"
    }
  }
}
```

### 5.2 Worker Configuration

**Unified Structure**:
```json
{
  "code_analysis": {
    "workers": {
      "database": {
        "enabled": true,
        "log_path": "logs/db_worker.log"
      },
      "vectorization": {
        "enabled": true,
        "batch_size": 10,
        "poll_interval": 30
      },
      "file_watcher": {
        "enabled": true,
        "scan_interval": 60,
        "watch_dirs": ["/path/to/projects"]
      }
    }
  }
}
```

## 6. Migration Strategy

### 6.1 Backward Compatibility

**Requirements**:
- Existing config files should continue to work
- Commands should work without changes (internal refactoring)
- Database files should be compatible

**Approach**:
- UniversalDriver detects old config format and converts
- CodeDatabase maintains backward compatibility for driver_config
- Gradual migration: old code continues to work, new code uses UniversalDriver

### 6.2 Rollout Plan

1. **Week 1**: Implement UniversalDriver, test in isolation
2. **Week 2**: Refactor CodeDatabase, update tests
3. **Week 3**: Refactor DBWorkerManager, integrate with WorkerManager
4. **Week 4**: Unify worker startup, eliminate duplication
5. **Week 5**: Update commands to use UniversalDriver
6. **Week 6**: Testing, bug fixes, documentation

## 7. Questions for Clarification

### 7.1 Architecture Questions

**Q1**: Should `CodeDatabase` become the "UniversalDriver" or should we create a new layer?

**Current Understanding**: Create new `UniversalDriver` layer that wraps `CodeDatabase`. This allows:
- Commands to use UniversalDriver (database-agnostic)
- UniversalDriver to handle initialization
- CodeDatabase to focus on operations
- Easy addition of new database types

**Clarified**: For SQLite, the chain is:
- UniversalDriver → CodeDatabase → SQLiteDriverProxy → DB Worker → SQLiteDriver
- SQLiteDriver is NEVER used directly by commands

**Q2**: Should `DBWorkerManager` be merged into `WorkerManager` or kept separate?

**Current Understanding**: Keep separate but integrate:
- `DBWorkerManager` handles DB-specific worker logic (SQLite worker process)
- `WorkerManager` handles all workers uniformly
- `DBWorkerManager` registers DB workers with `WorkerManager`

**Q3**: Where should database schema creation happen?

**Current Understanding**: 
- UniversalDriver calls `CodeDatabase._create_schema()` after ensuring database exists
- CodeDatabase provides `_create_schema()` method but doesn't call it automatically
- UniversalDriver is responsible for initialization lifecycle

**Q4**: Should database file existence check happen in UniversalDriver or specific driver?

**Current Understanding**: 
- UniversalDriver checks file existence (for file-based DBs like SQLite)
- UniversalDriver creates file if needed
- Specific driver (SQLiteDriver) only handles connection to existing file
- For server-based DBs (MySQL, PostgreSQL), UniversalDriver checks connection instead

**Q5**: How should non-SQLite databases work with workers?

**Current Understanding**:
- SQLite: Requires DB worker process (file-based, needs single writer)
  - Commands use SQLiteDriverProxy → DB Worker → SQLiteDriver
  - SQLiteDriver is ONLY in DB worker process
- MySQL/PostgreSQL: May use connection pooling, no separate worker process needed
  - Commands use MySQLDriver/PostgreSQLDriver directly (no proxy)
- UniversalDriver determines if worker is needed based on database type
- DBWorkerManager only starts workers for databases that need them (currently only SQLite)

### 7.2 Implementation Questions

**Q6**: Should we maintain backward compatibility with existing `driver_config` format?

**Answer Needed**: Yes/No

**Q7**: Should database initialization be synchronous or async?

**Current Understanding**: Synchronous for now, can be made async later if needed.

**Q8**: How should we handle database migrations in the future?

**Current Understanding**: 
- Phase 1: Only schema creation (current behavior)
- Phase 2: Add migration system (future work)
- UniversalDriver will handle migration calls when system is ready

## 8. Success Criteria

### 8.1 Functional Requirements

- [ ] All workers start through WorkerManager
- [ ] Database access goes through UniversalDriver → CodeDatabase → SpecificDriver
- [ ] Database initialization handled by UniversalDriver
- [ ] DB worker started automatically for SQLite databases
- [ ] No code duplication in worker startup
- [ ] Commands work without changes (internal refactoring)

### 8.2 Non-Functional Requirements

- [ ] Backward compatibility with existing configs
- [ ] Performance: No regression in database access speed
- [ ] Maintainability: Clear separation of concerns
- [ ] Testability: All components unit tested
- [ ] Documentation: Architecture documented

### 8.3 Code Quality

- [ ] Zero code duplication in worker startup
- [ ] All workers use worker_launcher
- [ ] Consistent error handling
- [ ] Proper logging at all levels

## 9. Risks and Mitigation

### 9.1 Risks

1. **Breaking Changes**: Refactoring may break existing functionality
   - **Mitigation**: Extensive testing, gradual rollout, backward compatibility

2. **Performance Impact**: Additional layer may add overhead
   - **Mitigation**: Benchmarking, optimization, caching

3. **Complexity**: New layer adds complexity
   - **Mitigation**: Clear documentation, simple interfaces, good abstractions

4. **Migration Issues**: Existing databases may need migration
   - **Mitigation**: Schema compatibility, migration scripts if needed

### 9.2 Rollback Plan

- Keep old code in separate branch
- Feature flags for new vs old code paths
- Gradual migration with ability to revert

## 10. Dependencies

### 10.1 External Dependencies

- No new external dependencies required
- Existing dependencies sufficient

### 10.2 Internal Dependencies

- `code_analysis/core/database/base.py` - CodeDatabase
- `code_analysis/core/db_driver/` - Driver implementations
- `code_analysis/core/db_worker_manager.py` - DB worker management
- `code_analysis/core/worker_manager.py` - Worker management
- `code_analysis/core/worker_launcher.py` - Worker startup

## 11. Timeline

**Estimated Duration**: 6 weeks

**Milestones**:
- Week 1: UniversalDriver implementation
- Week 2: CodeDatabase refactoring
- Week 3: DBWorkerManager integration
- Week 4: Worker startup unification
- Week 5: Command updates
- Week 6: Testing and bug fixes

## 12. Open Questions

Please answer the questions in Section 7 to proceed with implementation.
