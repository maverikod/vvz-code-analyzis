# Step 13: Testing and Validation

**Priority**: Finalization  
**Dependencies**: All previous steps  
**Estimated Time**: 2-3 weeks

## Goal

Comprehensive testing of new architecture with 90%+ test coverage and real data/server tests.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing test code using `code_mapper` indexes
- [ ] Review existing test patterns in `tests/` directory
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
- [ ] Note: Test files are excluded from code_mapper error checking

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

### 13.1 Unit Tests (90%+ Coverage Required)
- [ ] Test RPC server/client
- [ ] Test Result object
- [ ] Test object models
- [ ] Test client API methods
- [ ] Test AST/CST operations
- [ ] Test request queue
- [ ] Test driver operations
- [ ] **Verify 90%+ coverage for all modules**

### 13.2 Integration Tests with Real Data
- [ ] **Test all components with real data from test_data/**
- [ ] Test end-to-end workflows with real projects
- [ ] Test worker integration with real data
- [ ] Test command integration with real data
- [ ] Test all operations on real files from test_data
- [ ] Test all operations on real projects (vast_srv, bhlff)
- [ ] Verify all functionality works with real data

**Real Data Test Requirements**:
- [ ] Use actual projects from `test_data/` directory
- [ ] Use actual files from test_data projects
- [ ] Use actual database with real data
- [ ] Test all features on real codebases
- [ ] Verify results match expected behavior

### 13.3 Integration Tests with Real Server
- [ ] **Test all components with real running server**
- [ ] Test server startup and shutdown
- [ ] Test driver process with real server
- [ ] Test all RPC operations through real server
- [ ] Test all commands through real server
- [ ] Test all workers through real server
- [ ] Test error scenarios with real server
- [ ] Test concurrent operations with real server

**Real Server Test Requirements**:
- [ ] Start actual server process
- [ ] Test all features through real server
- [ ] Test all error scenarios
- [ ] Test performance with real server
- [ ] Test all project features

### 13.4 Performance Tests
- [ ] Test RPC latency
- [ ] Test throughput
- [ ] Test on real data from test_data
- [ ] Test with real server
- [ ] Optimize if needed

### 13.5 Regression Tests
- [ ] Run all existing tests
- [ ] Fix any issues
- [ ] Ensure all functionality works correctly
- [ ] **Verify 90%+ coverage maintained**

## Files to Create

- `tests/test_rpc_server.py`
- `tests/test_rpc_client.py`
- `tests/test_database_client.py`
- `tests/test_ast_cst_operations.py`
- `tests/integration/test_database_driver.py`
- `tests/integration/test_workers.py`
- `tests/integration/test_commands.py`
- `tests/performance/test_rpc_performance.py`

## Deliverables

- ✅ **Test coverage 90%+ for all modules**
- ✅ All unit tests pass
- ✅ **All integration tests pass on real data from test_data/**
- ✅ **All integration tests pass with real running server**
- ✅ Performance is acceptable
- ✅ No regressions
- ✅ Comprehensive test suite complete

## Next Steps

After completing this step, proceed to:
- [Step 14: Cleanup](./STEP_14_CLEANUP.md)
- [Step 15: Unified Testing Pipeline](./STEP_15_TESTING_PIPELINE.md)
