# Step 11: Commands Implementation

**Priority**: Implementation  
**Dependencies**: Step 4 (Client Implementation), Step 8 (Object Models), Step 9 (Client API), Step 10 (AST/CST Operations)  
**Estimated Time**: 3-4 weeks

## Goal

Implement MCP commands using DatabaseClient.

## Implementation Status

**Status**: ❌ **NOT IMPLEMENTED** (0%)

### Current State:
- ✅ **Commands exist**: All commands in `code_analysis/commands/`
- ✅ **BaseMCPCommand exists**: `code_analysis/commands/base_mcp_command.py`
- ❌ **Uses old CodeDatabase**: All commands still use `CodeDatabase` class (old architecture)

### Missing Components:
- Replacement of `CodeDatabase` with `DatabaseClient` in BaseMCPCommand
- Update all commands to use new DatabaseClient API
- Remove all references to old CodeDatabase

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
- [ ] Implement `BaseMCPCommand._open_database()` using `DatabaseClient`
- [ ] Remove all references to old `CodeDatabase`
- [ ] Use new `DatabaseClient` API for all database operations

### 11.2 Implement Individual Commands
- [ ] Implement each command using `DatabaseClient`
- [ ] Use new object-oriented API
- [ ] Test each command after implementation

**Commands to Implement**:
- All commands in `code_analysis/commands/` directory
- Priority: Most used commands first

### 11.3 Implement AST/CST Commands
- [ ] Implement commands that use AST/CST operations
- [ ] Use new AST/CST API with XPath filters
- [ ] Use Result objects for responses

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
