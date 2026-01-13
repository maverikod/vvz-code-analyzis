# Step 15: Unified Testing Pipeline

**Priority**: Finalization  
**Dependencies**: Step 13 (Testing and Validation)  
**Estimated Time**: 1 week

## Goal

Create unified testing pipeline that tests all server features with real data and real running server.

## Overview

This step creates a comprehensive testing pipeline that:
- Tests all server features
- Uses real data from `test_data/` directory
- Tests with real running server
- Covers all project-specific features
- Ensures 90%+ test coverage

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing test pipeline code using `code_mapper` indexes
- [ ] Review existing test infrastructure in `tests/` directory
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

### 15.1 Create Test Pipeline Infrastructure
- [ ] Create test pipeline script
- [ ] Create test configuration
- [ ] Create test data setup utilities
- [ ] Create server startup/shutdown utilities
- [ ] Create test reporting system

**Files to Create**:
- `tests/pipeline/test_pipeline.py` - Main pipeline script
- `tests/pipeline/config.py` - Pipeline configuration
- `tests/pipeline/server_manager.py` - Server management utilities
- `tests/pipeline/test_data_setup.py` - Test data setup utilities
- `tests/pipeline/reporting.py` - Test reporting

### 15.2 Test Data Setup
- [ ] Setup test database with real data from test_data
- [ ] Load real projects (vast_srv, bhlff, etc.)
- [ ] Load real files from test_data
- [ ] Setup test environment
- [ ] Verify test data is available

**Test Data Requirements**:
- [ ] Use projects from `test_data/` directory
- [ ] Use actual Python files from test_data
- [ ] Use actual database with real schema
- [ ] Verify all test_data projects are available

### 15.3 Server Startup Tests
- [ ] Test server startup with real config
- [ ] Test driver process startup
- [ ] Test worker startup
- [ ] Test server initialization
- [ ] Verify all components start correctly

### 15.4 Database Operations Tests
- [ ] Test all table operations on real data
- [ ] Test Project operations on real projects
- [ ] Test File operations on real files
- [ ] Test Attribute operations on real AST/CST
- [ ] Test Code Structure operations on real code
- [ ] Test Analysis operations on real data

### 15.5 AST/CST Operations Tests
- [ ] Test AST queries on real files
- [ ] Test CST queries on real files
- [ ] Test AST modify operations on real files
- [ ] Test CST modify operations on real files
- [ ] Test XPath filters on real code patterns
- [ ] Verify all operations work correctly

### 15.6 Command Tests
- [ ] Test all MCP commands through real server
- [ ] Test command execution on real data
- [ ] Test command responses
- [ ] Test error handling in commands
- [ ] Verify all commands work correctly

### 15.7 Worker Tests
- [ ] Test vectorization worker with real server
- [ ] Test file watcher worker with real server
- [ ] Test worker operations on real data
- [ ] Test worker error handling
- [ ] Verify all workers work correctly

### 15.8 Performance Tests
- [ ] Test RPC latency with real server
- [ ] Test throughput with real server
- [ ] Test performance on real data
- [ ] Benchmark all operations
- [ ] Verify performance is acceptable

### 15.9 Error Scenario Tests
- [ ] Test connection failures
- [ ] Test driver process crashes
- [ ] Test worker failures
- [ ] Test database errors
- [ ] Test invalid requests
- [ ] Verify error handling works correctly

### 15.10 Concurrent Operations Tests
- [ ] Test concurrent requests
- [ ] Test concurrent commands
- [ ] Test concurrent worker operations
- [ ] Test race conditions
- [ ] Verify thread safety

### 15.11 End-to-End Workflow Tests
- [ ] Test complete workflows with real server
- [ ] Test project analysis workflow
- [ ] Test file update workflow
- [ ] Test vectorization workflow
- [ ] Test file watching workflow
- [ ] Verify all workflows work correctly

### 15.12 Coverage Verification
- [ ] Run coverage analysis
- [ ] Verify 90%+ coverage for all modules
- [ ] Identify uncovered code
- [ ] Add tests for uncovered code
- [ ] Verify coverage requirements met

### 15.13 Test Reporting
- [ ] Generate test reports
- [ ] Generate coverage reports
- [ ] Generate performance reports
- [ ] Document test results
- [ ] Create test summary

## Files to Create

- `tests/pipeline/__init__.py`
- `tests/pipeline/test_pipeline.py` - Main pipeline script
- `tests/pipeline/config.py` - Pipeline configuration
- `tests/pipeline/server_manager.py` - Server management
- `tests/pipeline/test_data_setup.py` - Test data setup
- `tests/pipeline/reporting.py` - Test reporting
- `tests/pipeline/conftest.py` - Pytest fixtures for pipeline

## Pipeline Structure

```python
def run_test_pipeline():
    """Run unified test pipeline."""
    # 1. Setup test data
    setup_test_data()
    
    # 2. Start server
    server = start_test_server()
    
    try:
        # 3. Test database operations
        test_database_operations()
        
        # 4. Test AST/CST operations
        test_ast_cst_operations()
        
        # 5. Test commands
        test_commands()
        
        # 6. Test workers
        test_workers()
        
        # 7. Test performance
        test_performance()
        
        # 8. Test error scenarios
        test_error_scenarios()
        
        # 9. Test concurrent operations
        test_concurrent_operations()
        
        # 10. Test end-to-end workflows
        test_end_to_end_workflows()
        
    finally:
        # 11. Stop server
        stop_test_server(server)
        
    # 12. Generate reports
    generate_reports()
```

## Deliverables

- ✅ Unified test pipeline implemented
- ✅ All tests run on real data from test_data
- ✅ All tests run with real running server
- ✅ **Test coverage 90%+ for all modules**
- ✅ All project features tested
- ✅ Test reports generated
- ✅ Performance benchmarks created

## Success Criteria

- ✅ Pipeline runs all tests successfully
- ✅ **90%+ test coverage achieved**
- ✅ All tests pass on real data
- ✅ All tests pass with real server
- ✅ All project features work correctly
- ✅ Performance is acceptable
- ✅ Error handling works correctly

## Usage

```bash
# Run full test pipeline
pytest tests/pipeline/test_pipeline.py -v

# Run with coverage
pytest tests/pipeline/test_pipeline.py --cov=code_analysis --cov-report=html

# Run specific test suite
pytest tests/pipeline/test_pipeline.py::test_database_operations -v
```

## Test Data Projects

Pipeline must test with all available projects in `test_data/`:
- `test_data/vast_srv/` - Real project with real Python files
- `test_data/bhlff/` - Real project with real Python files
- `test_data/code_analysis/` - Real project (if exists)
- Any other projects in test_data directory

**Requirements**:
- Each project must have `projectid` file
- Each project must contain real Python files
- Test all operations on these real projects
- Verify all features work with real code

## Server Testing Requirements

**All server tests must use real running server**:
- Start actual server process using `python -m code_analysis.main --daemon`
- Test all features through real server
- Test all MCP commands through real server
- Test all workers through real server
- Test error scenarios with real server
- Test performance with real server

## Next Steps

This is the final step. After completing this step, the implementation is complete.
