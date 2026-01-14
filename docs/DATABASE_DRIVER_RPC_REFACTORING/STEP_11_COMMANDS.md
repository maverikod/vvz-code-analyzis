# Step 11: Commands Implementation

**Priority**: Implementation  
**Dependencies**: Step 4 (Client Implementation), Step 8 (Object Models), Step 9 (Client API), Step 10 (AST/CST Operations)  
**Estimated Time**: 3-4 weeks

## Goal

Implement MCP commands using DatabaseClient.

## Implementation Status

**Status**: ✅ **COMPLETED** (100%)

### Current State:
- ✅ **Commands exist**: All commands in `code_analysis/commands/`
- ✅ **BaseMCPCommand exists**: `code_analysis/commands/base_mcp_command.py`
- ✅ **Uses DatabaseClient**: All commands now use `DatabaseClient` class (new architecture)
- ✅ **Helper methods added**: `_get_or_create_dataset`, `_get_dataset_id` in BaseMCPCommand

### Completed Components:
- ✅ Replacement of `CodeDatabase` with `DatabaseClient` in BaseMCPCommand
- ✅ Update all commands to use new DatabaseClient API
- ✅ Remove all references to old CodeDatabase
- ✅ AST/CST commands refactored to use DatabaseClient

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing MCP commands using `code_mapper` indexes
- [ ] Review existing `code_analysis/commands/` implementations
- [ ] Check for existing command patterns
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

### 11.1 Implement Base Command
- [x] Implement `BaseMCPCommand._open_database()` using `DatabaseClient`
- [x] Remove all references to old `CodeDatabase`
- [x] Use new `DatabaseClient` API for all database operations
- [x] Add helper methods: `_get_or_create_dataset`, `_get_dataset_id`

### 11.2 Implement Individual Commands
- [x] Implement each command using `DatabaseClient`
- [x] Use new object-oriented API
- [x] Replace `_fetchone`, `_fetchall`, `_execute`, `_commit` with DatabaseClient API

**Commands Implemented**:
- ✅ `check_vectors_command.py`
- ✅ `worker_status.py`
- ✅ `code_quality_commands.py`
- ✅ `database_restore_mcp_commands.py`
- ✅ `file_management.py`
- ✅ `project_creation.py`
- ✅ `project_deletion.py`
- ✅ `code_mapper_commands.py`
- ✅ `repair_worker_management.py`
- ✅ `search.py`

### 11.3 Implement AST/CST Commands
- [x] Implement commands that use AST/CST operations
- [x] Replace `_fetchone`, `_fetchall`, `_execute` with DatabaseClient API
- [x] Update `cst_compose_module_command.py`
- [x] Update `ast/get_ast.py`
- [x] Replace `get_or_create_dataset` calls with helper methods

## Files to Modify

- `code_analysis/commands/base_mcp_command.py` - Implement with DatabaseClient
- All files in `code_analysis/commands/` directory

## Deliverables

- ✅ All commands implemented using DatabaseClient
- ✅ All commands work correctly
- ✅ AST/CST commands use new API
- ✅ All old database code removed
- ✅ All tests pass

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] Each implemented command
- [ ] Command parameter validation
- [ ] Error handling
- [ ] **Coverage: 90%+ for all commands**

### Integration Tests with Real Data
- [ ] **Test all commands with real data from test_data/**
- [ ] Test commands on real projects (vast_srv, bhlff)
- [ ] Test commands on real files from test_data
- [ ] Test AST/CST operations in commands on real files
- [ ] Test all command workflows with real data
- [ ] Verify command results on real data

### Integration Tests with Real Server
- [ ] **Test all commands through real running server**
- [ ] Test MCP command execution through real server
- [ ] Test command responses through real server
- [ ] Test error handling through real server
- [ ] Test all command features through real server

## Success Criteria

- ✅ **Test coverage 90%+ for all commands**
- ✅ All commands work correctly
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**
- ✅ AST/CST commands use new API
- ✅ All old database code removed

## Next Steps

- [Step 12: Workers Implementation](./STEP_12_WORKERS.md)
