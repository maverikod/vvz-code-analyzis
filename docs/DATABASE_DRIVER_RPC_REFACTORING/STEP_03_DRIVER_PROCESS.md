# Step 3: Driver Process Implementation

**Priority**: 2 (High)  
**Dependencies**: Step 1 (Query Language Testing), **Step 2 (RPC Infrastructure)** - **CRITICAL**  
**Estimated Time**: 3-4 weeks

## Implementation Status

**Status**: ❌ **NOT IMPLEMENTED** (0%)

### Current State:
- ❌ **New driver process**: `code_analysis/core/database_driver_pkg/` - **NOT EXISTS**
- ✅ **Old driver exists**: `code_analysis/core/db_driver/` (old architecture, still in use)
  - `sqlite_proxy.py` - Old proxy driver ✅ (still in use)
  - `sqlite.py` - Direct SQLite driver ✅ (still in use)
  - `base.py` - Old base driver interface ✅ (still in use)

### Missing Components:
- `code_analysis/core/database_driver_pkg/` - **ENTIRE PACKAGE DOES NOT EXIST**
- All files listed in "Files to Create" section - **NONE EXIST**

### Critical Dependency:
- ⚠️ **Step 5 (RPC Infrastructure) MUST be completed FIRST**
  - BaseRequest and BaseResult classes are required for Step 2
  - Driver must implement abstract methods from base classes

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Goal

Implement database driver process that runs in separate process, manages database connection, and handles request queue. Driver works in terms of database tables (not objects).

## Overview

Driver process:
- Runs in separate process (managed by WorkerManager)
- Connects to database (SQLite, PostgreSQL, MySQL, etc.)
- Manages request queue internally
- Works with database tables, columns, cells (low-level operations)
- Provides RPC server for client communication

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing database driver code using `code_mapper` indexes
- [ ] Review existing `code_analysis/core/db_driver/` implementations
- [ ] Check for existing RPC server implementations
- [ ] Review request queue implementations if any exist
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes
- [ ] Keep indexes up-to-date for other developers and tools

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] Verify no duplicate code was introduced
- [ ] Check file sizes (must be < 400 lines)
- [ ] Split files if they exceed 400 lines
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

**Commands**:
```bash
# Check existing functionality (excludes tests and test_data)
code_mapper -r code_analysis/

# Update indexes after changes (excludes tests and test_data)
code_mapper -r code_analysis/
```

## Checklist

### 2.1 Create Driver Process Package Structure
- [ ] Create `code_analysis/core/database_driver_pkg/` directory
- [ ] Create `__init__.py`
- [ ] Create package structure

**Files to Create**:
- `code_analysis/core/database_driver_pkg/__init__.py`
- `code_analysis/core/database_driver_pkg/runner.py`
- `code_analysis/core/database_driver_pkg/rpc_server.py`
- `code_analysis/core/database_driver_pkg/request_queue.py`
- `code_analysis/core/database_driver_pkg/exceptions.py`

### 2.2 Implement Request Queue
- [ ] Create request queue class
- [ ] Implement queue operations (enqueue, dequeue)
- [ ] Implement queue management (size limits, priorities)
- [ ] Implement queue monitoring

**Files to Create**:
- `code_analysis/core/database_driver_pkg/request_queue.py`

**Queue Features**:
- [ ] Thread-safe queue operations
- [ ] Request prioritization
- [ ] Queue size limits
- [ ] Request timeout handling
- [ ] Queue statistics

### 2.3 Create Base Driver Interface
- [ ] Define `BaseDatabaseDriver` interface
- [ ] Define required methods (connect, disconnect, execute, etc.)
- [ ] Define table-level operations

**Files to Create**:
- `code_analysis/core/database_driver_pkg/drivers/__init__.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`

**Driver Interface Methods**:
- [ ] `connect(config: dict) -> None`
- [ ] `disconnect() -> None`
- [ ] `create_table(schema: dict) -> bool`
- [ ] `drop_table(table_name: str) -> bool`
- [ ] `insert(table_name: str, data: dict) -> int`
- [ ] `update(table_name: str, where: dict, data: dict) -> int`
- [ ] `delete(table_name: str, where: dict) -> int`
- [ ] `select(table_name: str, where: dict, columns: list, limit: int, offset: int) -> list[dict]`
- [ ] `execute(sql: str, params: tuple) -> dict`
- [ ] `begin_transaction() -> str`
- [ ] `commit_transaction(transaction_id: str) -> bool`
- [ ] `rollback_transaction(transaction_id: str) -> bool`
- [ ] `get_table_info(table_name: str) -> list[dict]`
- [ ] `sync_schema(schema_definition: dict, backup_dir: str) -> dict`

### 2.4 Implement SQLite Driver
- [ ] Implement SQLite driver for driver process
- [ ] Implement all table-level operations
- [ ] Implement transaction support
- [ ] Implement schema operations
- [ ] **Implement all abstract methods from BaseRequest classes**
- [ ] **Implement all abstract methods from BaseResult classes**
- [ ] **Use concrete request classes (InsertRequest, SelectRequest, etc.)**
- [ ] **Return concrete result classes (SuccessResult, ErrorResult, etc.)**

**Files to Create**:
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`

**Note**: This is different from existing `SQLiteDriver` - this one runs in driver process and works with tables directly.

**⚠️ IMPORTANT**: BaseRequest and BaseResult classes are created in Step 2 (RPC Infrastructure). In Step 3, create the basic driver structure. The implementation of abstract methods from BaseRequest and BaseResult can be completed in Step 3 after Step 2 is done, or these requirements can be addressed when Step 2 is completed.

**Key Requirements**:
- [ ] SQLite driver must implement all abstract methods from `BaseRequest` and `BaseResult` (after Step 5)
- [ ] Driver must use concrete request classes for all operations (after Step 5)
- [ ] Driver must return concrete result classes for all operations (after Step 5)
- [ ] Implementation must be extensible (other drivers can follow same pattern)

### 2.5 Implement Driver Runner
- [ ] Create process entry point `run_database_driver()`
- [ ] Initialize request queue
- [ ] Load driver implementation based on type
- [ ] Connect to database
- [ ] Start request processing loop

**Files to Create**:
- `code_analysis/core/database_driver_pkg/runner.py`
- `code_analysis/core/database_driver_pkg/driver_factory.py`

**Runner Features**:
- [ ] Process entry point
- [ ] Driver type loading from config
- [ ] Database connection management
- [ ] Request queue initialization
- [ ] Request processing loop
- [ ] Error handling and recovery
- [ ] Graceful shutdown

### 2.6 Implement RPC Server
- [ ] Create RPC server for driver process
- [ ] Implement Unix socket server
- [ ] Implement request/response handling
- [ ] Integrate with request queue
- [ ] Implement error handling

**Files to Create**:
- `code_analysis/core/database_driver_pkg/rpc_server.py`
- `code_analysis/core/database_driver_pkg/rpc_protocol.py`

**RPC Server Features**:
- [ ] Unix socket server
- [ ] Request deserialization
- [ ] Request queuing
- [ ] Response serialization
- [ ] Error handling
- [ ] Connection management

### 2.7 Implement RPC Method Handlers
- [ ] Map RPC methods to driver methods
- [ ] Implement table operations handlers
- [ ] Implement transaction handlers
- [ ] Implement schema operations handlers
- [ ] Implement error handling

**Files to Modify**:
- `code_analysis/core/database_driver_pkg/rpc_server.py`

**RPC Methods**:
- [ ] `create_table(schema: dict) -> bool`
- [ ] `drop_table(table_name: str) -> bool`
- [ ] `insert(table_name: str, data: dict) -> int`
- [ ] `update(table_name: str, where: dict, data: dict) -> int`
- [ ] `delete(table_name: str, where: dict) -> int`
- [ ] `select(table_name: str, where: dict, columns: list, limit: int, offset: int) -> list[dict]`
- [ ] `execute(sql: str, params: tuple) -> dict`
- [ ] `begin_transaction() -> str`
- [ ] `commit_transaction(transaction_id: str) -> bool`
- [ ] `rollback_transaction(transaction_id: str) -> bool`
- [ ] `get_table_info(table_name: str) -> list[dict]`
- [ ] `sync_schema(schema_definition: dict, backup_dir: str) -> dict`

### 2.8 Testing
- [ ] Test driver process startup
- [ ] Test request queue operations
- [ ] Test all RPC methods
- [ ] Test transaction operations
- [ ] Test error handling
- [ ] Test concurrent requests
- [ ] Test queue overflow handling

**Files to Create**:
- `tests/test_database_driver_process.py`
- `tests/test_request_queue.py`
- `tests/test_driver_rpc_server.py`

## Deliverables

- ✅ Driver process can be started as separate process
- ✅ Request queue implemented and working
- ✅ SQLite driver implemented (table-level operations)
- ✅ RPC server implemented
- ✅ All RPC methods work correctly
- ✅ Request queue manages requests properly
- ✅ All tests pass

## Files to Create

- `code_analysis/core/database_driver_pkg/__init__.py`
- `code_analysis/core/database_driver_pkg/runner.py`
- `code_analysis/core/database_driver_pkg/rpc_server.py`
- `code_analysis/core/database_driver_pkg/rpc_protocol.py`
- `code_analysis/core/database_driver_pkg/request_queue.py`
- `code_analysis/core/database_driver_pkg/driver_factory.py`
- `code_analysis/core/database_driver_pkg/exceptions.py`
- `code_analysis/core/database_driver_pkg/drivers/__init__.py`
- `code_analysis/core/database_driver_pkg/drivers/base.py`
- `code_analysis/core/database_driver_pkg/drivers/sqlite.py`
- `tests/test_database_driver_process.py`
- `tests/test_request_queue.py`
- `tests/test_driver_rpc_server.py`

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] Request queue operations
- [ ] Driver methods (all table operations)
- [ ] RPC handlers
- [ ] Transaction operations
- [ ] Schema operations
- [ ] **Coverage: 90%+ for all modules**

### Integration Tests with Real Data
- [ ] **Test driver with real database from test_data projects**
- [ ] Test all table operations on real database schema
- [ ] Test queries on real data (projects, files, etc.)
- [ ] Test transactions on real data
- [ ] Test schema operations on real database
- [ ] Test request queue with real requests

**Real Data Test Requirements**:
- [ ] Use actual database with data from test_data projects
- [ ] Test operations on real projects (vast_srv, bhlff, etc.)
- [ ] Test operations on real files from test_data
- [ ] Test operations on real AST/CST trees from test_data
- [ ] Verify all operations work correctly with real data

### Integration Tests with Real Server
- [ ] **Test driver process with real running server**
- [ ] Test RPC communication with real server
- [ ] Test all RPC methods through real server
- [ ] Test concurrent requests through real server
- [ ] Test error scenarios with real server

### Concurrency Tests
- [ ] Multiple concurrent requests
- [ ] Request queue overflow handling
- [ ] Concurrent transactions
- [ ] Thread safety

### Error Tests
- [ ] Error handling, queue overflow, connection failures
- [ ] Database connection errors
- [ ] Invalid request handling
- [ ] Transaction rollback scenarios

## Success Criteria

- ✅ **Test coverage 90%+ for all driver modules**
- ✅ Driver process starts successfully
- ✅ Request queue works correctly
- ✅ All table-level operations work
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**
- ✅ RPC server handles requests correctly
- ✅ Transactions work correctly
- ✅ Error handling is robust
- ✅ Performance is acceptable

## Key Points

- **Driver works with tables**: All operations are table-level (insert, update, delete, select)
- **Request queue in driver**: Queue is managed inside driver process
- **No object models**: Driver doesn't know about Project, File, etc. - only tables
- **RPC communication**: Driver exposes RPC server for client communication

## Next Steps

After completing this step, proceed to:
- [Step 4: Client Implementation](./STEP_04_CLIENT_IMPLEMENTATION.md)
