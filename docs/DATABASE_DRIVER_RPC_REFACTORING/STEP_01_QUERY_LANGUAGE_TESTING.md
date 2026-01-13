# Step 1: Query Language Testing and Production Readiness

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

**Priority**: 1 (Highest)  
**Dependencies**: None  
**Estimated Time**: 1-2 weeks

## Implementation Status

**Status**: ✅ **COMPLETE** (100%)

### Current State:
- ✅ **CSTQuery exists**: `code_analysis/cst_query/` package is fully implemented
  - `parser.py` - Lark parser for selector grammar ✅
  - `executor.py` - Query executor ✅
  - `ast.py` - AST models ✅
- ✅ **Used in commands**: `query_cst_command.py` uses CSTQuery
- ✅ **Used in tree operations**: `cst_tree/tree_finder.py` uses CSTQuery
- ✅ **XPathFilter object**: `code_analysis/core/database_client/objects/xpath_filter.py` - **EXISTS**
- ✅ **Comprehensive tests**: Test coverage 92%+ (exceeds 90% requirement)
- ✅ **Performance benchmarks**: `tests/performance/test_cst_query_performance.py` - **EXISTS**

### Completed Components:
- ✅ `code_analysis/core/database_client/objects/xpath_filter.py` - Implemented
- ✅ `tests/test_xpath_filter.py` - All tests passing (11 tests)
- ✅ `tests/test_cst_query_parser.py` - All tests passing
- ✅ `tests/test_cst_query_executor.py` - All tests passing
- ✅ `tests/test_cst_query_integration.py` - All tests passing (with real data)
- ✅ `tests/test_cst_query_special_chars.py` - All tests passing
- ✅ `tests/performance/test_cst_query_performance.py` - All tests passing (6 tests)

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Goal

Test and refine CSTQuery language to ensure it's production-ready before implementing driver and client.

## Overview

CSTQuery is a jQuery/XPath-like selector language for locating Python CST nodes. This step ensures the query language is fully tested, documented, and ready for production use in AST/CST operations.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [x] **ALWAYS run code_mapper** to check if functionality already exists in project ✅
- [x] Search existing code using `code_mapper` indexes in `code_analysis/` directory ✅
- [x] Review existing implementations before creating new code ✅
- [x] Use `code_mapper` to find related code and understand project structure ✅
- [x] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data) ✅

### During Code Implementation
- [x] **Run code_mapper after each block of changes** to update indexes ✅
- [x] Use command: `code_mapper -r code_analysis/` to update indexes ✅
- [x] Keep indexes up-to-date for other developers and tools ✅

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

**Commands**:
```bash
# Check existing functionality (excludes tests and test_data)
code_mapper -r code_analysis/

# Update indexes after changes (excludes tests and test_data)
code_mapper -r code_analysis/
```

## Checklist

### 1.1 Review Existing CSTQuery Implementation
- [x] Review `code_analysis/cst_query/` package structure
- [x] Review parser implementation (`parser.py`)
- [x] Review executor implementation (`executor.py`)
- [x] Review AST definitions (`ast.py`)
- [x] Identify any gaps or issues

**Files to Review**:
- `code_analysis/cst_query/parser.py` ✅
- `code_analysis/cst_query/executor.py` ✅
- `code_analysis/cst_query/ast.py` ✅
- `code_analysis/cst_query/__init__.py` ✅
- `docs/CST_QUERY.md` ✅

### 1.2 Create Comprehensive Test Suite
- [x] Create unit tests for parser
- [x] Create unit tests for executor
- [x] Create integration tests for query operations
- [x] Test all selector syntax features
- [x] Test edge cases and error handling

**Files to Create**:
- `tests/test_cst_query_parser.py` ✅
- `tests/test_cst_query_executor.py` ✅
- `tests/test_cst_query_integration.py` ✅
- `tests/test_cst_query_special_chars.py` ✅

**Test Coverage**:
- [x] All selector types (TYPE, *)
- [x] All combinators (descendant, child)
- [x] All predicates (attr=value, attr!=value, attr~=value, attr^=value, attr$=value)
- [x] All pseudos (:first, :last, :nth(N))
- [x] Complex queries
- [x] Error cases (invalid syntax, missing nodes)

**Coverage Result**: 92%+ (exceeds 90% requirement)

### 1.3 Test XPath Filter Integration
- [x] Test XPathFilter object creation
- [x] Test selector string parsing
- [x] Test integration with CSTQuery engine
- [x] Test filter application to AST/CST trees

**Files to Create**:
- `tests/test_xpath_filter.py` ✅ (11 tests, all passing)
- `code_analysis/core/database_client/objects/xpath_filter.py` ✅

### 1.4 Performance Testing
- [x] Test query performance on large files
- [x] Test query performance on large codebases
- [x] Identify performance bottlenecks
- [x] Optimize if needed

**Files to Create**:
- `tests/performance/test_cst_query_performance.py` ✅ (6 tests, all passing)

**Performance Results**: All queries complete within acceptable time limits (< 100ms for typical queries)

### 1.5 Documentation
- [x] Update CSTQuery documentation
- [x] Document all selector syntax
- [x] Create query examples
- [x] Document best practices
- [x] Document performance considerations

**Files to Update**:
- `docs/CST_QUERY.md` ✅ (updated with XPathFilter and performance info)

### 1.6 Production Readiness Checklist
- [x] All tests pass (84 passed, 1 skipped)
- [x] Performance is acceptable (< 100ms for typical queries)
- [x] Documentation is complete
- [x] Error handling is robust
- [x] Edge cases are handled
- [x] Query language is stable

## Deliverables

- ✅ Comprehensive test suite for CSTQuery
- ✅ XPathFilter object implemented and tested
- ✅ Performance benchmarks
- ✅ Complete documentation
- ✅ Production-ready query language

## Files to Create

- `tests/test_cst_query_parser.py`
- `tests/test_cst_query_executor.py`
- `tests/test_cst_query_integration.py`
- `tests/test_xpath_filter.py`
- `tests/performance/test_cst_query_performance.py`
- `code_analysis/core/database_client/objects/xpath_filter.py` (if needed)

## Files to Modify

- `docs/CST_QUERY.md` - Update documentation

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [x] All parser and executor functions ✅
- [x] All selector syntax features ✅
- [x] Error handling and edge cases ✅
- [x] **Coverage: 90%+ for all modules** ✅ (92%+ achieved)

### Integration Tests with Real Data
- [x] **Test on real projects from `test_data/` directory** ✅
- [x] Test queries on `test_data/vast_srv/` project ✅
- [x] Test queries on `test_data/bhlff/` project ✅
- [x] Test queries on `test_data/code_analysis/` project (if exists) ✅
- [x] Test all query types on real Python files ✅
- [x] Test complex queries on real codebases ✅
- [x] Test performance on large real files ✅

**Real Data Test Requirements**:
- [x] Use actual Python files from test_data projects ✅
- [x] Test queries that match real code patterns ✅
- [x] Test queries on files with various structures (classes, functions, methods) ✅
- [x] Test queries on files with imports, decorators, etc. ✅
- [x] Verify query results match expected nodes in real code ✅

### Performance Tests
- [x] Query performance on large files from test_data ✅
- [x] Query performance on large codebases from test_data ✅
- [x] Benchmark queries on real projects ✅
- [x] Performance is acceptable (< 100ms for typical queries) ✅

### Error Tests
- [x] Invalid queries, missing nodes, edge cases ✅
- [x] Error handling on malformed selectors ✅
- [x] Error handling on non-existent nodes ✅

## Success Criteria

- ✅ **Test coverage 90%+ for all CSTQuery modules**
- ✅ All selector syntax features tested
- ✅ **All tests pass on real data from test_data/**
- ✅ Performance is acceptable (< 100ms for typical queries)
- ✅ Documentation is complete and accurate
- ✅ Query language is production-ready

## Next Steps

After completing this step, proceed to:
- [Step 2: RPC Infrastructure](./STEP_02_RPC_INFRASTRUCTURE.md) - **CRITICAL: Must be done before Step 3**
- [Step 3: Driver Process Implementation](./STEP_03_DRIVER_PROCESS.md) - Requires Step 2
