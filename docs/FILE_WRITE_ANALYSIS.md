# File Write Analysis: All Code File Writing Methods

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-27

## Executive Summary

This document analyzes **ALL** methods that write Python code files to disk in the project (excluding test files). The goal is to identify where files are written and ensure that database records are properly updated after each write operation.

**Related Documents**:
- `docs/AST_UPDATE_ANALYSIS.md` - Detailed analysis of AST update mechanism

**Key Finding**: ❌ **Most file write operations do NOT update database records**. Only `update_indexes` command updates database, but it's not called after file writes.

**Critical Issues**:
1. ❌ AST trees become stale after file writes (see `AST_UPDATE_ANALYSIS.md`)
2. ❌ CST trees are not cleared when files are updated
3. ❌ File watcher only marks files for chunking, doesn't update AST/CST
4. ❌ All code entity records (classes, functions, methods) become outdated

## 1. All File Write Operations

### 1.1 CST Module Editing (`compose_cst_module`)

**Location**: `code_analysis/commands/cst_compose_module_command.py`

**Method**: `write_with_backup()` (line 436)

```435:438:code_analysis/commands/cst_compose_module_command.py
            if apply:
                backup_path = write_with_backup(
                    target, new_source, create_backup=create_backup
                )
```

**What it does**:
- Writes modified code to disk using `write_with_backup()`
- Creates backup if `create_backup=True`
- Creates git commit if `commit_message` provided

**Database updates**: ❌ **NONE**
- Does NOT clear old database records
- Does NOT call `update_indexes`
- Does NOT update AST tree (see `AST_UPDATE_ANALYSIS.md` for details)
- Does NOT update CST tree in database
- Does NOT update code entities (classes, functions, methods)

**Impact**: 
- Database becomes stale after CST editing
- AST queries return outdated data
- Vectorization may fail on stale AST references
- Code entity information becomes incorrect

### 1.2 File Splitter (`split_file_to_package`)

**Location**: `code_analysis/core/refactorer_pkg/file_splitter.py`

**Methods**:
- `init_file.write_text()` (line 60) - Creates `__init__.py`
- `module_path.write_text()` (line 73) - Creates new module files

```58:74:code_analysis/core/refactorer_pkg/file_splitter.py
            init_file = package_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text(
                    '"""Package created by split_file_to_package."""\n'
                )

            # Split code into modules
            source_lines = self.source.splitlines(keepends=True)
            created_modules = []

            for module_name, module_config in modules.items():
                module_path = package_dir / f"{module_name}.py"
                module_content = self._build_module_content(
                    module_name, module_config, source_lines
                )
                module_path.write_text(module_content)
                created_modules.append(module_name)
```

**What it does**:
- Splits a large file into a package with multiple modules
- Creates `__init__.py` and new module files
- Original file may be deleted or modified

**Database updates**: ❌ **NONE**
- Does NOT update database for new files
- Does NOT clear old file records
- Does NOT call `update_indexes`

**Impact**: New files are not indexed, old file records remain.

### 1.3 Class Splitter (`split_class`)

**Location**: `code_analysis/core/refactorer_pkg/splitter.py`

**Method**: `f.write(new_content)` (line 181)

```179:181:code_analysis/core/refactorer_pkg/splitter.py
            new_content = self._perform_split(src_class, config)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
```

**What it does**:
- Splits a class into multiple classes
- Writes modified file content to disk
- Formats code with black

**Database updates**: ❌ **NONE**
- Does NOT clear old database records
- Does NOT call `update_indexes`
- Does NOT update AST tree

**Impact**: Database records reflect old class structure.

### 1.4 Superclass Extractor (`extract_superclass`)

**Location**: `code_analysis/core/refactorer_pkg/extractor.py`

**Method**: `f.write(new_content)` (line 407)

```405:407:code_analysis/core/refactorer_pkg/extractor.py
            new_content = self._perform_extraction(config, child_nodes)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
```

**What it does**:
- Extracts common functionality into base class
- Writes modified file content to disk
- Formats code with black

**Database updates**: ❌ **NONE**
- Does NOT clear old database records
- Does NOT call `update_indexes`
- Does NOT update AST tree

**Impact**: Database records reflect old class structure.

### 1.5 Code Formatter (`format_code_with_black`)

**Location**: `code_analysis/core/code_quality/formatter.py`

**Method**: `f.write(formatted_content)` (line 55)

```53:55:code_analysis/core/code_quality/formatter.py
        # Write formatted content back
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(formatted_content)
```

**What it does**:
- Formats Python code using black
- Writes formatted content back to file
- Only changes formatting, not structure

**Database updates**: ❌ **NONE**
- Does NOT update database
- Does NOT call `update_indexes`

**Impact**: Database records may have outdated formatting, but structure should be same.

**Note**: Formatting changes don't affect AST structure, but `file_mtime` changes, so database should be updated.

### 1.6 File Restoration (`repair_database`)

**Location**: `code_analysis/commands/file_management.py`

**Method**: `target_path.write_text(cst_code, encoding="utf-8")` (line 648)

```646:648:code_analysis/commands/file_management.py
            # Restore file content
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(cst_code, encoding="utf-8")
```

**What it does**:
- Restores file from CST (source code stored in database)
- Writes file to disk (project directory or version directory)

**Database updates**: ❌ **NONE**
- Does NOT update database after restoration
- Does NOT call `update_indexes`

**Impact**: Restored file is not indexed in database.

### 1.7 Write with Backup Utility

**Location**: `code_analysis/core/cst_module/utils.py`

**Method**: `target_file.write_text(new_source, encoding="utf-8")` (line 98)

```85:99:code_analysis/core/cst_module/utils.py
def write_with_backup(
    target_file: Path, new_source: str, create_backup: bool = True
) -> Optional[Path]:
    if create_backup and target_file.exists():
        backup_dir = target_file.parent / ".code_mapper_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{target_file.name}.backup"
        backup_path.write_text(
            target_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        backup_path = None

    target_file.write_text(new_source, encoding="utf-8")
    return backup_path
```

**What it does**:
- Creates backup of original file
- Writes new content to file

**Database updates**: ❌ **NONE** (utility function, no database access)

**Used by**: `compose_cst_module` command

## 2. Database Records That Need Clearing

### 2.1 Current `clear_file_data` Method

**Location**: `code_analysis/core/database/files.py`

**What it clears**:
- ✅ Classes and methods
- ✅ Functions
- ✅ Imports
- ✅ Issues
- ✅ Usages
- ✅ Dependencies
- ✅ Code content and FTS index
- ✅ AST trees
- ❌ **CST trees** - **NOT CLEARED**

**Missing**: CST trees are not cleared in `clear_file_data`.

### 2.2 Required Database Operations

When a file is written, we need to:

1. **Clear all old records** (as per `clear_file_data` + CST trees):
   - Classes and methods
   - Functions
   - Imports
   - Issues
   - Usages
   - Dependencies
   - Code content and FTS
   - **AST trees** (already cleared in `clear_file_data`)
   - **CST trees** (NOT cleared - needs fix)
   - Code chunks
   - Vector index entries
   - Comprehensive analysis results

2. **Recreate all records** (via `update_indexes`):
   - Parse file content
   - Parse AST tree
   - Extract classes, functions, methods, imports
   - Save AST tree to database
   - Save CST tree (source code) to database
   - Update file metadata (lines, mtime, has_docstring)
   - Extract code entities for indexing

**Note**: `update_indexes` command (`_analyze_file` method) already does all of this correctly. We just need to call it after file writes.

## 3. File Watcher Behavior

**Location**: `code_analysis/core/file_watcher_pkg/processor.py`

**Current behavior**:
- ✅ Detects file changes (compares `mtime` with `last_modified`)
- ✅ Marks file for chunking (`mark_file_needs_chunking`)
- ✅ Updates `last_modified` timestamp
- ❌ **Does NOT clear old database records**
- ❌ **Does NOT call `update_indexes`**

**What it should do** (as per `AST_UPDATE_ANALYSIS.md` recommendations):
1. Detect file change (compares `mtime` with `last_modified`)
2. Clear all old database records for file (including CST trees)
3. Call `update_indexes` to recreate all records:
   - Parse AST
   - Save AST tree
   - Save CST tree
   - Extract code entities
4. Mark file for chunking (vectorization worker will process)

**Current Gap**: File watcher only does step 4 (mark for chunking), missing steps 2-3.

## 4. Required Solution

### 4.1 Create Unified File Update Method

**New method**: `update_file_data(file_path, project_id, root_dir)`

**Location**: `code_analysis/core/database/files.py` or new module

**What it does** (unified update mechanism as per `AST_UPDATE_ANALYSIS.md`):
1. Get file_id from database by path
2. Clear all old records (including CST trees - fix `clear_file_data`)
3. Call `update_indexes` for the file (uses existing `_analyze_file` method)
4. Return success/failure

**This ensures**:
- ✅ File metadata is updated
- ✅ AST tree is updated (solves AST staleness issue)
- ✅ CST tree is updated
- ✅ Code entities (classes, functions, methods) are updated
- ✅ All related records are consistent

**Signature**:
```python
def update_file_data(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
) -> Dict[str, Any]:
    """
    Update all database records for a file after it was written.
    
    This is the unified update mechanism that ensures consistency across
    all data structures (AST, CST, code entities, chunks).
    
    Process:
    1. Find file_id by path
    2. Clear all old records (including CST trees)
    3. Call update_indexes to recreate all records:
       - Parse AST
       - Save AST tree
       - Save CST tree
       - Extract code entities
    4. Return result
    
    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory
        
    Returns:
        Dictionary with update result:
        {
            "success": bool,
            "file_id": int,
            "file_path": str,
            "ast_updated": bool,
            "cst_updated": bool,
            "entities_updated": int,
            "error": Optional[str]
        }
    """
```

### 4.2 Fix `clear_file_data` to Include CST Trees

**Current**: Does NOT clear CST trees

**Fix**: Add CST tree deletion:
```python
self._execute("DELETE FROM cst_trees WHERE file_id = ?", (file_id,))
```

### 4.3 Integration Points

**1. File Watcher** (`code_analysis/core/file_watcher_pkg/processor.py`):
- After detecting file change
- Call `update_file_data()` instead of just `mark_file_needs_chunking()`

**2. CST Compose** (`code_analysis/commands/cst_compose_module_command.py`):
- After successful file write (line 436)
- Call `update_file_data()` before returning

**3. File Splitter** (`code_analysis/core/refactorer_pkg/file_splitter.py`):
- After creating new files
- Call `update_indexes` for all new files

**4. Class Splitter** (`code_analysis/core/refactorer_pkg/splitter.py`):
- After writing modified file
- Call `update_file_data()`

**5. Superclass Extractor** (`code_analysis/core/refactorer_pkg/extractor.py`):
- After writing modified file
- Call `update_file_data()`

**6. Code Formatter** (`code_analysis/core/code_quality/formatter.py`):
- After formatting file
- Call `update_file_data()` (optional - formatting doesn't change structure)

**7. File Restoration** (`code_analysis/commands/file_management.py`):
- After restoring file
- Call `update_file_data()`

## 5. Summary Table

| Operation | Location | Write Method | Database Update | Status |
|-----------|----------|--------------|-----------------|--------|
| CST Compose | `cst_compose_module_command.py` | `write_with_backup()` | ❌ None | **NEEDS FIX** |
| File Splitter | `file_splitter.py` | `write_text()` | ❌ None | **NEEDS FIX** |
| Class Splitter | `splitter.py` | `f.write()` | ❌ None | **NEEDS FIX** |
| Superclass Extractor | `extractor.py` | `f.write()` | ❌ None | **NEEDS FIX** |
| Code Formatter | `formatter.py` | `f.write()` | ❌ None | **NEEDS FIX** |
| File Restoration | `file_management.py` | `write_text()` | ❌ None | **NEEDS FIX** |
| File Watcher | `processor.py` | N/A (detects changes) | ⚠️ Partial | **NEEDS FIX** |
| Update Indexes | `code_mapper_mcp_command.py` | N/A (reads files) | ✅ Full | **OK** |

## 6. Implementation Plan

### Step 1: Fix `clear_file_data`
- Add CST tree deletion
- Test that all records are cleared

### Step 2: Create `update_file_data` Method
- Implement unified update method
- Use `update_indexes` internally
- Handle errors gracefully

### Step 3: Integrate into File Watcher
- Replace `mark_file_needs_chunking` with `update_file_data`
- Test file change detection and update

### Step 4: Integrate into All Write Operations
- Add `update_file_data` call after each file write
- Test each operation

### Step 5: Testing
- Test all file write operations
- Verify database is updated correctly
- Verify no stale records remain

## 7. Code References

### Write Operations
- `code_analysis/commands/cst_compose_module_command.py:436` - CST compose
- `code_analysis/core/refactorer_pkg/file_splitter.py:60,73` - File splitter
- `code_analysis/core/refactorer_pkg/splitter.py:181` - Class splitter
- `code_analysis/core/refactorer_pkg/extractor.py:407` - Superclass extractor
- `code_analysis/core/code_quality/formatter.py:55` - Code formatter
- `code_analysis/commands/file_management.py:648` - File restoration
- `code_analysis/core/cst_module/utils.py:98` - Write utility

### Database Operations
- `code_analysis/core/database/files.py:199` - `clear_file_data` (needs CST fix)
- `code_analysis/core/database/cst.py:41` - `save_cst_tree`
- `code_analysis/commands/code_mapper_mcp_command.py:127` - `_analyze_file` (update_indexes)

### File Watcher
- `code_analysis/core/file_watcher_pkg/processor.py:504` - `_queue_file_for_processing`

## 8. Relationship to AST Update Analysis

This document complements `docs/AST_UPDATE_ANALYSIS.md`:

- **AST_UPDATE_ANALYSIS.md** focuses on:
  - How AST nodes are saved
  - Why AST becomes stale after CST editing
  - File watcher limitations for AST updates

- **FILE_WRITE_ANALYSIS.md** focuses on:
  - ALL file write operations in the project
  - Complete database update requirements
  - Unified solution for all write operations

**Combined Solution**:
- Fix `clear_file_data` to include CST trees
- Create `update_file_data` unified method
- This solves BOTH AST staleness AND complete database consistency
- Integrate into all write operations and file watcher

## 9. Conclusion

**Current State**:
- ❌ Most file write operations do NOT update database
- ❌ `clear_file_data` does NOT clear CST trees
- ❌ File watcher does NOT fully update database (only chunking)
- ❌ AST trees become stale after file writes (see `AST_UPDATE_ANALYSIS.md`)
- ✅ `update_indexes` works correctly but is not called automatically

**Required Actions**:
1. Fix `clear_file_data` to include CST trees
2. Create `update_file_data` unified method (solves AST + all data consistency)
3. Integrate into all file write operations:
   - CST compose
   - File/class splitters
   - Superclass extractor
   - Code formatter
   - File restoration
4. Integrate into file watcher (replaces `mark_file_needs_chunking`)
5. Test all operations

**Priority**: **HIGH** - Database consistency is critical for code analysis. This fixes both AST staleness and complete data consistency issues.

