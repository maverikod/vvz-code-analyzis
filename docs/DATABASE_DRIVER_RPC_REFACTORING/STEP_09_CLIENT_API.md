# Step 9: High-Level Client API

**Priority**: API Development  
**Dependencies**: Step 4 (Client Implementation), Step 8 (Object Models)  
**Estimated Time**: 2-3 weeks

## Goal

Implement object-oriented API methods in DatabaseClient.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [x] **ALWAYS run code_mapper** to check if functionality already exists in project ✅
- [x] Search existing client API code using `code_mapper` indexes ✅
- [x] Review existing database client implementations ✅
- [x] Check for similar API patterns ✅
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

### 9.1 Project Operations
- [x] `create_project(project: Project) -> Project` ✅
- [x] `get_project(project_id: str) -> Project` ✅
- [x] `update_project(project: Project) -> Project` ✅
- [x] `delete_project(project_id: str) -> bool` ✅
- [x] `list_projects() -> list[Project]` ✅

### 9.2 File Operations
- [x] `create_file(file: File) -> File` ✅
- [x] `get_file(file_id: int) -> File` ✅
- [x] `update_file(file: File) -> File` ✅
- [x] `delete_file(file_id: int) -> bool` ✅
- [x] `get_project_files(project_id: str) -> list[File]` ✅

### 9.3 Attribute Operations
- [x] `save_ast(file_id: int, ast_data: dict) -> bool` ✅
- [x] `get_ast(file_id: int) -> dict` ✅
- [x] `save_cst(file_id: int, cst_code: str) -> bool` ✅
- [x] `get_cst(file_id: int) -> str` ✅
- [x] `save_vectors(file_id: int, vectors: list[dict]) -> bool` ✅
- [x] `get_vectors(file_id: int) -> list[dict]` ✅

### 9.4 Code Structure Operations
- [ ] Methods for classes, functions, methods, imports
- [ ] Search and query methods
- [ ] Relationship navigation methods

### 9.5 Analysis Operations
- [ ] Methods for issues, usages, duplicates
- [ ] Query and search methods
- [ ] Statistics methods

## Files Created/Modified

- `code_analysis/core/database_client/client_api_projects.py` - Project operations mixin ✅
- `code_analysis/core/database_client/client_api_files.py` - File operations mixin ✅
- `code_analysis/core/database_client/client_api_attributes.py` - Attribute operations mixin ✅
- `code_analysis/core/database_client/client.py` - Integrated API mixins ✅
- `tests/test_client_api.py` - Unit tests for API methods ✅

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [x] All high-level API methods ✅
- [x] Object-to-table conversion ✅
- [x] Error handling ✅
- [ ] **Coverage: 90%+ for all API methods** (tests created, coverage to be verified)

### Integration Tests with Real Data
- [ ] **Test all API methods with real data from test_data/**
- [ ] Test Project operations on real projects
- [ ] Test File operations on real files
- [ ] Test Attribute operations on real AST/CST data
- [ ] Test Code Structure operations on real code
- [ ] Test Analysis operations on real data

### Integration Tests with Real Server
- [ ] **Test all API methods through real running server**
- [ ] Test RPC communication through real server
- [ ] Test all operations end-to-end through real server

## Deliverables

- ✅ All high-level API methods implemented
- ✅ Methods use object models
- ✅ Methods call RPC through client
- ✅ **Test coverage 90%+**
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**

## Next Steps

- [Step 10: AST/CST Tree Operations](./STEP_10_AST_CST_OPERATIONS.md)
