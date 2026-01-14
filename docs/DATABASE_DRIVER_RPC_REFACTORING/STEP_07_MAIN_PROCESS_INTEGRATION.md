# Step 7: Main Process Integration

**Priority**: Integration  
**Dependencies**: Step 5 (Configuration), Step 6 (WorkerManager Integration)  
**Estimated Time**: 1 week

## Goal

Integrate database driver startup into main process.

## Implementation Status

**Status**: ✅ **IMPLEMENTED** (~100%)

### Current State:
- ✅ **Function `startup_database_driver()` implemented**: `code_analysis/main.py:536-617`
- ✅ **Driver config loading**: Uses `get_driver_config()` from `code_analysis.core.config`
- ✅ **Startup sequence**: Driver starts before other workers (main.py:1099-1102)
- ✅ **Shutdown handling**: Implemented via signal handlers and atexit (main.py:1028-1083)
- ✅ **Test coverage**: Unit tests implemented (`tests/test_main_process_integration.py` - 7 tests, all passing)

### Completed Components:
- ✅ `startup_database_driver()` function loads config from `code_analysis.database.driver`
- ✅ Driver starts before vectorization and file watcher workers
- ✅ Shutdown handlers stop all workers including database driver
- ✅ Error handling during startup and shutdown
- ✅ Unit tests for driver startup, config loading, and error handling
- ✅ All hardcoded values replaced with constants from `code_analysis.core.constants`
- ✅ Fixed incorrect `asyncio.run()` usage for synchronous functions in startup event handler

### Missing/Incomplete Components:
- ⚠️ **Integration tests with real server**: Planned for Step 15 (Unified Testing Pipeline)

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [x] **ALWAYS run code_mapper** to check if functionality already exists in project
- [x] Search existing main process code using `code_mapper` indexes
- [x] Review existing `code_analysis/main.py` startup sequence
- [x] Check for existing worker startup patterns
- [x] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [x] **Run code_mapper after each block of changes** to update indexes
- [x] Use command: `code_mapper -r code_analysis/` to update indexes

### After Writing Code (Production Code Only, Not Tests)
- [x] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [x] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [x] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [x] Fix all code quality issues detected by code_mapper
- [x] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

- [x] Load driver config from `code_analysis.database.driver` (via `get_driver_config()` in `code_analysis/core/config.py:536`)
- [x] Create `startup_database_driver()` function (`code_analysis/main.py:536-617`)
- [x] Update startup sequence (driver starts BEFORE other workers) (`main.py:1099-1102`)
- [x] Add shutdown handling (`main.py:1028-1083` - signal handlers and atexit)
- [x] Test server startup with new sequence (unit tests in `tests/test_main_process_integration.py`)
- [x] Test driver startup on server start (unit tests implemented)
- [x] Test shutdown sequence (covered by WorkerManager tests)

## Files Modified

- ✅ `code_analysis/main.py` - Driver startup and shutdown implemented
  - `startup_database_driver()` function: lines 536-617
  - Startup sequence: lines 1099-1102 (driver starts before other workers)
  - Shutdown handlers: lines 1028-1083 (signal handlers and atexit)
  - Startup event handler: lines 389-471 (background thread startup)
  - Shutdown event handler: lines 473-514

## Test Files

- ✅ `tests/test_main_process_integration.py` - Unit tests for main process integration
  - 7 unit tests covering driver startup, config loading, error handling
  - All tests passing
  - Tests verify integration with WorkerManager and config loading logic

## Implementation Details

### Driver Configuration Loading
- Function `get_driver_config()` in `code_analysis/core/config.py:536` loads config from `code_analysis.database.driver` section
- Falls back to `code_analysis.db_path` for backward compatibility
- Returns driver config dict with `type` and `config` keys
- Log file path uses `DEFAULT_DATABASE_DRIVER_LOG_FILENAME` constant from `code_analysis.core.constants`

### Startup Sequence
1. **Database driver** starts first (line 1102) - required because other workers depend on it
2. **Vectorization worker** starts second (line 1123)
3. **File watcher worker** starts third (line 1138)
4. **Server** starts last (line 1167)

### Shutdown Sequence
- Signal handlers (SIGTERM, SIGINT) call `cleanup_workers()` (line 1072)
- `atexit` handler also calls `cleanup_workers()` (line 1081)
- FastAPI shutdown event handler stops all workers (line 506)
- All workers including database driver are stopped via `worker_manager.stop_all_workers()`
- Shutdown timeout uses `DEFAULT_SHUTDOWN_GRACE_TIMEOUT` constant (30.0 seconds) from `code_analysis.core.constants`

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [x] **Test driver startup via WorkerManager** (`test_main_process_integration.py`)
- [x] Test driver config loading from `code_analysis.database.driver`
- [x] Test startup when no driver config is found
- [x] Test error handling during startup
- [x] Test worker manager error handling
- [x] Test startup sequence logic
- [x] Test config path fallback
- [x] **Coverage: 7 unit tests, all passing**

### Integration Tests with Real Server
- [ ] **Test server startup with real running server** (can be done in Step 15)
- [ ] Test driver startup sequence with real server (can be done in Step 15)
- [ ] Test startup order (driver → workers → server) (can be done in Step 15)
- [ ] Test shutdown sequence with real server (can be done in Step 15)
- [ ] Test error handling during startup (covered by unit tests)
- [ ] Test error handling during shutdown (covered by unit tests)

**Note**: Full integration tests with real server are planned for Step 15 (Unified Testing Pipeline).
Unit tests verify the core logic and integration with WorkerManager.

## Deliverables

- ✅ Driver config loaded from config file (`get_driver_config()` function)
- ✅ Database driver starts before other workers (startup sequence implemented)
- ✅ Startup sequence is correct (driver → vectorization → file_watcher → server)
- ✅ Shutdown handling works (signal handlers, atexit, FastAPI events)
- ✅ **Test coverage**: Unit tests implemented (`tests/test_main_process_integration.py` - 7 tests, all passing)
- ⚠️ **Integration tests with real server**: Planned for Step 15 (Unified Testing Pipeline)

## Next Steps

- [Step 8: Object Models](./STEP_08_OBJECT_MODELS.md)
- [Step 9: High-Level Client API](./STEP_09_CLIENT_API.md)
- [Step 10: AST/CST Tree Operations](./STEP_10_AST_CST_OPERATIONS.md)
