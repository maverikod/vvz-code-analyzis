# Database Driver RPC Refactoring - Implementation Guide

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-13

## 🚨 CRITICAL: New Project Implementation

**⚠️ THIS IS A NEW PROJECT - NO MIGRATION, NO BACKWARD COMPATIBILITY, NO FALLBACKS ⚠️**

- ❌ **NO migration** from old code
- ❌ **NO backward compatibility** with old architecture
- ❌ **NO fallback mechanisms** to old code
- ✅ **NEW implementation** from scratch
- ✅ **Complete removal** of old code (`CodeDatabase`, `SQLiteDriverProxy`, `DBWorkerManager`)
- ✅ **Clean break** - old architecture is completely replaced

## Implementation Priorities

### Priority 1: Query Language Testing and Production Readiness
- Test and refine CSTQuery language
- Ensure query language is production-ready
- Document query language features

**See**: [Step 1: Query Language Testing](./STEP_01_QUERY_LANGUAGE_TESTING.md)

### Priority 2: Driver Process Implementation
- Implement driver process with database and request queue
- Driver works in terms of database tables (not objects)
- Request queue management in driver process

**See**: [Step 3: Driver Process Implementation](./STEP_03_DRIVER_PROCESS.md)

### Priority 3: Client Implementation
- Implement client library
- Object-oriented API on client side
- RPC communication with driver

**See**: [Step 4: Client Implementation](./STEP_04_CLIENT_IMPLEMENTATION.md)

## Implementation Steps

### Phase 1: Foundation
1. [Step 1: Query Language Testing](./STEP_01_QUERY_LANGUAGE_TESTING.md) - **PRIORITY 1**
2. [Step 2: RPC Infrastructure](./STEP_02_RPC_INFRASTRUCTURE.md) - **⚠️ CRITICAL: Must be done BEFORE Step 3**
3. [Step 3: Driver Process Implementation](./STEP_03_DRIVER_PROCESS.md) - **PRIORITY 2** (Requires Step 2)
4. [Step 4: Client Implementation](./STEP_04_CLIENT_IMPLEMENTATION.md) - **PRIORITY 3**

### Phase 2: Integration
5. [Step 5: Configuration Structure](./STEP_05_CONFIGURATION.md)
6. [Step 6: WorkerManager Integration](./STEP_06_WORKERMANAGER_INTEGRATION.md)
7. [Step 7: Main Process Integration](./STEP_07_MAIN_PROCESS_INTEGRATION.md)

### Phase 3: Object Models and API
8. [Step 8: Object Models](./STEP_08_OBJECT_MODELS.md)
9. [Step 9: High-Level Client API](./STEP_09_CLIENT_API.md)
10. [Step 10: AST/CST Tree Operations](./STEP_10_AST_CST_OPERATIONS.md)

### Phase 4: Commands and Workers
11. [Step 11: Commands Implementation](./STEP_11_COMMANDS.md)
12. [Step 12: Workers Implementation](./STEP_12_WORKERS.md)

### Phase 5: Finalization
13. [Step 13: Testing and Validation](./STEP_13_TESTING.md)
14. [Step 14: Cleanup](./STEP_14_CLEANUP.md)
15. [Step 15: Unified Testing Pipeline](./STEP_15_TESTING_PIPELINE.md) - **CRITICAL: Tests all features with real server**

## Reference Documents

- [Technical Specification](../DATABASE_DRIVER_RPC_REFACTORING.md) - Complete technical specification
- [Original Plan](../DATABASE_DRIVER_RPC_REFACTORING_PLAN.md) - Original implementation plan (reference)
- [Driver Development Standard](./DRIVER_DEVELOPMENT_STANDARD.md) - **Standard for developing new database drivers (MySQL, PostgreSQL, etc.)**
- [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) - **Current implementation status and comparison with requirements**

## ⚠️ Implementation Status

**Current Status**: The new RPC-based architecture has **NOT been implemented yet**. The project still uses the old architecture with `CodeDatabase`, `SQLiteDriverProxy`, and `DBWorkerManager`.

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison between planned steps and current codebase state.

### Key Findings:
- ✅ **Step 1 (CSTQuery)**: Partially complete (60%) - CSTQuery exists but XPathFilter object missing
- ❌ **Step 2-15**: Not implemented (0%) - All new components are missing
- ⚠️ **Critical Path**: Step 2 (RPC Infrastructure) must be completed BEFORE Step 3

## Quick Start

### Recommended Order (by Critical Path)

**⚠️ IMPORTANT**: Step 5 (RPC Infrastructure) is a CRITICAL dependency for Step 2 and must be completed FIRST.

1. **🔴 Step 2: RPC Infrastructure** - **CRITICAL: Do this FIRST**
   - Create BaseRequest and BaseResult classes
   - Define RPC protocol
   - Create serialization utilities
   - **Required before Step 3**

2. **🟠 Step 1: Query Language Testing** - Priority 1
   - Test and refine CSTQuery language
   - Complete XPathFilter object
   - Ensure production readiness
   - **Can be done in parallel with Step 2**

3. **🟡 Step 3: Driver Process Implementation** - Priority 2
   - Implement driver process with database and request queue
   - Driver works in terms of tables (not objects)
   - **Requires Step 2 to be complete**

4. **🟢 Step 4: Client Implementation** - Priority 3
   - Implement client library
   - Object-oriented API
   - **Requires Step 3 to be complete**

5. **Step 5: Configuration Structure**
   - Can be done in parallel with Step 2/3
   - Update config schema
   - Add validation

### Then Continue With

6. Integration (Steps 6-7)
7. Object Models and API (Steps 8-10)
8. Commands and Workers (Steps 11-12)
9. Testing and Cleanup (Steps 13-15)

## Step Structure

Each step file contains:
- ✅ **Code Mapper requirements** - **⚠️ CRITICAL: Must use code_mapper utility**
  - Before writing code: Check existing functionality
  - During implementation: Update indexes after each block of changes
  - After writing code: Eliminate ALL errors found by code_mapper
- ✅ **Detailed checklist** - All tasks with checkboxes
- ✅ **Files to create/modify** - Complete file list
- ✅ **Deliverables** - What must be completed
- ✅ **Testing requirements** - What to test
  - **⚠️ 90%+ test coverage required for all modules**
  - **⚠️ Tests on real data from test_data/ required**
  - **⚠️ Tests with real running server required (where applicable)**
- ✅ **Dependencies** - What must be done first
- ✅ **Success criteria** - How to know step is complete
- ✅ **Next steps** - What to do after

## Code Mapper Requirements (All Steps)

**⚠️ CRITICAL: Must use code_mapper utility throughout ALL steps**

### Before Writing Code
- **ALWAYS run code_mapper** to check if functionality already exists in project
- Search existing code using `code_mapper` indexes in `code_analysis/` directory
- Review existing implementations before creating new code
- Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- **Run code_mapper after each block of changes** to update indexes
- Use command: `code_mapper -r code_analysis/` to update indexes
- Keep indexes up-to-date for other developers and tools

### After Writing Code (Production Code Only, Not Tests)
- **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- Fix all code quality issues detected by code_mapper
- Verify no duplicate code was introduced
- Check file sizes (must be < 400 lines)
- **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

**See each step file for specific code_mapper requirements.**

## Testing Requirements (All Steps)

**⚠️ CRITICAL TESTING REQUIREMENTS:**

1. **Test Coverage: 90%+** for all modules in each step
2. **Real Data Tests**: All tests must use real data from `test_data/` directory
   - Use actual projects: `test_data/vast_srv/`, `test_data/bhlff/`, etc.
   - Use actual Python files from test_data
   - Use actual database with real data
3. **Real Server Tests**: Where server is created, tests must use real running server
   - Start actual server process
   - Test all features through real server
   - Test error scenarios with real server
4. **Unified Pipeline**: Step 15 creates unified testing pipeline for all features

## Key Architecture Principles

### Driver Process (Priority 2)
- **Works with tables**: All operations are table-level (insert, update, delete, select)
- **Request queue**: Queue is managed inside driver process
- **No object models**: Driver doesn't know about Project, File, etc. - only tables
- **RPC server**: Driver exposes RPC server for client communication

### Client (Priority 3)
- **Object-oriented API**: Client provides high-level API (Project, File, Attributes)
- **RPC communication**: All communication goes through RPC client
- **Object-to-table mapping**: Client converts objects to table operations

### Query Language (Priority 1)
- **CSTQuery engine**: XPath-like selectors for AST/CST trees
- **Production-ready**: Fully tested and documented before use
- **XPathFilter object**: Wrapper for CSTQuery selectors

## Testing Requirements Summary

**⚠️ CRITICAL: All Steps Must Meet These Requirements**

### Test Coverage
- **90%+ test coverage required** for all modules in each step
- Coverage must be verified before step completion
- Use `pytest --cov` to verify coverage

### Real Data Testing
- **All tests must use real data from `test_data/` directory**
- Use actual projects: `test_data/vast_srv/`, `test_data/bhlff/`, etc.
- Use actual Python files from test_data
- Use actual database with real data
- Verify all operations work correctly with real code

### Real Server Testing
- **Where server is created, tests must use real running server**
- Start actual server process: `python -m code_analysis.main --daemon`
- Test all features through real server
- Test all MCP commands through real server
- Test all workers through real server
- Test error scenarios with real server

### Unified Testing Pipeline
- **Step 15** creates unified testing pipeline
- Tests all features with real data and real server
- Comprehensive test coverage verification
- Performance benchmarking
- End-to-end workflow testing
