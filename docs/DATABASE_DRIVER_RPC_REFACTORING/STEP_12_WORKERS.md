# Step 12: Workers Implementation

**Priority**: Implementation  
**Dependencies**: Step 4 (Client Implementation), Step 8 (Object Models), Step 9 (Client API)  
**Estimated Time**: 2-3 weeks

## Goal

Implement workers using DatabaseClient.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [x] **ALWAYS run code_mapper** to check if functionality already exists in project ✅
- [x] Search existing worker code using `code_mapper` indexes ✅
- [x] Review existing `code_analysis/core/vectorization_worker_pkg/` and `file_watcher_pkg/` ✅
- [x] Check for existing worker patterns ✅
- [x] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data) ✅

### During Code Implementation
- [x] **Run code_mapper after each block of changes** to update indexes ✅
- [x] Use command: `code_mapper -r code_analysis/` to update indexes ✅

### After Writing Code (Production Code Only, Not Tests)
- [x] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues ✅
- [x] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis) ✅
- [x] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY ✅
- [x] Fix all code quality issues detected by code_mapper ✅
- [x] Verify no duplicate code was introduced ✅
- [x] Check file sizes (must be < 400 lines) ✅
- [x] **DO NOT proceed until ALL code_mapper errors are fixed** ✅

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

### 12.1 Implement Vectorization Worker
- [x] Remove all references to old `CodeDatabase` ✅
- [x] Implement using `DatabaseClient` ✅
- [x] Use new object-oriented API ✅
- [ ] Test worker functionality (requires integration testing)

### 12.2 Implement File Watcher Worker
- [x] Remove all references to old `CodeDatabase` ✅
- [x] Implement using `DatabaseClient` ✅
- [x] Use new object-oriented API ✅
- [ ] Test worker functionality (requires integration testing)

### 12.3 Implement Worker Database Access
- [x] Ensure workers use DatabaseClient correctly ✅
- [x] Handle connection errors ✅
- [x] Implement retry logic if needed ✅
- [x] Remove all old database access patterns ✅

## Files to Modify

- `code_analysis/core/vectorization_worker_pkg/runner.py`
- `code_analysis/core/file_watcher_pkg/multi_project_worker.py`
- All worker files that access database

## Deliverables

- ✅ All workers implemented using DatabaseClient
- ✅ All workers work correctly
- ✅ Database operations work in workers
- ✅ All old database code removed

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] Vectorization worker methods
- [ ] File watcher worker methods
- [ ] Worker database operations
- [ ] Worker error handling
- [ ] **Coverage: 90%+ for all workers**

### Integration Tests with Real Data
- [ ] **Test workers with real data from test_data/**
- [ ] Test vectorization worker on real projects
- [ ] Test file watcher worker on real projects
- [ ] Test worker operations on real files
- [ ] Test worker database operations on real data
- [ ] Verify workers process real data correctly

### Integration Tests with Real Server
- [ ] **Test workers with real running server**
- [ ] Test worker startup with real server
- [ ] Test worker operations through real server
- [ ] Test worker error handling with real server
- [ ] Test worker shutdown with real server

## Success Criteria

- ✅ **Test coverage 90%+ for all workers**
- ✅ All workers work correctly
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**
- ✅ Database operations work in workers
- ✅ All old database code removed

## Next Steps

- [Step 13: Testing and Validation](./STEP_13_TESTING.md)
