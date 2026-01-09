# Missing Items in PLAN_AUTO_START_VECTORIZATION_WORKER.md

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Overview

This document lists items that are missing or need clarification in the main plan.

## Critical Missing Items

### 1. Worker Manager Registration

**Issue**: Worker registration in `WorkerManager` is not mentioned in the plan.

**Current State**:
- In `main.py`: Workers registered with name `f"vectorization_{project_id}_{dataset_id[:8]}"`
- In `worker_launcher.py`: Workers registered with name `f"vectorization_{project_id}"`
- Restart functions also use project_id/dataset_id

**What's Missing**:
- Step 6 should mention updating worker registration name to `"vectorization_universal"` or just `"vectorization"`
- Need to update `worker_launcher.py` function `start_vectorization_worker()` to register universal worker
- Need to update restart function in `main.py` (if it exists) to work without project_id/dataset_id

**Files to Update**:
- `code_analysis/core/worker_launcher.py` - update `start_vectorization_worker()` registration
- `code_analysis/main.py` - update worker registration and restart function (if exists)

### 2. MCP Command `start_worker`

**Issue**: MCP command for starting workers is not mentioned in the plan.

**Current State**:
- `code_analysis/commands/worker_management_mcp_commands.py` has `StartWorkerMCPCommand`
- It accepts `project_id` and `dataset_id` parameters
- It uses `start_vectorization_worker()` from `worker_launcher.py`

**What's Missing**:
- Decision: Should MCP command still support manual start with project_id/dataset_id, or should it be updated to universal mode only?
- If keeping manual mode: Document that MCP command can still start project-specific workers (for backward compatibility or manual control)
- If removing manual mode: Update MCP command to start universal worker only

**Recommendation**: Keep MCP command flexible - allow both universal mode (no project_id) and project-specific mode (with project_id) for manual control.

### 3. SQL Query Details for `get_projects_with_vectorization_count()`

**Issue**: Step 1 doesn't provide SQL query example or detailed implementation.

**What's Missing**:
- Example SQL query showing how to count files needing chunking + chunks needing vectorization
- Clarification: Should count be per project (all datasets) or per dataset?
- Since plan uses project-scoped indexes, count should be per project (all datasets combined)

**Suggested SQL** (needs to be added to Step 1):
```sql
SELECT 
    p.id AS project_id,
    p.root_path,
    (
        -- Count files needing chunking (all datasets in project)
        (SELECT COUNT(DISTINCT f.id)
         FROM files f
         WHERE f.project_id = p.id
           AND (f.deleted = 0 OR f.deleted IS NULL)
           AND (f.has_docstring = 1 
                OR EXISTS (SELECT 1 FROM classes c WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != '')
                OR EXISTS (SELECT 1 FROM functions fn WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != '')
                OR EXISTS (SELECT 1 FROM methods m JOIN classes c ON m.class_id = c.id WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''))
           AND NOT EXISTS (SELECT 1 FROM code_chunks cc WHERE cc.file_id = f.id))
        +
        -- Count chunks needing vectorization (all datasets in project)
        (SELECT COUNT(cc.id)
         FROM code_chunks cc
         INNER JOIN files f ON cc.file_id = f.id
         WHERE cc.project_id = p.id
           AND (f.deleted = 0 OR f.deleted IS NULL)
           AND cc.embedding_vector IS NOT NULL
           AND cc.vector_id IS NULL)
    ) AS pending_count
FROM projects p
WHERE pending_count > 0
ORDER BY pending_count ASC
```

### 4. Chunking Request Details

**Issue**: Step 2 mentions `get_files_needing_chunking()` but doesn't detail what happens with these files.

**Current State**:
- `_request_chunking_for_files()` is called in `processing.py`
- It uses `DocstringChunker` to chunk files
- It reads files from disk, parses AST, and calls chunker

**What's Missing**:
- Clarification: `_request_chunking_for_files()` should still work (it uses project_id from file record)
- No changes needed to chunking logic - it already works with project_id
- But need to ensure it's called correctly in the new processing loop

**Note**: This is probably fine as-is, but should be mentioned in Step 2 details.

### 5. Worker Launcher Function Update

**Issue**: `worker_launcher.py` function `start_vectorization_worker()` is not in the "Files to Modify" list.

**Current State**:
- Function signature: `start_vectorization_worker(db_path, project_id, faiss_index_path, ...)`
- It registers worker with name `f"vectorization_{project_id}"`
- It calls `run_vectorization_worker()` with project_id

**What's Missing**:
- Function signature needs to change: remove `project_id`, `faiss_index_path`, `dataset_id`; add `faiss_dir`
- Worker registration name should change to `"vectorization_universal"`
- Function should call `run_vectorization_worker()` without project_id/dataset_id

**Files to Update**:
- `code_analysis/core/worker_launcher.py` - update `start_vectorization_worker()` function

### 6. Restart Function in main.py

**Issue**: If restart function exists in `main.py`, it needs to be updated.

**Current State**:
- In `main.py` around line 1003-1042, there's a `_restart_vectorization_worker()` function
- It uses `project_id` and `dataset_id` from closure
- It creates restart function with these parameters

**What's Missing**:
- If universal worker, restart function should not use project_id/dataset_id
- Restart function should start universal worker only
- Need to update restart function signature and logic

**Files to Update**:
- `code_analysis/main.py` - update restart function (if it exists)

### 7. Edge Case: Multiple Workers

**Issue**: What if someone manually starts a project-specific worker while universal worker is running?

**What's Missing**:
- Edge case: Multiple vectorization workers running simultaneously
- Should universal worker detect and handle this?
- Or should worker manager prevent multiple workers of same type?

**Recommendation**: Add to Edge Cases section:
- **Multiple workers running**: If universal worker is running, prevent starting project-specific workers (or vice versa)
- Worker manager should check if universal worker exists before allowing project-specific workers

### 8. Configuration: watch_dirs

**Issue**: Plan says to remove watch_dirs, but what about config file?

**Current State**:
- Config file may have `watch_dirs` in worker config
- Worker currently uses these for filesystem scanning

**What's Missing**:
- Clarification: Should `watch_dirs` be removed from config schema?
- Or should it be ignored by worker (for backward compatibility)?
- File watcher still uses watch_dirs, so they should remain in config

**Recommendation**: Keep `watch_dirs` in config (file watcher needs them), but worker ignores them.

### 9. Log File Path

**Issue**: Worker log path currently includes project_id/dataset_id in name.

**Current State**:
- In `main.py`: `dataset_log_path = f"{log_path_obj.stem}_{project_id[:8]}_{dataset_id[:8]}{log_path_obj.suffix}"`
- Universal worker should have single log file

**What's Missing**:
- Update log path generation for universal worker
- Should be just `vectorization_worker.log` or `vectorization_universal.log`

**Files to Update**:
- `code_analysis/main.py` - update log path generation

### 10. Database Method: get_non_vectorized_chunks with dataset_id=None

**Issue**: Step 2 mentions `get_non_vectorized_chunks(project_id, dataset_id=None)`, but need to verify this works correctly.

**Current State**:
- Method exists and supports `dataset_id=None` for all datasets in project
- Should work as-is

**What's Missing**:
- Verification that `dataset_id=None` returns chunks from all datasets in project
- Should be tested/verified

**Note**: This is probably fine, but should be verified during implementation.

## Minor Missing Items

### 11. Import Statements

**Issue**: When removing parameters, need to check all import statements and usages.

**What's Missing**:
- Verify no unused imports after removing project_id/dataset_id
- Check all places where these parameters are used

### 12. Type Hints

**Issue**: Function signatures need type hints updated.

**What's Missing**:
- Update type hints for all modified functions
- Remove `project_id: str` and `dataset_id: Optional[str]` from signatures
- Add `faiss_dir: Path` or `faiss_dir: str` to signatures

### 13. Documentation Strings

**Issue**: Docstrings need to be updated to reflect universal mode.

**What's Missing**:
- Update all docstrings that mention project_id/dataset_id
- Remove references to "single project" or "dataset-scoped"
- Add description of universal mode

## Summary

**Critical Items** (must be added):
1. Worker Manager registration update (Step 6)
2. Worker launcher function update (add to Files to Modify)
3. SQL query example for Step 1
4. Restart function update (if exists)
5. Log file path update

**Important Items** (should be added):
6. MCP command decision/documentation
7. Edge case: multiple workers
8. Configuration watch_dirs clarification

**Nice to Have** (can be done during implementation):
9. Import cleanup
10. Type hints update
11. Docstring updates

