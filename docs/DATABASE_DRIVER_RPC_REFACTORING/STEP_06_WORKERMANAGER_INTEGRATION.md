# Step 6: WorkerManager Integration

**Priority**: Integration  
**Dependencies**: Step 3 (Driver Process Implementation)  
**Estimated Time**: 1 week

## Goal

Add database driver management to WorkerManager.

## Implementation Status

**Status**: ❌ **NOT IMPLEMENTED** (0%)

### Current State:
- ✅ **WorkerManager exists**: `code_analysis/core/worker_manager.py`
- ❌ **Driver management methods**: Not implemented
- ✅ **Old DB worker management**: `db_worker_manager.py` exists (old architecture, still in use)

### Missing Components:
- `start_database_driver()` method
- `stop_database_driver()` method
- `restart_database_driver()` method
- `get_database_driver_status()` method
- Process lifecycle management
- PID file management for driver

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing WorkerManager code using `code_mapper` indexes
- [ ] Review existing `code_analysis/core/worker_manager.py`
- [ ] Check for existing process management patterns
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

- [ ] Add `start_database_driver()` method to WorkerManager
- [ ] Add `stop_database_driver()` method
- [ ] Add `restart_database_driver()` method
- [ ] Add `get_database_driver_status()` method
- [ ] Implement process lifecycle management
- [ ] Add PID file management
- [ ] Test driver startup
- [ ] Test driver shutdown
- [ ] Test driver restart
- [ ] Test process crash handling

## Files to Modify

- `code_analysis/core/worker_manager.py` - Add driver management methods

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] Driver startup method
- [ ] Driver shutdown method
- [ ] Driver restart method
- [ ] Process health monitoring
- [ ] PID file management
- [ ] **Coverage: 90%+ for WorkerManager driver methods**

### Integration Tests with Real Server
- [ ] **Test driver startup with real running server**
- [ ] Test driver shutdown with real server
- [ ] Test driver restart with real server
- [ ] Test process crash handling with real server
- [ ] Test health monitoring with real server

## Deliverables

- ✅ WorkerManager can start database driver
- ✅ WorkerManager can stop database driver
- ✅ WorkerManager can restart database driver
- ✅ Process health monitoring works
- ✅ PID file management works
- ✅ **Test coverage 90%+**
- ✅ **All tests pass with real running server**

## Next Steps

- [Step 7: Main Process Integration](./STEP_07_MAIN_PROCESS_INTEGRATION.md)
