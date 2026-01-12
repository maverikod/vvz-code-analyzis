# Analysis: CST Compose Module Command - Error Analysis

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-12

## Executive Summary

This document analyzes errors discovered during testing of `compose_cst_module` command with `project_id` parameter support.

## Issues Discovered

### Issue 1: Changes Not Applied Despite Success Response

**Problem**: 
- Command returns `success: true` and `applied: true`
- `stats` shows `replaced: 1`
- But file content remains unchanged
- `diff` is empty string
- `source` in response shows old code, not new code

**Location**: `code_analysis/commands/cst_compose_module_command.py`

**Symptoms**:
1. Command execution returns success
2. File on disk contains old code
3. `return_source=true` shows old code in response
4. `return_diff=true` returns empty diff

**Root Cause Analysis**:
- **Path confusion**: Multiple path variables (`abs_path`, `abs_path_for_db`, `abs_path_for_add`) were used for the same file
- `target` was already resolved at line 237, but then `rel_path` was computed and absolute path was rebuilt as `(root_path / rel_path).resolve()`
- This could result in different paths being used for file operations vs database operations
- If `target` was not within `root_path`, `rel_path` became absolute, and `(root_path / rel_path)` could produce incorrect paths

**Status**: ✅ FIXED
- Simplified path logic: use `target.resolve()` directly as `abs_path`
- Removed redundant `rel_path` computation and path rebuilding
- Use single `abs_path` variable consistently for all database operations

### Issue 2: Empty Diff When Changes Applied

**Problem**:
- `stats` shows `replaced: 1` (changes detected)
- But `diff` is empty string
- This suggests `unified_diff(old_source, new_source, ...)` returns empty

**Possible Causes**:
1. `old_source` and `new_source` are actually the same (CST operations didn't modify code)
2. `unified_diff` function has a bug
3. File content is different from `new_source` used for diff calculation

### Issue 3: File ID Variable Scope Issue

**Problem**:
- `file_id` variable used in line 567 but only defined inside `if not file_record:` block
- If file exists in database, `file_id` is undefined
- Fixed by initializing `file_id = None` before block and setting it in both branches

**Status**: ✅ FIXED

### Issue 4: Project ID Support Missing in CST Commands

**Problem**:
- CST commands (`compose_cst_module`, `list_cst_blocks`, `query_cst`) only accepted `root_dir`
- Should accept `project_id` and resolve `root_dir` from database
- All file paths should be relative to project root

**Status**: ✅ FIXED
- Added `_resolve_project_root()` helper method to `BaseMCPCommand`
- Updated all CST commands to support `project_id` parameter
- Updated schemas to make `root_dir` optional when `project_id` provided

### Issue 5: Path Resolution Issues

**Problem**:
- `normalize_path_simple()` resolves relative paths from CWD, not from project root
- This causes "File not within project root" errors
- Need to use absolute paths resolved from project root
- Multiple path variables created confusion (`abs_path`, `abs_path_for_db`, `abs_path_for_add`)

**Status**: ✅ FIXED
- Simplified to use `target.resolve()` directly (target is already resolved at line 237)
- Use single `abs_path` variable consistently for all operations
- Removed redundant path rebuilding from `rel_path`

### Issue 6: Database Transaction Visibility

**Problem**:
- `get_file_by_path()` called inside transaction doesn't see changes from `add_file()`
- SQLite should see uncommitted changes, but `get_file_by_path` may use different connection

**Status**: ✅ FIXED
- Added `file_id` parameter to `update_file_data_atomic()`
- Use `get_file_by_id()` after `add_file()` to get record within transaction
- Pass `file_id` directly to `update_file_data_atomic()` to avoid path lookup issues

## Testing Results

### Test Case: Create new file with `project_id`

**Command**:
```python
compose_cst_module(
    project_id='feb9e4d6-0747-4746-818a-fbc404d03f46',
    file_path='server.py',
    ops=[{
        'operation_type': 'create',
        'selector': {'kind': 'module'},
        'file_docstring': '...',
        'new_code': '...'
    }],
    apply=True
)
```

**Result**:
- ✅ File created successfully
- ✅ Database updated
- ✅ Command returns success
- ❌ But subsequent edits don't apply (Issue 1)

### Test Case: Edit existing file with `project_id`

**Command**:
```python
compose_cst_module(
    project_id='feb9e4d6-0747-4746-818a-fbc404d03f46',
    file_path='server.py',
    ops=[{
        'selector': {'kind': 'range', 'start_line': 136, 'end_line': 149},
        'new_code': '...'
    }],
    apply=True
)
```

**Result**:
- ✅ Command returns success
- ✅ `stats` shows `replaced: 1`
- ❌ File content unchanged
- ❌ `diff` is empty
- ❌ `source` shows old code

## Recommendations

1. **Investigate Issue 1**: Why changes don't apply despite success
   - Add logging to track file write operations
   - Verify `new_source` contains expected changes
   - Check if file is overwritten after move
   - Verify `unified_diff` calculation

2. **Fix diff calculation**: Why diff is empty when changes are detected
   - Check `unified_diff()` function implementation
   - Verify `old_source` and `new_source` are different
   - Add logging to diff calculation

3. **Add integration tests**: Test full flow with `project_id` parameter
   - Test file creation
   - Test file modification
   - Test file deletion
   - Verify file content matches expected

4. **Improve error reporting**: When changes don't apply, report clearly
   - Check file content after operation
   - Compare expected vs actual content
   - Report mismatch as error

## Next Steps

1. Debug why `new_source` doesn't match file content after move
2. Fix `unified_diff` to show actual changes
3. Add validation that file content matches `new_source` after operation
4. Add comprehensive tests for `project_id` parameter support
