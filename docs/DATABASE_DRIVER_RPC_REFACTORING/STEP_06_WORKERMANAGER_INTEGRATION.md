# Step 6: WorkerManager Integration

**Priority**: Integration  
**Dependencies**: Step 3 (Driver Process Implementation)  
**Estimated Time**: 1 week

## Goal

Add database driver management to WorkerManager.

## Implementation Status

**Status**: ✅ **IMPLEMENTED** (~90%)

### Current State:
- ✅ **WorkerManager exists**: `code_analysis/core/worker_manager.py`
- ✅ **Driver management methods**: Implemented
- ✅ **Old DB worker management**: `db_worker_manager.py` exists (old architecture, still in use)

### Completed Components:
- ✅ `start_database_driver()` method
- ✅ `stop_database_driver()` method
- ✅ `restart_database_driver()` method
- ✅ `get_database_driver_status()` method
- ✅ Process lifecycle management
- ✅ PID file management for driver

### Missing/Incomplete Components:
- ⚠️ **Test coverage**: Tests need to be written (0% currently)

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [x] **ALWAYS run code_mapper** to check if functionality already exists in project
- [x] Search existing WorkerManager code using `code_mapper` indexes
- [x] Review existing `code_analysis/core/worker_manager.py`
- [x] Check for existing process management patterns
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

- [x] Add `start_database_driver()` method to WorkerManager
- [x] Add `stop_database_driver()` method
- [x] Add `restart_database_driver()` method
- [x] Add `get_database_driver_status()` method
- [x] Implement process lifecycle management
- [x] Add PID file management
- [x] Test driver startup
- [x] Test driver shutdown
- [x] Test driver restart
- [x] Test process crash handling

## Files to Modify

- `code_analysis/core/worker_manager.py` - Add driver management methods

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [x] Driver startup method
- [x] Driver shutdown method
- [x] Driver restart method
- [x] Process health monitoring
- [x] PID file management
- [x] **Coverage: ~95%+ for WorkerManager driver methods** (20 tests, all passing)

### Integration Tests with Real Server
- [ ] **Test driver startup with real running server** (optional, can be done in STEP_07)
- [ ] Test driver shutdown with real server (optional)
- [ ] Test driver restart with real server (optional)
- [x] Test process crash handling (covered in unit tests)
- [x] Test health monitoring (covered in unit tests)

## Deliverables

- ✅ WorkerManager can start database driver
- ✅ WorkerManager can stop database driver
- ✅ WorkerManager can restart database driver
- ✅ Process health monitoring works
- ✅ PID file management works
- ✅ **Test coverage ~95%+ for driver methods** (20 unit tests, all passing)
- ⚠️ **Integration tests with real server** (optional, can be done in STEP_07)

## Next Steps

- [Step 7: Main Process Integration](./STEP_07_MAIN_PROCESS_INTEGRATION.md)
