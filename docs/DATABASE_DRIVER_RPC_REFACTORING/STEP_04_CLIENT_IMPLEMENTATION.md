# Step 4: Client Implementation

**Priority**: 3 (High)  
**Dependencies**: Step 3 (Driver Process Implementation)  
**Estimated Time**: 2-3 weeks

## Goal

Implement client library that communicates with driver process via RPC and provides object-oriented API.

## Implementation Status

**Status**: ❌ **NOT IMPLEMENTED** (0%)

### Current State:
- ❌ **New client library**: `code_analysis/core/database_client/` - **NOT EXISTS**
- ✅ **Old database access**: `code_analysis/core/database/base.py` (CodeDatabase class) - **STILL IN USE**

### Missing Components:
- `code_analysis/core/database_client/` - **ENTIRE PACKAGE DOES NOT EXIST**
- All files listed in "Files to Create" section - **NONE EXIST**

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing client code using `code_mapper` indexes
- [ ] Review existing database client implementations if any
- [ ] Check for existing RPC client code
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

## Overview

Client library:
- Communicates with driver process via RPC
- Provides object-oriented API (Project, File, Attributes)
- Converts objects to table operations
- Handles RPC communication, errors, retries

## Checklist

### 3.1 Create Client Package Structure
- [ ] Create `code_analysis/core/database_client/` directory
- [ ] Create `__init__.py`
- [ ] Create package structure

**Files to Create**:
- `code_analysis/core/database_client/__init__.py`
- `code_analysis/core/database_client/client.py`
- `code_analysis/core/database_client/rpc_client.py`
- `code_analysis/core/database_client/exceptions.py`

### 3.2 Implement RPC Client
- [ ] Create RPC client class
- [ ] Implement connection to driver process
- [ ] Implement request sending
- [ ] Implement response receiving
- [ ] Implement connection pooling
- [ ] Implement retry logic
- [ ] Implement error handling

**Files to Create**:
- `code_analysis/core/database_client/rpc_client.py`

**RPC Client Features**:
- [ ] Unix socket connection
- [ ] Request serialization
- [ ] Response deserialization
- [ ] Connection pooling
- [ ] Retry logic
- [ ] Error handling
- [ ] Timeout handling

### 3.3 Implement Database Client Base
- [ ] Create `DatabaseClient` class
- [ ] Initialize RPC client connection
- [ ] Implement connection management
- [ ] Implement health check methods
- [ ] Implement low-level RPC method wrappers

**Files to Create**:
- `code_analysis/core/database_client/client.py`

**Base Client Methods**:
- [ ] `connect() -> None`
- [ ] `disconnect() -> None`
- [ ] `is_connected() -> bool`
- [ ] `health_check() -> bool`
- [ ] Low-level RPC method wrappers

### 3.4 Implement Result Object
- [ ] Create `Result` object class
- [ ] Implement result validation
- [ ] Implement error handling

**Files to Create**:
- `code_analysis/core/database_client/result.py`

**Result Object**:
- [ ] `code: int` - Return code (0 = success, non-zero = error)
- [ ] `description: Optional[str]` - Error description (required if code != 0)
- [ ] `data: Optional[Any]` - Result data (optional, depends on operation)

### 3.5 Testing
- [ ] Test RPC client connection
- [ ] Test all RPC method calls
- [ ] Test error handling
- [ ] Test retry logic
- [ ] Test connection pooling

**Files to Create**:
- `tests/test_database_client.py`
- `tests/test_rpc_client.py`

## Deliverables

- ✅ RPC client implemented
- ✅ DatabaseClient base class implemented
- ✅ Result object implemented
- ✅ Connection management works
- ✅ Error handling works
- ✅ All tests pass

## Files to Create

- `code_analysis/core/database_client/__init__.py`
- `code_analysis/core/database_client/client.py`
- `code_analysis/core/database_client/rpc_client.py`
- `code_analysis/core/database_client/result.py`
- `code_analysis/core/database_client/exceptions.py`
- `tests/test_database_client.py`
- `tests/test_rpc_client.py`

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] RPC client methods
- [ ] DatabaseClient base methods
- [ ] Result object
- [ ] Connection management
- [ ] Error handling
- [ ] **Coverage: 90%+ for all modules**

### Integration Tests with Real Data
- [ ] **Test client with real database from test_data projects**
- [ ] Test all client methods on real data
- [ ] Test object-to-table mapping with real data
- [ ] Test RPC communication with real driver process
- [ ] Test all operations on real projects and files

**Real Data Test Requirements**:
- [ ] Use actual database with data from test_data projects
- [ ] Test client operations on real projects (vast_srv, bhlff, etc.)
- [ ] Test client operations on real files from test_data
- [ ] Verify object-to-table conversion works correctly

### Integration Tests with Real Server
- [ ] **Test client with real running server**
- [ ] Test RPC communication through real server
- [ ] Test all client methods through real server
- [ ] Test connection pooling with real server
- [ ] Test retry logic with real server

### Error Tests
- [ ] Connection failures, RPC errors, timeouts
- [ ] Driver process unavailable scenarios
- [ ] Invalid response handling
- [ ] Network errors

### Performance Tests
- [ ] Connection pooling performance
- [ ] Concurrent requests performance
- [ ] RPC latency measurements

## Success Criteria

- ✅ **Test coverage 90%+ for all client modules**
- ✅ RPC client connects to driver process
- ✅ **All tests pass on real data from test_data/**
- ✅ **All tests pass with real running server**
- ✅ All RPC methods work through client
- ✅ Error handling works correctly
- ✅ Retry logic works
- ✅ Connection pooling works
- ✅ Performance is acceptable

## Key Points

- **Object-oriented API**: Client provides high-level API (will be extended in later steps)
- **RPC communication**: All communication goes through RPC client
- **Error handling**: Robust error handling and retry logic
- **Connection management**: Connection pooling and health checks

## Next Steps

After completing this step, proceed to:
- [Step 5: Configuration Structure](./STEP_05_CONFIGURATION.md)
- [Step 8: Object Models](./STEP_08_OBJECT_MODELS.md) (for object-oriented API)
