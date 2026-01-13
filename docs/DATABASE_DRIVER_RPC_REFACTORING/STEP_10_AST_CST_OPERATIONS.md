# Step 10: AST/CST Tree Operations

**Priority**: API Development  
**Dependencies**: Step 1 (Query Language Testing), Step 4 (Client Implementation), Step 8 (Object Models), Step 9 (Client API)  
**Estimated Time**: 2-3 weeks

## Goal

Implement AST/CST tree operations with XPath filters and Result objects.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing AST/CST operations using `code_mapper` indexes
- [ ] Review existing `code_analysis/core/cst_tree/` implementations
- [ ] Check for existing tree modification code
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

### 10.1 XPath Filter Object
- [ ] Create `XPathFilter` class
- [ ] Integrate with CSTQuery engine (from Step 1)
- [ ] Support selector syntax and additional filters

### 10.2 Tree Action Types
- [ ] Create `TreeAction` enum (REPLACE, DELETE, INSERT)
- [ ] Define action parameters

### 10.3 AST Query Operations
- [ ] `query_ast(file_id: int, filter: XPathFilter) -> Result[list[ASTNode]]`
- [ ] Implement AST tree loading from database
- [ ] Implement XPath filtering on AST
- [ ] Return Result object with nodes

### 10.4 CST Query Operations
- [ ] `query_cst(file_id: int, filter: XPathFilter) -> Result[list[CSTNode]]`
- [ ] Implement CST tree loading from database
- [ ] Implement XPath filtering using CSTQuery engine
- [ ] Return Result object with nodes

### 10.5 AST Modify Operations
- [ ] `modify_ast(file_id: int, filter: XPathFilter, action: TreeAction, nodes: list[ASTNode]) -> Result[ASTTree]`
- [ ] Implement node replacement
- [ ] Implement node deletion
- [ ] Implement node insertion
- [ ] Return Result object with modified tree

### 10.6 CST Modify Operations
- [ ] `modify_cst(file_id: int, filter: XPathFilter, action: TreeAction, nodes: list[CSTNode]) -> Result[CSTTree]`
- [ ] Integrate with existing `tree_modifier.py` functionality
- [ ] Implement node replacement
- [ ] Implement node deletion
- [ ] Implement node insertion
- [ ] Return Result object with modified tree

### 10.7 RPC Methods in Driver
- [ ] Implement AST query handler in RPC server
- [ ] Implement CST query handler in RPC server
- [ ] Implement AST modify handler in RPC server
- [ ] Implement CST modify handler in RPC server

## Files to Create

- `code_analysis/core/database_client/objects/xpath_filter.py`
- `code_analysis/core/database_client/objects/tree_action.py`

## Files to Modify

- `code_analysis/core/database_client/client.py` - Add AST/CST methods
- `code_analysis/core/database_driver_pkg/rpc_server.py` - Add AST/CST handlers

## Deliverables

- ✅ XPathFilter object implemented
- ✅ TreeAction enum created
- ✅ AST query operations work
- ✅ CST query operations work
- ✅ AST modify operations work
- ✅ CST modify operations work
- ✅ All operations return Result object correctly

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] XPathFilter object
- [ ] TreeAction enum
- [ ] Result object
- [ ] AST query operations
- [ ] CST query operations
- [ ] AST modify operations
- [ ] CST modify operations
- [ ] **Coverage: 90%+ for all AST/CST operations**

### Integration Tests with Real Data
- [ ] **Test AST/CST operations on real files from test_data/**
- [ ] Test AST queries on real Python files (vast_srv, bhlff)
- [ ] Test CST queries on real Python files
- [ ] Test AST modify operations on real files
- [ ] Test CST modify operations on real files
- [ ] Test XPath filters on real code patterns
- [ ] Test complex queries on real codebases
- [ ] Verify operations work correctly with real code

**Real Data Test Requirements**:
- [ ] Use actual Python files from test_data projects
- [ ] Test queries that match real code patterns
- [ ] Test modify operations on real code
- [ ] Verify Result objects for all operations
- [ ] Test atomicity on real files

### Integration Tests with Real Server
- [ ] **Test AST/CST operations through real running server**
- [ ] Test queries through real server
- [ ] Test modify operations through real server
- [ ] Test error handling through real server

## Success Criteria

- ✅ **Test coverage 90%+ for all AST/CST operations**
- ✅ All operations work correctly
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**
- ✅ Result objects work correctly
- ✅ Atomicity is maintained

## Next Steps

- [Step 11: Commands Implementation](./STEP_11_COMMANDS.md)
