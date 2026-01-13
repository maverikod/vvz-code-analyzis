# Step 7: Main Process Integration

**Priority**: Integration  
**Dependencies**: Step 5 (Configuration), Step 6 (WorkerManager Integration)  
**Estimated Time**: 1 week

## Goal

Integrate database driver startup into main process.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing main process code using `code_mapper` indexes
- [ ] Review existing `code_analysis/main.py` startup sequence
- [ ] Check for existing worker startup patterns
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

- [ ] Load driver config from `code_analysis.database.driver`
- [ ] Create `startup_database_driver()` function
- [ ] Update startup sequence (driver starts BEFORE other workers)
- [ ] Add shutdown handling
- [ ] Test server startup with new sequence
- [ ] Test driver startup on server start
- [ ] Test shutdown sequence

## Files to Modify

- `code_analysis/main.py` - Add driver startup and shutdown

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Integration Tests with Real Server
- [ ] **Test server startup with real running server**
- [ ] Test driver startup sequence with real server
- [ ] Test startup order (driver → workers → server)
- [ ] Test shutdown sequence with real server
- [ ] Test error handling during startup
- [ ] Test error handling during shutdown

**Real Server Test Requirements**:
- [ ] Start actual server process
- [ ] Verify driver starts before workers
- [ ] Verify all workers start correctly
- [ ] Verify server starts correctly
- [ ] Test graceful shutdown
- [ ] Test error recovery

## Deliverables

- ✅ Driver config loaded from config file
- ✅ Database driver starts before other workers
- ✅ Startup sequence is correct
- ✅ Shutdown handling works
- ✅ **Test coverage 90%+**
- ✅ **All tests pass with real running server**

## Next Steps

- [Step 11: Commands Implementation](./STEP_11_COMMANDS.md)
- [Step 12: Workers Implementation](./STEP_12_WORKERS.md)
