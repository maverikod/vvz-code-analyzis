# Step 9: High-Level Client API

**Priority**: API Development  
**Dependencies**: Step 4 (Client Implementation), Step 8 (Object Models)  
**Estimated Time**: 2-3 weeks

## Goal

Implement object-oriented API methods in DatabaseClient.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing client API code using `code_mapper` indexes
- [ ] Review existing database client implementations
- [ ] Check for similar API patterns
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] Verify no duplicate code was introduced
- [ ] Check file sizes (must be < 400 lines)
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

### 9.1 Project Operations
- [ ] `create_project(project: Project) -> Project`
- [ ] `get_project(project_id: str) -> Project`
- [ ] `update_project(project: Project) -> Project`
- [ ] `delete_project(project_id: str) -> bool`
- [ ] `list_projects() -> list[Project]`

### 9.2 File Operations
- [ ] `create_file(file: File) -> File`
- [ ] `get_file(file_id: int) -> File`
- [ ] `update_file(file: File) -> File`
- [ ] `delete_file(file_id: int) -> bool`
- [ ] `get_project_files(project_id: str) -> list[File]`

### 9.3 Attribute Operations
- [ ] `save_ast(file_id: int, ast_data: dict) -> bool`
- [ ] `get_ast(file_id: int) -> dict`
- [ ] `save_cst(file_id: int, cst_code: str) -> bool`
- [ ] `get_cst(file_id: int) -> str`
- [ ] `save_vectors(file_id: int, vectors: list[dict]) -> bool`
- [ ] `get_vectors(file_id: int) -> list[dict]`

### 9.4 Code Structure Operations
- [ ] Methods for classes, functions, methods, imports
- [ ] Search and query methods
- [ ] Relationship navigation methods

### 9.5 Analysis Operations
- [ ] Methods for issues, usages, duplicates
- [ ] Query and search methods
- [ ] Statistics methods

## Files to Modify

- `code_analysis/core/database_client/client.py` - Add high-level API methods

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] All high-level API methods
- [ ] Object-to-table conversion
- [ ] Error handling
- [ ] **Coverage: 90%+ for all API methods**

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
