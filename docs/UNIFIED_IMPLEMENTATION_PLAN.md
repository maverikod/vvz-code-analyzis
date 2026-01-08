# Unified Implementation Plan: File Write and Database Update

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-27

## Executive Summary

This document provides a unified, step-by-step implementation plan for ensuring database consistency after file write operations. It combines requirements from:

- `docs/FILE_WRITE_ANALYSIS.md` - All file write operations analysis
- `docs/AST_UPDATE_ANALYSIS.md` - AST update mechanism analysis
- `docs/IMPLEMENTATION_PLAN_CLASS_MERGER_AND_AST_RESTORE.md` - AST/CST restoration enhancements

**Goal**: Ensure that after ANY file write operation:
1. All database records (AST, CST, code entities, chunks) are properly updated and synchronized
2. **File is immediately vectorized** (if SVO available) or marked for worker processing

## Table of Contents

1. [Dependencies and Prerequisites](#1-dependencies-and-prerequisites)
2. [Phase 1: Foundation - Database Methods](#2-phase-1-foundation---database-methods)
3. [Phase 2: Core - Unified Update Method](#3-phase-2-core---unified-update-method)
4. [Phase 3: Integration - File Write Operations](#4-phase-3-integration---file-write-operations)
5. [Phase 4: Integration - File Watcher](#5-phase-4-integration---file-watcher)
6. [Phase 5: Enhancement - AST Comment Preservation](#6-phase-5-enhancement---ast-comment-preservation)
7. [Testing Strategy](#7-testing-strategy)
8. [Success Criteria](#8-success-criteria)

---

## 1. Dependencies and Prerequisites

### 1.1 Required Knowledge

- Understanding of `update_indexes` command (`code_analysis/commands/code_mapper_mcp_command.py`)
- Understanding of `clear_file_data` method (`code_analysis/core/database/files.py`)
- Understanding of file write operations (CST compose, splitters, extractors, formatter)
- Understanding of file watcher architecture

### 1.2 Required Files

- `code_analysis/core/database/files.py` - Database file operations
- `code_analysis/core/database/cst.py` - CST tree operations
- `code_analysis/commands/code_mapper_mcp_command.py` - Update indexes command
- `code_analysis/core/file_watcher_pkg/processor.py` - File watcher processor
- All file write operation files (see Phase 3)

### 1.3 Dependencies Graph

```
Phase 1 (Foundation)
  └─> Phase 2 (Core)
       └─> Phase 3 (Integration - Write Ops)
       └─> Phase 4 (Integration - Watcher)
  └─> Phase 5 (Enhancement - AST Comments)
```

**Critical Path**: Phase 1 → Phase 2 → Phase 3/4 (can be parallel)

---

## 2. Phase 1: Foundation - Database Methods

**Goal**: Fix `clear_file_data` to include CST trees deletion.

**Duration**: 30 minutes  
**Dependencies**: None  
**Blocks**: Phase 2

### Step 1.1: Analyze Current `clear_file_data` Implementation

**File**: `code_analysis/core/database/files.py`

**Current State** (line 199-271):
- Clears: classes, methods, functions, imports, issues, usages, dependencies, code_content, FTS, AST trees, code chunks, vector index
- ❌ **Missing**: CST trees deletion

**Task**: Review current implementation to understand all deletion operations.

### Step 1.2: Add CST Tree Deletion to `clear_file_data`

**File**: `code_analysis/core/database/files.py`

**Location**: After AST tree deletion (around line 248)

**Code to Add**:
```python
# Delete CST trees for this file
self._execute("DELETE FROM cst_trees WHERE file_id = ?", (file_id,))
```

**Full Context**:
```python
def clear_file_data(self, file_id: int) -> None:
    """
    Clear all data for a file.
    
    Removes all related data including:
    - classes and their methods
    - functions
    - imports
    - issues
    - usages
    - dependencies (both as source and target)
    - code_content and FTS index
    - AST trees
    - CST trees  # <-- ADD THIS TO DOCSTRING
    - code chunks
    - vector index entries
    """
    # ... existing code ...
    
    self._execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))
    
    # ADD THIS:
    self._execute("DELETE FROM cst_trees WHERE file_id = ?", (file_id,))
    
    # ... rest of existing code ...
```

### Step 1.3: Update Method Docstring

**Task**: Update docstring to include CST trees in the list of cleared data.

### Step 1.4: Test `clear_file_data` Fix

**Test Cases**:
1. Create test file with AST and CST trees in database
2. Call `clear_file_data(file_id)`
3. Verify CST trees are deleted
4. Verify all other data is still cleared correctly

**Test File**: `tests/test_database_files.py` (add test case)

**Expected Result**: All CST trees for file_id are deleted from `cst_trees` table.

---

## 3. Phase 2: Core - Unified Update Method

**Goal**: Create `update_file_data` method that clears old records and recreates them via `update_indexes`.

**Duration**: 2-3 hours  
**Dependencies**: Phase 1 (clear_file_data fix)  
**Blocks**: Phase 3, Phase 4

### Step 2.1: Design Method Signature and Behavior

**Method Name**: `update_file_data`

**Location**: `code_analysis/core/database/files.py` (or new module `code_analysis/core/database/file_updater.py`)

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

### Step 2.2: Implement File Path Resolution

**Task**: Resolve file path (handle both relative and absolute paths).

**Code**:
```python
from pathlib import Path
from ..project_resolution import normalize_abs_path

# Normalize path to absolute
abs_path = normalize_abs_path(file_path)
if not Path(abs_path).is_absolute():
    abs_path = (Path(root_dir) / file_path).resolve()

# Get file record
file_record = self.get_file_by_path(str(abs_path), project_id)
if not file_record:
    return {
        "success": False,
        "error": f"File not found in database: {file_path}",
        "file_path": str(abs_path)
    }

file_id = file_record["id"]
```

### Step 2.3: Implement Clear Old Records

**Task**: Call `clear_file_data` to remove all old records.

**Code**:
```python
try:
    # Clear all old records (including CST trees - fixed in Phase 1)
    self.clear_file_data(file_id)
except Exception as e:
    logger.error(f"Error clearing file data for {file_path}: {e}", exc_info=True)
    return {
        "success": False,
        "error": f"Failed to clear old records: {e}",
        "file_path": str(abs_path),
        "file_id": file_id
    }
```

### Step 2.4: Implement Call to `update_indexes`

**Task**: Call `_analyze_file` from `UpdateIndexesMCPCommand` to recreate all records.

**Challenge**: `_analyze_file` is a method of `UpdateIndexesMCPCommand` class, not database method.

**Solution Options**:

**Option A**: Extract `_analyze_file` logic to utility function
- Create `code_analysis/core/file_analyzer.py`
- Extract analysis logic
- Use in both `update_indexes` and `update_file_data`

**Option B**: Import and use `UpdateIndexesMCPCommand._analyze_file` directly
- Create instance of command
- Call `_analyze_file` method

**Option C**: Duplicate analysis logic in `update_file_data`
- Not recommended (code duplication)

**Recommended**: **Option A** (extract to utility)

**Implementation** (Option A):
```python
from ..commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

# Create command instance
update_cmd = UpdateIndexesMCPCommand()

# Call _analyze_file (this will parse AST, save AST/CST, extract entities)
result = update_cmd._analyze_file(
    database=self,
    file_path=Path(abs_path),
    project_id=project_id,
    root_path=Path(root_dir)
)

if result.get("status") == "error":
    return {
        "success": False,
        "error": result.get("error", "Unknown error"),
        "file_path": str(abs_path),
        "file_id": file_id
    }
```

### Step 2.5: Implement Result Processing

**Task**: Process `_analyze_file` result and return formatted response.

**Code**:
```python
# Check if AST and CST were saved
ast_updated = result.get("ast_saved", False)
cst_updated = result.get("cst_saved", False)
entities_count = result.get("classes", 0) + result.get("functions", 0)

return {
    "success": True,
    "file_id": file_id,
    "file_path": str(abs_path),
    "ast_updated": ast_updated,
    "cst_updated": cst_updated,
    "entities_updated": entities_count,
    "result": result  # Full result from _analyze_file
}
```

### Step 2.6: Add Immediate Vectorization Support

**Task**: Add optional immediate vectorization after database update.

**New Method**: `vectorize_file_immediately(file_id, project_id, file_path)`

**Location**: `code_analysis/core/database/files.py` or new module `code_analysis/core/vectorization_helper.py`

**Purpose**: Immediately chunk and vectorize file after database update.

**Approach**: 
- Try immediate chunking if SVO client manager is available
- If successful, file is vectorized immediately
- If failed or SVO unavailable, mark for worker processing

**Signature**:
```python
async def vectorize_file_immediately(
    self,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Immediately chunk and vectorize a file after database update.
    
    This method attempts to vectorize the file immediately. If SVO client
    manager is not available or chunking fails, file is marked for worker
    processing (non-blocking fallback).
    
    Process:
    1. Check if SVO client manager is available
    2. Read file content and parse AST
    3. Call DocstringChunker.process_file() to chunk and get embeddings
    4. If successful, chunks are saved with embeddings
    5. Worker will add vectors to FAISS in next cycle
    6. If failed, mark file for worker processing
    
    Args:
        file_id: File ID
        project_id: Project ID
        file_path: File path (absolute)
        svo_client_manager: Optional SVO client manager
        faiss_manager: Optional FAISS manager
        
    Returns:
        Dictionary with vectorization result:
        {
            "success": bool,
            "chunked": bool,  # True if chunking succeeded
            "chunks_created": int,
            "vectorized": bool,  # True if embeddings were created
            "marked_for_worker": bool,  # True if marked for worker processing
            "error": Optional[str]
        }
    """
```

**Implementation**:
```python
import ast
import logging
from pathlib import Path
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

async def vectorize_file_immediately(
    self,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Immediately chunk and vectorize a file after database update.
    """
    # If no SVO client manager, mark for worker processing
    if not svo_client_manager:
        logger.debug(f"No SVO client manager, marking {file_path} for worker processing")
        self.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": True,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": None
        }
    
    try:
        # Read file content
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.warning(f"File not found for vectorization: {file_path}")
            self.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": "File not found"
            }
        
        file_content = file_path_obj.read_text(encoding="utf-8")
        
        # Parse AST
        try:
            tree = ast.parse(file_content, filename=file_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            self.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": f"Syntax error: {e}"
            }
        
        # Create chunker and process file
        from ..docstring_chunker_pkg import DocstringChunker
        
        chunker = DocstringChunker(
            database=self,
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
            min_chunk_length=30,
        )
        
        chunks_created = await chunker.process_file(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            tree=tree,
            file_content=file_content,
        )
        
        logger.info(
            f"Immediately vectorized file {file_path}: "
            f"{chunks_created} chunks created"
        )
        
        return {
            "success": True,
            "chunked": True,
            "chunks_created": chunks_created,
            "vectorized": chunks_created > 0,  # Chunks have embeddings if created
            "marked_for_worker": False,
            "error": None
        }
        
    except Exception as e:
        logger.error(
            f"Error during immediate vectorization of {file_path}: {e}",
            exc_info=True
        )
        # Fallback: mark for worker processing
        self.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": False,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": str(e)
        }
```

**Note**: This method is async and requires SVO client manager. It should be called from async context.

**See**: `docs/IMMEDIATE_VECTORIZATION_SOLUTION.md` for detailed implementation guide.

### Step 2.7: Create Helper Functions for SVO/FAISS Managers

**Task**: Create helper functions to get SVO client manager and FAISS manager from config.

**File**: `code_analysis/core/vectorization_helper.py` (NEW FILE) or add to existing module

**Code**:
```python
"""
Helper functions for immediate vectorization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


def get_svo_client_manager() -> Optional[Any]:
    """
    Get SVO client manager from config or global state.
    
    Returns:
        SVOClientManager instance or None if not available
    """
    try:
        # Try to get from global state or config
        # This depends on how managers are stored in your architecture
        from ..svo_client_manager import get_global_svo_manager
        return get_global_svo_manager()
    except (ImportError, AttributeError):
        logger.debug("SVO client manager not available")
        return None


def get_faiss_manager() -> Optional[Any]:
    """
    Get FAISS manager from config or global state.
    
    Returns:
        FAISSManager instance or None if not available
    """
    try:
        from ..faiss_manager import get_global_faiss_manager
        return get_global_faiss_manager()
    except (ImportError, AttributeError):
        logger.debug("FAISS manager not available")
        return None
```

**Alternative**: Pass managers as parameters to methods that need them.

### Step 2.8: Add Error Handling

**Task**: Add comprehensive error handling for all failure cases.

**Error Cases**:
1. File not found in database
2. File not found on filesystem
3. Syntax error in file
4. Database error during clear
5. Database error during save

**Code**:
```python
try:
    # ... implementation ...
except FileNotFoundError as e:
    return {"success": False, "error": f"File not found: {e}", ...}
except SyntaxError as e:
    return {"success": False, "error": f"Syntax error: {e}", ...}
except Exception as e:
    logger.error(f"Unexpected error in update_file_data: {e}", exc_info=True)
    return {"success": False, "error": f"Unexpected error: {e}", ...}
```

### Step 2.8: Integrate Immediate Vectorization into `update_file_data`

**Task**: Add optional immediate vectorization call after database update.

**Location**: In `update_file_data` method, after successful `_analyze_file` call.

**Code**:
```python
# After successful _analyze_file
result = update_cmd._analyze_file(...)

# Try immediate vectorization (optional, non-blocking)
vectorization_result = None
try:
    # Get SVO client manager if available (need to pass or get from config)
    # This is optional - if not available, file will be processed by worker
    if hasattr(self, '_svo_client_manager') and self._svo_client_manager:
        vectorization_result = await self.vectorize_file_immediately(
            file_id=file_id,
            project_id=project_id,
            file_path=str(abs_path),
            svo_client_manager=self._svo_client_manager,
            faiss_manager=getattr(self, '_faiss_manager', None),
        )
    else:
        # No SVO manager, mark for worker processing
        self.mark_file_needs_chunking(str(abs_path), project_id)
        vectorization_result = {
            "chunked": False,
            "marked_for_worker": True
        }
except Exception as e:
    logger.warning(f"Immediate vectorization failed for {file_path}: {e}")
    # Fallback: mark for worker processing
    self.mark_file_needs_chunking(str(abs_path), project_id)
    vectorization_result = {
        "chunked": False,
        "marked_for_worker": True,
        "error": str(e)
    }

# Add vectorization info to result
return {
    "success": True,
    "file_id": file_id,
    "file_path": str(abs_path),
    "ast_updated": ast_updated,
    "cst_updated": cst_updated,
    "entities_updated": entities_count,
    "vectorization": vectorization_result,  # Add vectorization result
    "result": result
}
```

**Note**: `update_file_data` becomes async if immediate vectorization is enabled. Alternatively, make vectorization optional and call it separately.

**Alternative Approach**: Keep `update_file_data` synchronous, add separate `update_and_vectorize_file` async method.

**Alternative Approach**: Keep `update_file_data` synchronous, create separate async wrapper.

**Better Approach**: Create `update_and_vectorize_file` async method that calls both:
```python
async def update_and_vectorize_file(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Update database and immediately vectorize file.
    
    This is the recommended method for file write operations.
    It combines update_file_data + vectorize_file_immediately.
    """
    # Update database
    update_result = self.update_file_data(
        file_path=file_path,
        project_id=project_id,
        root_dir=root_dir
    )
    
    if not update_result.get("success"):
        return update_result
    
    # Try immediate vectorization
    file_id = update_result.get("file_id")
    abs_path = update_result.get("file_path")
    
    if svo_client_manager:
        vectorization_result = await self.vectorize_file_immediately(
            file_id=file_id,
            project_id=project_id,
            file_path=abs_path,
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
        )
    else:
        # Mark for worker
        self.mark_file_needs_chunking(abs_path, project_id)
        vectorization_result = {
            "chunked": False,
            "marked_for_worker": True
        }
    
    # Combine results
    update_result["vectorization"] = vectorization_result
    return update_result
```

### Step 2.10: Test `update_file_data` and Vectorization Methods

**Test Cases**:
1. Test with existing file in database
2. Test with file not in database (should return error)
3. Test with file with syntax errors
4. Verify AST is updated
5. Verify CST is updated
6. Verify code entities are updated
7. Verify old records are cleared

**Test File**: `tests/test_database_files.py` (add test cases)

---

## 3.5 Phase 2.5: Immediate Vectorization

**Goal**: Add immediate vectorization capability after database update.

**Duration**: 1-2 hours  
**Dependencies**: Phase 2 (update_file_data method)  
**Blocks**: Phase 3, Phase 4

### Step 2.5.1: Create `vectorize_file_immediately` Method

**Location**: `code_analysis/core/database/files.py` or `code_analysis/core/vectorization_helper.py`

**Task**: Implement method that immediately chunks and vectorizes a file.

**See**: `docs/IMMEDIATE_VECTORIZATION_SOLUTION.md` for complete implementation details.

**Key Points**:
- Async method
- Requires SVO client manager
- Falls back to worker if unavailable
- Non-blocking (doesn't fail if vectorization fails)

### Step 2.5.2: Create `update_and_vectorize_file` Wrapper

**Task**: Create async wrapper that combines `update_file_data` + `vectorize_file_immediately`.

**Purpose**: Single method for file write operations that need both update and vectorization.

**See**: `docs/IMMEDIATE_VECTORIZATION_SOLUTION.md` for implementation.

### Step 2.5.3: Create Helper Functions

**Task**: Create helper functions to get SVO/FAISS managers.

**File**: `code_analysis/core/vectorization_helper.py` (NEW)

**Functions**:
- `get_svo_client_manager()` - Get SVO client manager
- `get_faiss_manager()` - Get FAISS manager

### Step 2.5.4: Test Immediate Vectorization

**Test Cases**:
1. Test with SVO available - verify chunks created
2. Test with SVO unavailable - verify marked for worker
3. Test with SVO failure - verify fallback to worker
4. Test error handling

---

## 4. Phase 3: Integration - File Write Operations

**Goal**: Integrate `update_file_data` and immediate vectorization into all file write operations.

**Duration**: 3-4 hours  
**Dependencies**: Phase 2 (update_file_data method, vectorize_file_immediately method)  
**Can be parallel**: Yes (each operation can be done independently)

### Step 3.1: Integrate into CST Compose Command

**File**: `code_analysis/commands/cst_compose_module_command.py`

**Location**: After successful file write (after line 436)

**Code to Add**:
```python
if apply:
    backup_path = write_with_backup(
        target, new_source, create_backup=create_backup
    )
    
    # Update database after file write
    try:
        from pathlib import Path
        from ..core.project_resolution import get_project_id
        
        project_id = get_project_id(root_path)
        if project_id:
            update_result = database.update_file_data(
                file_path=str(target.relative_to(root_path)),
                project_id=project_id,
                root_dir=root_path
            )
            if not update_result.get("success"):
                logger.warning(
                    f"Failed to update database after CST compose: "
                    f"{update_result.get('error')}"
                )
            else:
                logger.info(
                    f"Database updated after CST compose: "
                    f"AST={update_result.get('ast_updated')}, "
                    f"CST={update_result.get('cst_updated')}"
                )
                
                # Try immediate vectorization (async, non-blocking)
                try:
                    # Get SVO client manager if available
                    # Note: Need to get from config or pass as parameter
                    svo_manager = get_svo_client_manager()  # Helper function needed
                    if svo_manager:
                        vectorization_result = await database.vectorize_file_immediately(
                            file_id=update_result.get("file_id"),
                            project_id=project_id,
                            file_path=str(target),
                            svo_client_manager=svo_manager,
                            faiss_manager=get_faiss_manager(),  # Helper function needed
                        )
                        if vectorization_result.get("chunked"):
                            logger.info(
                                f"File vectorized immediately after CST compose: "
                                f"{vectorization_result.get('chunks_created')} chunks"
                            )
                        else:
                            logger.debug("File marked for worker vectorization")
                    else:
                        # No SVO manager, mark for worker
                        database.mark_file_needs_chunking(
                            str(target.relative_to(root_path)),
                            project_id
                        )
                except Exception as e:
                    logger.warning(f"Immediate vectorization failed: {e}")
                    # Fallback: mark for worker
                    database.mark_file_needs_chunking(
                        str(target.relative_to(root_path)),
                        project_id
                    )
    except Exception as e:
        logger.error(f"Error updating database after CST compose: {e}", exc_info=True)
        # Don't fail the operation, just log the error
    
    # Create git commit if git repository and commit_message provided
    if is_git and commit_message:
        # ... existing code ...
```

**Note**: Requires async context. If command is not async, use `asyncio.create_task()` or mark for worker only.

**Note**: Need to get `database` instance. Check how it's accessed in this command.

### Step 3.2: Integrate into File Splitter

**File**: `code_analysis/core/refactorer_pkg/file_splitter.py`

**Location**: After creating new files (after line 73)

**Code to Add**:
```python
for module_name, module_config in modules.items():
    module_path = package_dir / f"{module_name}.py"
    module_content = self._build_module_content(
        module_name, module_config, source_lines
    )
    module_path.write_text(module_content)
    created_modules.append(module_name)
    
    # Update database for new file
    try:
        # Get database and project_id (need to pass these to FileToPackageSplitter)
        if hasattr(self, 'database') and hasattr(self, 'project_id') and hasattr(self, 'root_dir'):
            update_result = self.database.update_file_data(
                file_path=str(module_path.relative_to(self.root_dir)),
                project_id=self.project_id,
                root_dir=self.root_dir
            )
            if not update_result.get("success"):
                logger.warning(f"Failed to update database for {module_path}: {update_result.get('error')}")
    except Exception as e:
        logger.error(f"Error updating database for {module_path}: {e}", exc_info=True)
```

**Note**: Need to pass `database`, `project_id`, `root_dir` to `FileToPackageSplitter` constructor.

### Step 3.3: Integrate into Class Splitter

**File**: `code_analysis/core/refactorer_pkg/splitter.py`

**Location**: After writing modified file (after line 181)

**Code to Add**:
```python
new_content = self._perform_split(src_class, config)
with open(self.file_path, "w", encoding="utf-8") as f:
    f.write(new_content)
    
# Update database after file write
try:
    if hasattr(self, 'database') and hasattr(self, 'project_id') and hasattr(self, 'root_dir'):
        update_result = self.database.update_file_data(
            file_path=str(self.file_path.relative_to(self.root_dir)),
            project_id=self.project_id,
            root_dir=self.root_dir
        )
        if not update_result.get("success"):
            logger.warning(f"Failed to update database: {update_result.get('error')}")
except Exception as e:
    logger.error(f"Error updating database: {e}", exc_info=True)

format_success, format_error = format_code_with_black(self.file_path)
```

**Note**: Need to pass `database`, `project_id`, `root_dir` to `ClassSplitter` constructor.

### Step 3.4: Integrate into Superclass Extractor

**File**: `code_analysis/core/refactorer_pkg/extractor.py`

**Location**: After writing modified file (after line 407)

**Code to Add**: Same pattern as Step 3.3

### Step 3.5: Integrate into Code Formatter

**File**: `code_analysis/core/code_quality/formatter.py`

**Location**: After formatting file (after line 55)

**Code to Add**:
```python
# Write formatted content back
with open(file_path, "w", encoding="utf-8") as f:
    f.write(formatted_content)

# Update database after formatting
# Note: Formatting doesn't change structure, but file_mtime changes
# So we should update database to reflect new mtime
try:
    # Need to get database, project_id, root_dir
    # This might require passing them as parameters to format_code_with_black
    # OR: Make this optional (formatting is less critical)
    pass  # TODO: Implement if needed
except Exception as e:
    logger.warning(f"Error updating database after formatting: {e}")
```

**Note**: Formatting is less critical. Can be marked as optional or deferred.

### Step 3.6: Integrate into File Restoration

**File**: `code_analysis/commands/file_management.py`

**Location**: After restoring file (after line 648)

**Code to Add**:
```python
# Restore file content
target_path.parent.mkdir(parents=True, exist_ok=True)
target_path.write_text(cst_code, encoding="utf-8")

# Update database after restoration
try:
    update_result = self.database.update_file_data(
        file_path=file_path,
        project_id=file_record.get("project_id"),
        root_dir=self.root_dir
    )
    if not update_result.get("success"):
        logger.warning(f"Failed to update database after restoration: {update_result.get('error')}")
except Exception as e:
    logger.error(f"Error updating database after restoration: {e}", exc_info=True)

logger.info(f"Restored file {file_path} from CST to {target_path}")
return True
```

### Step 3.7: Update Refactorer Base Class (if needed)

**File**: `code_analysis/core/refactorer_pkg/base.py`

**Task**: If multiple refactorers need database access, add `database`, `project_id`, `root_dir` to base class constructor.

**Code** (if needed):
```python
def __init__(
    self,
    file_path: Path,
    database: Optional[Any] = None,
    project_id: Optional[str] = None,
    root_dir: Optional[Path] = None,
):
    self.file_path = Path(file_path)
    self.database = database
    self.project_id = project_id
    self.root_dir = root_dir
    # ... rest of existing code ...
```

### Step 3.8: Test All Integrations

**Test Cases for Each Operation**:
1. Perform operation (CST compose, split, etc.)
2. Verify file is written
3. Verify database is updated (AST, CST, entities)
4. Verify old records are cleared
5. Test error handling (database unavailable, etc.)

---

## 5. Phase 4: Integration - File Watcher

**Goal**: Replace `mark_file_needs_chunking` with `update_file_data` in file watcher.

**Duration**: 1-2 hours  
**Dependencies**: Phase 2 (update_file_data method)  
**Can be parallel**: Yes (with Phase 3)

### Step 4.1: Analyze Current File Watcher Behavior

**File**: `code_analysis/core/file_watcher_pkg/processor.py`

**Current Method**: `_queue_file_for_processing()` (line 504)

**Current Behavior**:
- Marks file for chunking (`mark_file_needs_chunking`)
- Updates `last_modified` timestamp
- Does NOT update AST/CST

**Task**: Understand current implementation and identify integration point.

### Step 4.2: Replace `mark_file_needs_chunking` with `update_file_data`

**File**: `code_analysis/core/file_watcher_pkg/processor.py`

**Location**: In `_queue_file_for_processing()` method

**Current Code** (lines 555-575):
```python
# Retry marking for chunking
result = self.database.mark_file_needs_chunking(
    file_path, project_id
)

if result:
    # Update last_modified if file exists
    self.database._execute(
        """
        UPDATE files 
        SET last_modified = ?, updated_at = julianday('now')
        WHERE project_id = ? AND path = ?
        """,
        (mtime, project_id, file_path),
    )
    self.database._commit()
```

**New Code**:
```python
# Update all database records for changed file
try:
    # Get root_dir from project or watch_dirs
    root_dir = self._get_project_root_dir(project_id, file_path)
    if not root_dir:
        logger.warning(f"Could not determine root_dir for {file_path}, skipping update")
        return False
    
    update_result = self.database.update_file_data(
        file_path=file_path,
        project_id=project_id,
        root_dir=root_dir
    )
    
    if update_result.get("success"):
        logger.debug(
            f"[QUEUE] File updated in database: {file_path} | "
            f"AST={update_result.get('ast_updated')}, "
            f"CST={update_result.get('cst_updated')}"
        )
        
        # Try immediate vectorization (if SVO available)
        # Note: This requires async context, so we mark for worker if not available
        vectorization = update_result.get("vectorization")
        if vectorization and vectorization.get("chunked"):
            logger.debug(
                f"[QUEUE] File vectorized immediately: {file_path} | "
                f"chunks={vectorization.get('chunks_created')}"
            )
        else:
            # Mark for chunking (vectorization worker will process)
            self.database.mark_file_needs_chunking(file_path, project_id)
            logger.debug(f"[QUEUE] File marked for worker vectorization: {file_path}")
        
        return True
    else:
        logger.error(
            f"[QUEUE] Failed to update file in database: {file_path} | "
            f"Error: {update_result.get('error')}"
        )
        return False
except Exception as e:
    logger.error(
        f"[QUEUE] Error updating file in database {file_path}: {e}",
        exc_info=True
    )
    return False
```

### Step 4.3: Implement `_get_project_root_dir` Helper Method

**Task**: Create helper method to get project root directory.

**Code**:
```python
def _get_project_root_dir(self, project_id: str, file_path: str) -> Optional[Path]:
    """
    Get project root directory for a file.
    
    Args:
        project_id: Project ID
        file_path: File path (absolute)
        
    Returns:
        Project root directory or None if not found
    """
    try:
        # Get project record
        project = self.database.get_project(project_id)
        if project and project.get("root_path"):
            return Path(project["root_path"])
        
        # Fallback: try to find root from watch_dirs
        abs_path = Path(file_path).resolve()
        for watch_dir in self.watch_dirs_resolved:
            try:
                abs_path.relative_to(watch_dir)
                return watch_dir
            except ValueError:
                continue
        
        return None
    except Exception as e:
        logger.error(f"Error getting project root dir: {e}", exc_info=True)
        return None
```

### Step 4.4: Update Logging

**Task**: Update log messages to reflect new behavior.

**Changes**:
- Change "queued for chunking" to "updated in database"
- Add AST/CST update status to logs
- Keep chunking logs (still needed for vectorization)

### Step 4.5: Test File Watcher Integration

**Test Cases**:
1. Create/modify file outside of code analysis tools
2. Verify file watcher detects change
3. Verify `update_file_data` is called
4. Verify AST is updated
5. Verify CST is updated
6. Verify file is marked for chunking
7. Test with multiple file changes
8. Test error handling (file not in database, etc.)

---

## 6. Phase 5: Enhancement - AST Comment Preservation

**Goal**: Enhance AST saving to preserve comments (optional enhancement).

**Duration**: 2-3 hours  
**Dependencies**: Phase 2 (update_file_data uses _analyze_file)  
**Priority**: Medium (nice to have, not critical)

### Step 5.1: Extract `_parse_with_comments` to Utility

**File**: `code_analysis/core/ast_utils.py` (NEW FILE)

**Task**: Extract `_parse_with_comments` logic from `BaseRefactorer` to standalone utility function.

**Source**: `code_analysis/core/refactorer_pkg/base.py` (method `_parse_with_comments`, line 239)

**Code Structure**:
```python
"""
AST utilities for parsing with comment preservation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tokenize
import io
from typing import Dict, List, Tuple
from pathlib import Path


def parse_with_comments(source: str, filename: str = "<unknown>") -> ast.Module:
    """
    Parse Python code and preserve comments as string expressions in AST.
    
    Comments are added as ast.Expr(ast.Constant(value="# comment")) nodes
    before the statements they precede.
    
    Args:
        source: Python source code string
        filename: Filename for error messages
        
    Returns:
        AST module with comments preserved as string expressions
    """
    # Copy logic from BaseRefactorer._parse_with_comments
    # ... (see IMPLEMENTATION_PLAN_CLASS_MERGER_AND_AST_RESTORE.md for details)
```

### Step 5.2: Update `_analyze_file` to Use `parse_with_comments`

**File**: `code_analysis/commands/code_mapper_mcp_command.py`

**Location**: Line 233 (AST parsing)

**Current Code**:
```python
tree = ast.parse(file_content, filename=str(file_path))
```

**New Code**:
```python
from ..core.ast_utils import parse_with_comments

# Use parse_with_comments to preserve comments in AST
tree = parse_with_comments(file_content, filename=str(file_path))
```

### Step 5.3: Test Comment Preservation

**Test Cases**:
1. Parse file with comments
2. Verify comments are preserved in AST
3. Save AST to database
4. Verify AST JSON contains comment nodes
5. Test with various comment types (inline, block, docstring-like)

### Step 5.4: Update Documentation

**File**: `docs/AST_UPDATE_ANALYSIS.md`

**Task**: Update to reflect that AST now preserves comments.

**Changes**:
- Update "AST Storage Process" section
- Note that comments are preserved
- Explain comment preservation mechanism

---

## 7. Testing Strategy

### 7.1 Unit Tests

**Phase 1 Tests**:
- `test_clear_file_data_includes_cst_trees()` - Verify CST trees are deleted

**Phase 2 Tests**:
- `test_update_file_data_success()` - Test successful update
- `test_update_file_data_file_not_found()` - Test error handling
- `test_update_file_data_syntax_error()` - Test syntax error handling
- `test_update_file_data_clears_old_records()` - Verify old records cleared
- `test_update_file_data_creates_new_records()` - Verify new records created

**Phase 3 Tests** (for each operation):
- `test_cst_compose_updates_database()` - CST compose integration
- `test_file_splitter_updates_database()` - File splitter integration
- `test_class_splitter_updates_database()` - Class splitter integration
- `test_extractor_updates_database()` - Extractor integration

**Phase 4 Tests**:
- `test_file_watcher_updates_database()` - File watcher integration
- `test_file_watcher_multiple_changes()` - Multiple file changes

**Phase 5 Tests**:
- `test_parse_with_comments()` - Comment preservation
- `test_ast_saving_with_comments()` - AST saving with comments

### 7.2 Integration Tests

**Test Scenarios**:
1. **Full Workflow Test**:
   - Write file via CST compose
   - Verify database updated
   - Modify file directly
   - Verify file watcher updates database
   - Verify all records are consistent

2. **Error Recovery Test**:
   - Simulate database error during update
   - Verify operation doesn't fail
   - Verify error is logged
   - Verify file is still written

3. **Concurrent Updates Test**:
   - Multiple file writes simultaneously
   - Verify all updates succeed
   - Verify no race conditions

### 7.3 Manual Testing Checklist

- [ ] CST compose updates database
- [ ] File splitter updates database for new files
- [ ] Class splitter updates database
- [ ] Extractor updates database
- [ ] File watcher updates database on file change
- [ ] Old records are cleared before update
- [ ] AST tree is updated
- [ ] CST tree is updated
- [ ] Code entities are updated
- [ ] Error handling works correctly
- [ ] Logging is informative

---

## 8. Success Criteria

### 8.1 Functional Requirements

✅ **After ANY file write operation**:
- All old database records are cleared (including CST trees)
- New records are created (AST, CST, entities)
- Database is consistent with file content

✅ **File watcher**:
- Detects file changes
- Updates database automatically
- Marks files for chunking

✅ **Error handling**:
- Operations don't fail if database update fails
- Errors are logged clearly
- File writes succeed even if database update fails

### 8.2 Performance Requirements

- Database update should not significantly slow down file writes
- File watcher should handle multiple changes efficiently
- No blocking operations in file write paths

### 8.3 Code Quality Requirements

- All methods have proper docstrings
- Error handling is comprehensive
- Logging is informative
- Code follows project conventions

---

## 9. Implementation Order Summary

**Week 1**:
- Day 1: Phase 1 (Foundation) - 30 min
- Day 1: Phase 2 (Core) - 2-3 hours
- Day 1: Phase 2.5 (Immediate Vectorization) - 1-2 hours
- Day 1-2: Phase 3 (Integration - Write Ops) - 3-4 hours

**Week 2**:
- Day 1: Phase 4 (Integration - Watcher) - 1-2 hours
- Day 1-2: Testing and bug fixes - 2-3 hours
- Day 2-3: Phase 5 (Enhancement) - 2-3 hours (optional)

**Total Estimated Time**: 12-17 hours (includes immediate vectorization)

---

## 10. Risk Mitigation

### 10.1 Risks

1. **Database update fails during file write**
   - **Mitigation**: Don't fail file write, just log error
   - **Impact**: Low (file is written, database can be updated later)

2. **Performance impact**
   - **Mitigation**: Make database update async where possible
   - **Impact**: Medium (may slow down file writes)

3. **Race conditions in file watcher**
   - **Mitigation**: Use database locks, handle errors gracefully
   - **Impact**: Low (rare, handled by error recovery)

### 10.2 Rollback Plan

If issues arise:
1. Revert Phase 3/4 integrations (keep Phase 1/2)
2. Keep `update_file_data` method for manual use
3. Gradually re-integrate after fixes

---

## 11. References

- `docs/FILE_WRITE_ANALYSIS.md` - Complete file write operations analysis
- `docs/AST_UPDATE_ANALYSIS.md` - AST update mechanism analysis
- `docs/IMPLEMENTATION_PLAN_CLASS_MERGER_AND_AST_RESTORE.md` - AST comment preservation
- `code_analysis/core/database/files.py` - Database file operations
- `code_analysis/commands/code_mapper_mcp_command.py` - Update indexes command

---

**End of Document**

