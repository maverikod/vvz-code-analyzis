# Plan: Auto-start Vectorization Worker for New Projects

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Problem Statement

Currently, vectorization workers are started only during server startup for projects discovered at that time. When a new project is discovered by the file watcher after server startup, no vectorization worker is automatically started for it, resulting in:

- Files are added to database ✅
- Files are marked for chunking ✅
- But chunks are never created ❌ (no worker to process them)
- Vectors are never created ❌ (no worker to process them)

**Root Cause**: Vectorization worker is bound to a specific `project_id` passed at startup. It doesn't query the database to discover new projects dynamically. **Solution**: Remove project_id binding completely - worker always works in universal mode, processing all projects from database.

## Solution Overview

**Current Architecture Problem**: 
- One vectorization worker process per project
- Workers are started only at server startup for projects discovered at that time
- New projects discovered later have no worker to process them

**Correct Solution**:
Make vectorization worker database-driven and universal:
- **One universal vectorization worker** for all projects (single process)
- Worker works **only with database** - no filesystem access, no watch_dirs
- Worker periodically queries database to get:
  - List of projects with count of files needing vectorization (sorted from smallest to largest)
  - For each project: list of non-vectorized files/chunks
- Processes projects sequentially, one by one
- **File watcher remains unchanged** - continues to work independently with database
- Both workers are completely independent - no inter-process dependencies
- **Note**: FAISS indexes are project-scoped - each project has its own index file

**Architecture**:
```
File Watcher (1 process)
    ↓ (writes to DB)
Database
    ↑ (reads from DB)
Vectorization Worker (1 universal process for all projects)
    - Works only with database
    - No filesystem access
    - Processes projects sequentially
```

**Benefits**:
- File watcher and vectorization worker remain independent
- No need to start new processes for new projects
- More efficient resource usage (one process instead of many)
- Automatic discovery of new projects through database queries
- Simple architecture: two independent workers, both work with database
- No filesystem dependencies - pure database-driven processing

## Implementation Plan

### Step 0: Exclude Dataset Concept Completely from Vectorization Worker

**Files**: All vectorization worker files

**Action**:
- **EXCLUDE all dataset-related code** from vectorization worker completely
- **EXCLUDE `dataset_id` parameter** from all worker functions - it must not exist in worker code
- Work directly with `project_id` only - worker operates at project level only
- FAISS index path: `{faiss_dir}/{project_id}.bin` (project-scoped, datasets EXCLUDED)
- Database methods should work with `project_id` only - `dataset_id` parameter EXCLUDED from all calls

**Details**:
- **EXCLUDE `dataset_id` parameter** from all worker function signatures - parameter must not exist
- **EXCLUDE dataset concept** from FAISS index paths - change from `get_faiss_index_path(faiss_dir, project_id, dataset_id)` to `faiss_dir / f"{project_id}.bin"`
  - **Path format**: `{faiss_dir}/{project_id}.bin` (datasets EXCLUDED from path structure)
- **EXCLUDE `dataset_id`** from all `get_non_vectorized_chunks()` calls - use `project_id` only (all chunks in project, datasets EXCLUDED)
- **EXCLUDE `dataset_id`** from all `check_index_sync()` calls - use `project_id` only (datasets EXCLUDED from sync logic)
- **EXCLUDE `dataset_id`** from all `rebuild_from_database()` calls - use `project_id` only (all chunks in project, datasets EXCLUDED)
- **EXCLUDE all dataset-related logic** from worker code - worker must not process datasets at all
- **EXCLUDE dataset filtering** - worker processes all files/chunks in project regardless of dataset
- **Note**: Dataset table in database remains (for file watcher compatibility), but vectorization worker **completely EXCLUDES** it from processing
- **Note**: No migration needed - test database only, existing indexes can be ignored or removed manually
- **MCP Command `start_worker`**: Only universal mode, `project_id` and `dataset_id` parameters **EXCLUDED** completely

**Checklist**:
- [ ] **EXCLUDE `dataset_id` parameter** from `run_vectorization_worker()` function signature - parameter must not exist
- [ ] **EXCLUDE `dataset_id` parameter** from `VectorizationWorker.__init__()` method signature - parameter must not exist
- [ ] **EXCLUDE `dataset_id`** from all calls to `get_non_vectorized_chunks()` - datasets EXCLUDED from chunk retrieval
- [ ] **EXCLUDE `dataset_id`** from all calls to `check_index_sync()` - datasets EXCLUDED from sync checks
- [ ] **EXCLUDE `dataset_id`** from all calls to `rebuild_from_database()` - datasets EXCLUDED from rebuilds
- [ ] **EXCLUDE dataset concept** from FAISS paths - replace all `get_faiss_index_path(faiss_dir, project_id, dataset_id)` with `faiss_dir / f"{project_id}.bin"`
- [ ] **EXCLUDE all `dataset_id` variables** and references in worker code - must not exist
- [ ] **EXCLUDE dataset mentions** from all docstrings - worker does not process datasets
- [ ] Run `grep -r "dataset_id"` in `vectorization_worker_pkg/` - should return no results (datasets EXCLUDED)
- [ ] Run `grep -r "dataset"` in `vectorization_worker_pkg/` - should return no results (datasets EXCLUDED)
- [ ] Verify FAISS index paths use format `{faiss_dir}/{project_id}.bin` everywhere (datasets EXCLUDED from path)

**Tests**:
1. **Test function signatures**: Verify `dataset_id` parameter **EXCLUDED** from worker functions
   - Create test that tries to call with `dataset_id` - should fail with TypeError (parameter **EXCLUDED**)
   - Verify function signatures match expected (`dataset_id` **EXCLUDED** completely)

2. **Test FAISS index path generation**: Verify all index paths use project-scoped format (datasets EXCLUDED)
   - Mock `faiss_dir` and `project_id`
   - Verify path is `{faiss_dir}/{project_id}.bin` (datasets EXCLUDED - not `{faiss_dir}/{project_id}/{dataset_id}.bin`)
   - Test in all places where FAISS manager is created
   - Verify no dataset-related path components

3. **Test database method calls**: Verify all calls use `project_id` only (datasets EXCLUDED)
   - Mock database methods and verify calls **EXCLUDE `dataset_id` completely**
   - Test `get_non_vectorized_chunks(project_id)` - **EXCLUDES `dataset_id`** (processes all chunks in project)
   - Test `check_index_sync(database, project_id=project_id)` - **EXCLUDES `dataset_id`** (checks all chunks in project)
   - Test `rebuild_from_database(..., project_id=project_id)` - **EXCLUDES `dataset_id`** (rebuilds all chunks in project)

4. **Test code search**: Verify datasets EXCLUDED from worker code
   - Run `grep -r "dataset_id"` in worker package - should return empty (datasets EXCLUDED)
   - Run `grep -r "dataset"` in worker package - should return empty (datasets EXCLUDED)
   - Verify no dataset-related code remains in worker

5. **Test type hints**: Verify type hints don't include `dataset_id`
   - Check all function signatures for type hints
   - Verify `Optional[str]` for `dataset_id` is **EXCLUDED** (type hint must not exist)

### Step 1: Add Database Method to Get Projects with Vectorization Count

**File**: `code_analysis/core/database/projects.py` or `chunks.py`

**Action**:
- Add new method `get_projects_with_vectorization_count()` that returns:
  - List of projects with count of files/chunks needing vectorization
  - Sorted from smallest count to largest (process smaller projects first)
  - Returns: `List[Dict[str, Any]]` with keys: `project_id`, `root_path`, `pending_count`

**Details**:
- Query counts files needing chunking + chunks needing vectorization per project
- Sort by total count ascending (smallest first)
- Return project_id, root_path, and count for each project
- **Note**: Methods for project ID ↔ path conversion already exist:
  - `database.get_project_id(root_path: str) -> Optional[str]` - get ID by path
  - `database.get_project(project_id: str) -> Optional[Dict[str, Any]]` - get project (with root_path) by ID
  - `database.get_all_projects() -> List[Dict[str, Any]]` - get all projects with root_path

**SQL Query Example**:
```sql
SELECT 
    p.id AS project_id,
    p.root_path,
    (
        -- Count files needing chunking (project-scoped, all files in project)
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
        -- Count chunks needing vectorization (project-scoped, all chunks in project)
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

**Checklist**:
- [ ] Add method `get_projects_with_vectorization_count()` to database class
- [ ] Implement SQL query that counts files needing chunking per project
- [ ] Implement SQL query that counts chunks needing vectorization per project
- [ ] Combine counts and sort by `pending_count ASC`
- [ ] Return list with keys: `project_id`, `root_path`, `pending_count`
- [ ] Handle edge cases: empty database, no projects, projects with zero pending count
- [ ] Add method to appropriate database module (`projects.py` or `chunks.py`)
- [ ] Add docstring with method description and return type
- [ ] Verify SQL query excludes deleted files correctly
- [ ] Verify SQL query handles NULL values correctly

**Tests**:
1. **Test empty database**: Call method on empty database - should return empty list
   - Create empty database
   - Call `get_projects_with_vectorization_count()`
   - Assert result is empty list `[]`

2. **Test single project with pending items**: Verify method returns correct count
   - Create test database with one project
   - Add files needing chunking (e.g., 5 files)
   - Add chunks needing vectorization (e.g., 10 chunks)
   - Call method and verify:
     - Returns list with one item
     - `pending_count == 15` (5 files + 10 chunks)
     - `project_id` matches
     - `root_path` matches

3. **Test multiple projects sorted by count**: Verify sorting works correctly
   - Create test database with 3 projects:
     - Project A: 5 pending items
     - Project B: 20 pending items
     - Project C: 10 pending items
   - Call method and verify:
     - Returns 3 items
     - Sorted by `pending_count ASC`: [5, 10, 20]
     - Order: Project A, Project C, Project B

4. **Test projects with zero pending count**: Verify they are excluded
   - Create test database with:
     - Project A: 5 pending items
     - Project B: 0 pending items (all processed)
   - Call method and verify:
     - Returns only Project A
     - Project B is not in result

5. **Test deleted files exclusion**: Verify deleted files are not counted
   - Create test database with project
   - Add files: 3 normal, 2 deleted
   - Add chunks: 5 normal (from normal files), 3 from deleted files
   - Call method and verify:
     - `pending_count` counts only normal files/chunks
     - Deleted files and their chunks are excluded

6. **Test SQL query correctness**: Verify SQL query matches expected logic
   - Test files needing chunking: files with docstrings but no chunks
   - Test chunks needing vectorization: chunks with embeddings but no vector_id
   - Verify JOIN conditions are correct
   - Verify WHERE clauses exclude deleted files

7. **Test return type**: Verify return type matches specification
   - Call method and verify:
     - Returns `List[Dict[str, Any]]`
     - Each dict has keys: `project_id`, `root_path`, `pending_count`
     - All values are correct types (str, str, int)

### Step 2: Modify Vectorization Worker to Query Database for Projects

**File**: `code_analysis/core/vectorization_worker_pkg/processing.py`

**Action**:
- Modify `process_chunks` method to query database for all projects with files needing processing
- Remove all filesystem access (no `_enqueue_watch_dirs`, no watch_dirs)
- Worker works **only with database**

**Details**:
- Use new method `database.get_projects_with_vectorization_count()` to get sorted list
- For each project in sorted list:
  - Get files needing chunking: `database.get_files_needing_chunking(project_id)` (project-scoped, all files in project)
  - Process files using `_request_chunking_for_files()` method (already exists, no changes needed)
    - Method uses `DocstringChunker` to chunk files
    - Works with project_id from file record (no changes needed)
  - Get chunks needing vectorization: `database.get_non_vectorized_chunks(project_id)` (project-scoped, all chunks in project, datasets **EXCLUDED**)
    - **Note**: Method signature should be updated to **EXCLUDE `dataset_id` parameter** completely - datasets not processed
  - Process chunks using `process_embedding_ready_chunks()` (already exists, no changes needed)
  - Use project-scoped FAISS manager (index path: `faiss_dir / f"{project_id}.bin"`)
- Process projects sequentially (one by one)
- No filesystem scanning, no watch_dirs - pure database queries
- Worker works only at project level

**Checklist**:
- [ ] Modify `process_chunks` method to call `database.get_projects_with_vectorization_count()`
- [ ] Add loop over projects from sorted list
- [ ] For each project: get files needing chunking using `get_files_needing_chunking(project_id)`
- [ ] For each project: process files using `_request_chunking_for_files()` (no changes needed)
- [ ] For each project: get chunks using `get_non_vectorized_chunks(project_id)` (no dataset_id)
- [ ] For each project: process chunks using `process_embedding_ready_chunks()` (no changes needed)
- [ ] For each project: create FAISS manager with path `faiss_dir / f"{project_id}.bin"`
- [ ] Remove `_enqueue_watch_dirs` call completely
- [ ] Remove all filesystem access code
- [ ] Process projects sequentially (one by one)
- [ ] Add logging for project processing

**Tests**:
1. **Test project discovery from database**: Verify worker queries database for projects
   - Mock database with 2 projects
   - Mock `get_projects_with_vectorization_count()` to return test projects
   - Run one processing cycle
   - Verify method was called
   - Verify projects are processed in sorted order (by count)

2. **Test files processing per project**: Verify files are processed for each project
   - Create test database with 2 projects, each with files needing chunking
   - Mock `get_files_needing_chunking()` to return test files
   - Mock `_request_chunking_for_files()` to track calls
   - Run one processing cycle
   - Verify `_request_chunking_for_files()` called for each project
   - Verify correct project_id passed for each call

3. **Test chunks processing per project**: Verify chunks are processed for each project
   - Create test database with 2 projects, each with chunks needing vectorization
   - Mock `get_non_vectorized_chunks()` to return test chunks (no dataset_id parameter)
   - Mock `process_embedding_ready_chunks()` to track calls
   - Run one processing cycle
   - Verify `process_embedding_ready_chunks()` called for each project
   - Verify correct project_id and FAISS manager passed

4. **Test FAISS manager creation per project**: Verify manager created with correct path
   - Mock `FaissIndexManager` class
   - Run processing cycle with 2 projects
   - Verify `FaissIndexManager` instantiated twice (once per project)
   - Verify paths: `{faiss_dir}/{project_id1}.bin` and `{faiss_dir}/{project_id2}.bin`

5. **Test no filesystem access**: Verify `_enqueue_watch_dirs` is not called
   - Mock `_enqueue_watch_dirs` method
   - Run processing cycle
   - Verify `_enqueue_watch_dirs` was never called
   - Verify no filesystem operations (no `Path.exists()`, `Path.rglob()`, etc.)

6. **Test sequential processing**: Verify projects processed one by one
   - Create test database with 3 projects
   - Add delays in processing to track order
   - Run processing cycle
   - Verify projects processed in order (sorted by count)
   - Verify one project completes before next starts

7. **Test empty projects list**: Verify worker handles empty list gracefully
   - Mock `get_projects_with_vectorization_count()` to return empty list
   - Run processing cycle
   - Verify no errors occur
   - Verify worker continues to next cycle

8. **Test project processing errors**: Verify errors in one project don't stop others
   - Create test database with 3 projects
   - Make processing fail for middle project
   - Run processing cycle
   - Verify first project processed
   - Verify error logged for middle project
   - Verify third project still processed

### Step 3: FAISS Manager Management Strategy

**File**: `code_analysis/core/vectorization_worker_pkg/runner.py` and `base.py`

**Action**:
- FAISS manager is created dynamically for each project during processing
- Pass `faiss_dir` (base directory) instead of `faiss_index_path` to worker
- Worker creates FAISS manager for each project as needed

**Details**:
- Remove `faiss_index_path` parameter from `run_vectorization_worker()` - use `faiss_dir` instead
- Worker gets `faiss_dir` from storage paths
- For each project, create FAISS manager with path: `faiss_dir / f"{project_id}.bin"`
- FAISS manager is created/used per project during processing cycle
- Project-scoped indexes - each project has its own index file

**Checklist**:
- [ ] Remove `faiss_index_path` parameter from `run_vectorization_worker()` function signature
- [ ] Add `faiss_dir` parameter to `run_vectorization_worker()` function signature
- [ ] Update `VectorizationWorker.__init__()` to accept `faiss_dir` instead of `faiss_manager`
- [ ] Remove `faiss_manager` parameter from worker initialization
- [ ] Update processing loop to create FAISS manager dynamically for each project
- [ ] Use path format: `faiss_dir / f"{project_id}.bin"` for each project
- [ ] Ensure FAISS manager is created before processing each project
- [ ] Ensure FAISS manager is closed after processing each project (or reused)
- [ ] Update all function calls to pass `faiss_dir` instead of `faiss_index_path`
- [ ] Update type hints for all modified functions

**Tests**:
1. **Test function signature change**: Verify `run_vectorization_worker()` accepts `faiss_dir`
   - Test that function signature has `faiss_dir: str` parameter
   - Test that `faiss_index_path` parameter is removed
   - Test that calling with old signature fails

2. **Test FAISS manager dynamic creation**: Verify manager created per project
   - Mock `FaissIndexManager` class
   - Run processing cycle with 2 projects
   - Verify `FaissIndexManager` instantiated with correct paths:
     - `{faiss_dir}/{project_id1}.bin`
     - `{faiss_dir}/{project_id2}.bin`
   - Verify `vector_dim` passed correctly

3. **Test FAISS manager path format**: Verify paths use project-scoped format
   - Set `faiss_dir = Path("/test/faiss")`
   - Create test projects with known IDs
   - Run processing cycle
   - Verify manager created with paths like `/test/faiss/{project_id}.bin`
   - Verify no subdirectories (not `/test/faiss/{project_id}/{dataset_id}.bin`)

4. **Test FAISS manager lifecycle**: Verify manager created and used correctly
   - Mock `FaissIndexManager` to track creation/destruction
   - Run processing cycle with 2 projects
   - Verify manager created before processing each project
   - Verify manager used for chunk processing
   - Verify manager closed or reused appropriately

5. **Test worker initialization**: Verify worker accepts `faiss_dir`
   - Create worker with `faiss_dir` parameter
   - Verify worker stores `faiss_dir` correctly
   - Verify worker doesn't have `faiss_manager` at initialization
   - Verify worker creates manager when needed

6. **Test error handling**: Verify errors in manager creation don't crash worker
   - Make `FaissIndexManager` creation fail for one project
   - Run processing cycle
   - Verify error logged
   - Verify worker continues with next project

### Step 4: Update Worker Initialization for Universal Mode

**File**: `code_analysis/core/vectorization_worker_pkg/runner.py` and `base.py`

**Action**:
- **EXCLUDE `project_id` and `dataset_id` parameters** completely - they must not exist in function signatures
- Worker always operates in universal mode - processes all projects from database
- Remove watch_dirs dependency completely
- Update function signature and initialization logic
- **FAISS index sync check at startup**: For universal worker, check sync for all projects (or skip check and rely on rebuild in processing cycle)

**Details**:
- Remove `project_id` parameter from `run_vectorization_worker()` and `VectorizationWorker.__init__()`
- Worker always queries DB for all projects (universal mode only)
- `watch_dirs` is not used - worker works only with database
- No conditional logic - always universal mode
- **Database auto-creation** (required):
  - Before connecting to database, check if database file exists: `Path(db_path).exists()`
  - If database doesn't exist:
    1. Ensure parent directory exists: `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`
    2. Create database connection: `CodeDatabase(driver_config=driver_config)` - this will automatically create schema via `_create_schema()`
    3. Log info: "Database file not found, creating new database at {db_path}"
  - If database exists but is old/corrupted (or for test database):
    - **Simple approach**: Delete old database and create new one
    - Remove old database file: `Path(db_path).unlink()` if exists
    - Create new database: `CodeDatabase(driver_config=driver_config)`
    - Log info: "Removed old database, created new database at {db_path}"
  - **Note**: For test database, always start fresh - no migration needed, just delete and recreate
- **FAISS index sync check at startup** (required):
  - For universal worker, check sync for all projects at startup
  - Get all projects from database: `database.get_all_projects()`
  - For each project:
    1. Get project-scoped FAISS index path: `faiss_dir / f"{project_id}.bin"`
    2. Create FAISS manager for this project
    3. Check sync: `faiss_manager.check_index_sync(database, project_id=project_id)` (datasets **EXCLUDED**)
       - **Note**: Method signature should be updated to **EXCLUDE `dataset_id` parameter** completely - datasets not checked
    4. If sync fails (index and database vectors don't match):
       - Log warning with sync details
       - Rebuild index: `faiss_manager.rebuild_from_database(database, svo_client_manager, project_id=project_id)` (datasets **EXCLUDED**)
       - **Note**: Method signature should be updated to **EXCLUDE `dataset_id` parameter** completely - datasets not rebuilt
    5. Close FAISS manager
  - This ensures all project indexes are synchronized with database at startup
  - **Note**: This may be slow for many projects, but ensures consistency before worker starts processing

**Checklist**:
- [ ] Remove `project_id` parameter from `run_vectorization_worker()` function signature
- [ ] Remove `project_id` parameter from `VectorizationWorker.__init__()` method signature
- [ ] Remove `watch_dirs` parameter from both functions
- [ ] Update worker to always query database for all projects (universal mode)
- [ ] Remove all conditional logic based on `project_id`
- [ ] Implement database auto-creation logic
- [ ] Implement FAISS index sync check for all projects at startup
- [ ] Update function signatures and type hints
- [ ] Update docstrings to reflect universal mode
- [ ] Remove all `watch_dirs` references

**Tests**:
1. **Test function signatures**: Verify parameters removed correctly
   - Test `run_vectorization_worker()` doesn't accept `project_id` or `watch_dirs`
   - Test `VectorizationWorker.__init__()` doesn't accept `project_id` or `watch_dirs`
   - Test calling with old parameters fails with TypeError

2. **Test database auto-creation**: Verify database created if doesn't exist
   - Set up test with non-existent database path
   - Run worker initialization
   - Verify database file created
   - Verify schema initialized correctly
   - Verify log message about database creation

3. **Test database recreation**: Verify old database deleted and recreated
   - Create old/corrupted database file
   - Run worker initialization (test mode)
   - Verify old database deleted
   - Verify new database created
   - Verify log message about recreation

4. **Test FAISS index sync check for all projects**: Verify sync check runs for all projects
   - Create test database with 3 projects
   - Create FAISS indexes for 2 projects (one missing)
   - Run worker initialization
   - Verify `check_index_sync()` called for all 3 projects
   - Verify sync check uses correct index paths
   - Verify missing index handled gracefully

5. **Test FAISS index rebuild on sync failure**: Verify rebuild triggered when sync fails
   - Create test database with project
   - Create out-of-sync FAISS index
   - Mock `check_index_sync()` to return `False`
   - Run worker initialization
   - Verify `rebuild_from_database()` called
   - Verify rebuild uses correct `project_id` (no dataset_id)

6. **Test universal mode**: Verify worker queries database for all projects
   - Create test database with 3 projects
   - Mock `database.get_all_projects()` to return test projects
   - Run worker initialization
   - Verify `get_all_projects()` called
   - Verify all projects processed in sync check

7. **Test no watch_dirs usage**: Verify watch_dirs not used anywhere
   - Run `grep -r "watch_dirs"` in worker code - should return no results
   - Verify no filesystem scanning
   - Verify worker only uses database

8. **Test empty database handling**: Verify worker handles empty database
   - Create empty database (no projects)
   - Run worker initialization
   - Verify no errors occur
   - Verify sync check skipped (no projects)
   - Verify worker continues to processing cycle

9. **Test error handling**: Verify errors don't crash worker
   - Make database connection fail
   - Make sync check fail for one project
   - Run worker initialization
   - Verify errors logged
   - Verify worker continues (or exits gracefully)

### Step 5: FAISS Index Rebuild Strategy

**File**: `code_analysis/core/vectorization_worker_pkg/processing.py`

**Action**:
- After processing all projects in a cycle, rebuild FAISS indexes for all projects
- Use atomic file replacement: create in temp directory, then rename

**Details**:
- At end of each processing cycle (after processing all projects):
  - For each project:
    1. Get project-scoped FAISS index path: `faiss_dir / f"{project_id}.bin"`
    2. Create FAISS manager for this project
    3. Rebuild index from database for this project: `faiss_manager.rebuild_from_database(database, svo_client_manager, project_id=project_id)` (datasets **EXCLUDED**)
       - **Note**: Method signature should be updated to **EXCLUDE `dataset_id` parameter** completely - datasets not included in rebuild
       - Rebuild includes all chunks in project (project-scoped, datasets **EXCLUDED** from processing)
    4. Use atomic file replacement: create temp file, then rename (FAISS manager handles this)
- This ensures each project index is always consistent with database
- Each project maintains its own separate FAISS index file: `{faiss_dir}/{project_id}.bin`

**Checklist**:
- [ ] Add rebuild logic at end of processing cycle (after all projects processed)
- [ ] Loop over all projects from database
- [ ] For each project: get FAISS index path `faiss_dir / f"{project_id}.bin"`
- [ ] For each project: create FAISS manager
- [ ] For each project: call `rebuild_from_database()` with `project_id` only
- [ ] For each project: use atomic file replacement (FAISS manager handles this)
- [ ] Close FAISS manager after rebuild
- [ ] Add logging for rebuild operations
- [ ] Handle errors gracefully (one project failure doesn't stop others)

**Tests**:
1. **Test rebuild after processing cycle**: Verify rebuild runs after all projects processed
   - Create test database with 2 projects
   - Run one complete processing cycle
   - Verify rebuild called after all projects processed
   - Verify rebuild called for all projects

2. **Test rebuild per project**: Verify each project index rebuilt separately
   - Create test database with 3 projects
   - Mock `rebuild_from_database()` to track calls
   - Run processing cycle
   - Verify `rebuild_from_database()` called 3 times (once per project)
   - Verify correct `project_id` passed for each call (no dataset_id)

3. **Test FAISS index path in rebuild**: Verify correct paths used
   - Set `faiss_dir = Path("/test/faiss")`
   - Create test projects with known IDs
   - Run processing cycle
   - Verify rebuild uses paths: `/test/faiss/{project_id}.bin`
   - Verify no dataset-scoped paths

4. **Test atomic file replacement**: Verify rebuild uses atomic replacement
   - Mock file operations
   - Run rebuild for one project
   - Verify temp file created first
   - Verify old file replaced atomically (rename operation)
   - Verify no partial files left

5. **Test rebuild includes all chunks**: Verify rebuild processes all chunks in project
   - Create test database with project
   - Add chunks with vector_id (already vectorized)
   - Mock `rebuild_from_database()` to verify chunks processed
   - Run rebuild
   - Verify all chunks included (project-scoped, no dataset filtering)

6. **Test rebuild error handling**: Verify errors don't stop other projects
   - Create test database with 3 projects
   - Make rebuild fail for middle project
   - Run processing cycle
   - Verify rebuild attempted for all projects
   - Verify error logged for failed project
   - Verify other projects still rebuilt

7. **Test rebuild with empty index**: Verify rebuild works with missing index
   - Create test database with project
   - Ensure FAISS index file doesn't exist
   - Run rebuild
   - Verify index created
   - Verify all chunks added to index

8. **Test rebuild performance**: Verify rebuild doesn't block processing
   - Create test database with many projects
   - Measure rebuild time
   - Verify rebuild completes in reasonable time
   - Consider: rebuild could be async or batched in future

### Step 6: Update Server Startup to Start Single Universal Worker

**File**: `code_analysis/main.py`

**Action**:
- **Remove** the loop that starts one worker per project
- Start **only one universal worker** (no project_id parameter)
- Remove project discovery logic from vectorization worker startup (worker will discover projects from DB)
- Remove FAISS index rebuild loop (worker will rebuild index itself)
- **Add PID file check**: Before starting worker, check if PID file exists and if process is alive

**Details**:
  - In `startup_vectorization_worker` function:
  - **Database auto-creation** (before starting worker):
    - Check if database file exists: `Path(db_path).exists()`
    - **For test database**: Always start fresh - delete old database if exists and create new one
    - If old database exists:
      1. Remove old database file: `Path(db_path).unlink()` if exists
      2. Log info: "Removed old database at {db_path}"
    - Create new database:
      1. Ensure parent directory exists: `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`
      2. Create database connection to initialize schema: `CodeDatabase(driver_config=driver_config)` - this will automatically create schema
      3. Close database connection
      4. Log info: "Created new database at {db_path}"
    - **Note**: For test database, always start fresh - no migration needed, just delete and recreate
  - Remove loop over `project_ids`
  - Remove FAISS index rebuild loop (worker handles this)
  - Remove all project discovery logic
  - **PID file check** (before starting worker):
    - Define PID file path: `logs/vectorization_worker.pid` (or from config)
    - Check if PID file exists
    - If exists:
      - Read PID from file
      - Check if process with that PID is alive (using `os.kill(pid, 0)` or `psutil`)
      - If process is alive: log warning and skip worker startup (worker already running)
      - If process is dead: remove stale PID file and continue with startup
    - If PID file doesn't exist: proceed with worker startup
  - Start single universal worker: `run_vectorization_worker(db_path, faiss_dir, ...)` (no project_id, no faiss_index_path - use faiss_dir instead)
  - Worker will query DB to discover all projects automatically
  - Pass `faiss_dir` (base directory) instead of `faiss_index_path` - worker creates index paths dynamically for each project
  - **Write PID file** after worker starts: write worker PID to `logs/vectorization_worker.pid`
  - Update log file path generation: use `vectorization_worker.log` (no project_id in name)
  - Update worker registration in `WorkerManager`:
    - Change worker name from `f"vectorization_{project_id}"` to `"vectorization_universal"`
    - Update restart function (if exists) to start universal worker without project_id
    - Restart function will get all parameters from config (no closure variables needed)
  - **Update worker_launcher.py**:
    - File: `code_analysis/core/worker_launcher.py`
    - Function: `start_vectorization_worker()`
    - Changes:
      1. **Update function signature**:
         - Remove parameters: `project_id`, `faiss_index_path`
         - Add parameter: `faiss_dir: str` (base directory for FAISS indexes)
         - Keep other parameters: `db_path`, `vector_dim`, `svo_config`, `batch_size`, `poll_interval`, `worker_log_path`
      2. **Add PID file check** (before starting worker):
         - Define PID file path: `logs/vectorization_worker.pid` (or from config)
         - Check if PID file exists
         - If exists:
           - Read PID from file
           - Check if process with that PID is alive (using `os.kill(pid, 0)` or `psutil`)
           - If process is alive: return error `WorkerStartResult(success=False, message="Vectorization worker already running")`
           - If process is dead: remove stale PID file and continue
         - If PID file doesn't exist: proceed with worker startup
      3. **Update worker process creation**:
         - Change `run_vectorization_worker()` call:
           - Remove `project_id` from args
           - Replace `faiss_index_path` with `faiss_dir` in args
           - New signature: `run_vectorization_worker(db_path, faiss_dir, vector_dim, ...)`
      4. **Update worker registration**:
         - Change worker name from `f"vectorization_{project_id}"` to `"vectorization_universal"`
         - Update registration: `worker_manager.register_worker("vectorization", {"name": "vectorization_universal", ...})`
      5. **Write PID file** after worker starts:
         - Write worker PID to `logs/vectorization_worker.pid`
         - Handle errors gracefully (log warning if write fails)
  - **Update MCP Command `StartWorkerMCPCommand`**:
    - File: `code_analysis/commands/worker_management_mcp_commands.py`
    - Class: `StartWorkerMCPCommand`
    - Changes:
      1. **Update schema** (`get_schema()` method):
         - Remove `project_id` parameter from input schema
         - Keep other parameters: `worker_type`, `root_dir`, `poll_interval`, `batch_size`, `vector_dim`, `worker_log_path`
         - **Note**: `root_dir` is still needed for resolving storage paths (to get `faiss_dir` and `db_path`)
      2. **Update execute() method**:
         - Remove all logic for resolving `project_id`
         - For `worker_type == "vectorization"`:
           - Get storage paths: `resolve_storage_paths(config_data, config_path)`
           - Get `faiss_dir` from `storage.faiss_dir` (not `faiss_index_path`)
           - Get `db_path` from `storage.db_path`
           - Load SVO config from `config_data.get("code_analysis", {})`
           - Call `start_vectorization_worker()` with:
             - `db_path=str(db_path)`
             - `faiss_dir=str(faiss_dir)` (instead of `faiss_index_path`)
             - `vector_dim=vector_dim`
             - `svo_config=svo_config`
             - `batch_size=batch_size`
             - `poll_interval=poll_interval`
             - `worker_log_path=worker_log_path`
           - Remove all project_id related code
         - Update error messages to remove references to project_id
      3. **Update docstrings and metadata**:
         - Remove mentions of `project_id` from docstrings
         - Update command description to reflect universal worker mode
         - Update examples in metadata to show universal worker usage
- **File watcher startup remains unchanged** - no modifications needed

**Checklist**:
- [ ] Remove loop over `project_ids` in `startup_vectorization_worker()`
- [ ] Remove FAISS index rebuild loop (worker handles this)
- [ ] Remove all project discovery logic
- [ ] Add database auto-creation logic (delete old, create new for test)
- [ ] Add PID file check before starting worker
- [ ] Implement PID file read/write logic
- [ ] Start single universal worker with `faiss_dir` (not `faiss_index_path`)
- [ ] Update worker registration name to `"vectorization_universal"`
- [ ] Update log file path to `vectorization_worker.log`
- [ ] Update `worker_launcher.py` function signature and logic
- [ ] Update MCP Command schema and execute method
- [ ] Remove all `project_id` resolution logic from MCP command

**Tests**:
1. **Test single worker startup**: Verify only one worker started
   - Mock `multiprocessing.Process` to track starts
   - Run `startup_vectorization_worker()`
   - Verify only one process started
   - Verify no loop over projects

2. **Test PID file check - worker running**: Verify startup skipped if worker already running
   - Create PID file with valid running process PID
   - Run `startup_vectorization_worker()`
   - Verify worker not started
   - Verify warning logged
   - Verify PID file not overwritten

3. **Test PID file check - stale PID**: Verify stale PID file removed
   - Create PID file with non-existent PID
   - Run `startup_vectorization_worker()`
   - Verify stale PID file removed
   - Verify worker started
   - Verify new PID file created

4. **Test PID file check - no PID file**: Verify worker starts normally
   - Ensure no PID file exists
   - Run `startup_vectorization_worker()`
   - Verify worker started
   - Verify PID file created with correct PID

5. **Test database auto-creation**: Verify database created if doesn't exist
   - Set up test with non-existent database
   - Run `startup_vectorization_worker()`
   - Verify database created
   - Verify schema initialized
   - Verify log message

6. **Test database recreation**: Verify old database deleted and recreated (test mode)
   - Create old database file
   - Run `startup_vectorization_worker()` in test mode
   - Verify old database deleted
   - Verify new database created
   - Verify log message

7. **Test worker parameters**: Verify correct parameters passed to worker
   - Mock `run_vectorization_worker()` to track calls
   - Run `startup_vectorization_worker()`
   - Verify called with:
     - `db_path` (correct)
     - `faiss_dir` (not `faiss_index_path`)
     - No `project_id` parameter
   - Verify other parameters correct

8. **Test worker registration**: Verify worker registered with correct name
   - Mock `WorkerManager.register_worker()`
   - Run `startup_vectorization_worker()`
   - Verify registered with name `"vectorization_universal"`
   - Verify not registered with project-specific name

9. **Test MCP command schema**: Verify schema doesn't include `project_id`
   - Call `StartWorkerMCPCommand.get_schema()`
   - Verify `project_id` not in schema
   - Verify `root_dir` still in schema
   - Verify other parameters present

10. **Test MCP command execution**: Verify command starts universal worker
    - Mock `start_vectorization_worker()` to track calls
    - Execute MCP command with `worker_type="vectorization"`
    - Verify called with:
      - `faiss_dir` (not `faiss_index_path`)
      - No `project_id` parameter
    - Verify worker started successfully

11. **Test log file path**: Verify log file uses universal name
    - Run `startup_vectorization_worker()`
    - Verify log file path is `vectorization_worker.log`
    - Verify no project_id in log file name

### Step 7: Remove Filesystem Dependencies

**File**: `code_analysis/core/vectorization_worker_pkg/processing.py` and `watch_dirs.py`

**Action**:
- Remove `_enqueue_watch_dirs` call completely
- Remove watch_dirs dependency completely
- Remove watch_dirs from worker initialization
- Worker should not access filesystem - only database

**Details**:
- In `process_chunks`, remove `_enqueue_watch_dirs` call entirely
- Remove `watch_dirs` parameter from `VectorizationWorker.__init__()`
- Remove `watch_dirs` from `run_vectorization_worker()` function
- File watcher handles all filesystem operations
- Vectorization worker only processes data from database
- No filesystem access at all

**Checklist**:
- [ ] Remove `_enqueue_watch_dirs` call from `process_chunks` method
- [ ] Remove `watch_dirs` parameter from `VectorizationWorker.__init__()`
- [ ] Remove `watch_dirs` parameter from `run_vectorization_worker()` function
- [ ] Remove `watch_dirs` attribute from worker class
- [ ] Remove all filesystem scanning code
- [ ] Remove `_refresh_config` calls related to watch_dirs
- [ ] Run `grep -r "watch_dirs"` in worker code - should return no results
- [ ] Run `grep -r "_enqueue_watch_dirs"` - should return no results
- [ ] Verify no `Path.rglob()`, `Path.exists()` calls for file scanning

**Tests**:
1. **Test no _enqueue_watch_dirs call**: Verify method not called
   - Mock `_enqueue_watch_dirs` method
   - Run processing cycle
   - Verify `_enqueue_watch_dirs` never called
   - Verify no filesystem scanning

2. **Test no watch_dirs parameter**: Verify parameter removed from all functions
   - Test `VectorizationWorker.__init__()` doesn't accept `watch_dirs`
   - Test `run_vectorization_worker()` doesn't accept `watch_dirs`
   - Test calling with `watch_dirs` fails

3. **Test no filesystem access**: Verify no filesystem operations
   - Mock `Path` operations (`exists()`, `rglob()`, `read_text()`, etc.)
   - Run processing cycle
   - Verify no filesystem operations called
   - Verify only database operations

4. **Test code search**: Verify no watch_dirs references
   - Run `grep -r "watch_dirs"` in `vectorization_worker_pkg/` - should return empty
   - Run `grep -r "_enqueue_watch_dirs"` - should return empty
   - Verify no filesystem scanning code remains

5. **Test worker initialization**: Verify worker doesn't store watch_dirs
   - Create worker without `watch_dirs` parameter
   - Verify worker doesn't have `watch_dirs` attribute
   - Verify worker works correctly

6. **Test processing without filesystem**: Verify processing works with database only
   - Create test database with projects and files
   - Run processing cycle
   - Verify files processed from database
   - Verify no filesystem access needed
   - Verify chunks created correctly

### Step 8: Add Logging

**Files**: All modified files

**Action**:
- Add appropriate logging for:
  - Project discovery from database
  - Project processing order (sorted by count)
  - FAISS index rebuild operations
  - Worker status checks

**Details**:
- Use INFO level for successful operations
- Use WARNING for non-critical failures
- Use ERROR for critical failures
- Log project processing: "Processing project {project_id} with {count} pending items"
- Log FAISS index rebuild: "Rebuilding FAISS index for project {project_id}"

**Checklist**:
- [ ] Add logging for project discovery: "Found {count} projects with pending items"
- [ ] Add logging for project processing order: "Processing projects in order: {list}"
- [ ] Add logging for each project: "Processing project {project_id} with {count} pending items"
- [ ] Add logging for files chunking: "Requesting chunking for {count} files in project {project_id}"
- [ ] Add logging for chunks vectorization: "Processing {count} chunks for project {project_id}"
- [ ] Add logging for FAISS index rebuild: "Rebuilding FAISS index for project {project_id}"
- [ ] Add logging for FAISS sync check: "Checking FAISS index sync for project {project_id}"
- [ ] Add logging for errors with appropriate levels
- [ ] Add logging for worker status: "Worker cycle complete: {stats}"
- [ ] Verify all log messages use correct log levels

**Tests**:
1. **Test project discovery logging**: Verify log message when projects discovered
   - Mock logger
   - Run processing cycle with 3 projects
   - Verify INFO log: "Found 3 projects with pending items"
   - Verify projects listed in log

2. **Test project processing logging**: Verify log for each project processed
   - Mock logger
   - Run processing cycle with 2 projects
   - Verify INFO log for each project: "Processing project {id} with {count} pending items"
   - Verify count matches actual pending items

3. **Test FAISS rebuild logging**: Verify log for rebuild operations
   - Mock logger
   - Run processing cycle with rebuild
   - Verify INFO log: "Rebuilding FAISS index for project {id}"
   - Verify log includes project ID

4. **Test error logging**: Verify errors logged with correct level
   - Create test scenario with error (e.g., database connection failure)
   - Run processing cycle
   - Verify ERROR log for critical errors
   - Verify WARNING log for non-critical errors
   - Verify log includes error details

5. **Test worker cycle logging**: Verify cycle completion logged
   - Mock logger
   - Run complete processing cycle
   - Verify INFO log at cycle end with statistics
   - Verify includes: processed count, errors count, cycle duration

6. **Test log levels**: Verify correct log levels used
   - Test INFO for normal operations
   - Test WARNING for non-critical issues
   - Test ERROR for critical failures
   - Test DEBUG for detailed debugging (if applicable)

### Step 9: Remove Old Code and Verify Cleanup

**Files**: All modified files

**Action**:
- Remove all old code related to single-project mode
- Remove all conditional logic based on project_id
- Remove all watch_dirs usage
- Verify no legacy code remains

**Details**:
- Search and remove all references to:
  - `project_id` parameter in function signatures (except database queries)
  - `watch_dirs` parameter and usage
  - Conditional checks like `if project_id is None` or `if project_id`
  - Single-project mode logic
  - Per-project worker loops in main.py
  - Per-project FAISS manager creation in main.py
- Verify no dead code remains:
  - No unused imports
  - No commented-out code
  - No unused variables
  - No conditional branches that are never executed
- Run code analysis tools (mypy, flake8) to catch any issues

**Checklist**:
- [ ] Search and remove all `project_id` parameters (except database queries)
- [ ] Search and remove all `watch_dirs` parameters and usage
- [ ] Search and remove all conditional checks: `if project_id`, `if project_id is None`
- [ ] Remove all single-project mode logic
- [ ] Remove all per-project worker loops in `main.py`
- [ ] Remove all per-project FAISS manager creation in `main.py`
- [ ] Remove all commented-out legacy code
- [ ] Remove all unused imports
- [ ] Remove all unused variables
- [ ] Run `grep -r "project_id.*="` to verify no old parameter usage
- [ ] Run `grep -r "watch_dirs"` to verify no filesystem access
- [ ] Run `mypy` and fix all type errors
- [ ] Run `flake8` and fix all style errors
- [ ] Verify no dead code remains

**Tests**:
1. **Test code search for project_id**: Verify no old parameter usage
   - Run `grep -r "project_id.*="` in worker code
   - Verify only database query methods have `project_id` parameter
   - Verify no worker initialization with `project_id`

2. **Test code search for watch_dirs**: Verify no filesystem access
   - Run `grep -r "watch_dirs"` in worker code
   - Verify no results (or only in file watcher, not vectorization worker)

3. **Test mypy type checking**: Verify all type hints correct
   - Run `mypy` on all modified files
   - Fix all type errors
   - Verify no `Any` types where specific types possible
   - Verify function signatures match implementations

4. **Test flake8 style checking**: Verify code style correct
   - Run `flake8` on all modified files
   - Fix all style errors
   - Verify code follows PEP 8

5. **Test no dead code**: Verify no unreachable code
   - Review all conditional branches
   - Verify all branches reachable
   - Remove any unreachable code
   - Verify no `pass` statements in production code

6. **Test no unused imports**: Verify all imports used
   - Run import analysis
   - Remove unused imports
   - Verify all imports necessary

7. **Test function signatures**: Verify all signatures updated
   - Check all modified functions
   - Verify parameters removed correctly
   - Verify return types correct
   - Verify type hints updated

8. **Test docstrings**: Verify all docstrings updated
   - Check all modified functions
   - Verify docstrings reflect universal mode
   - Verify no mentions of removed parameters
   - Verify examples updated

### Step 10: Testing

**Action**:
- Test with new project discovered after server startup
- Verify worker processes projects from database
- Verify worker processes files correctly
- Verify chunks and vectors are created
- Verify FAISS index rebuild works correctly
- Verify no old code paths are executed

**Test Scenarios**:
1. Create new project after server startup → worker should process it in next cycle
2. Multiple projects in database → worker should process all, sorted by count
3. FAISS index rebuild → verify atomic replacement works for each project index
4. Database-only operation → verify no filesystem access (no watch_dirs, no project_id)
5. Worker startup → verify no project_id parameters are used or required
6. Code verification → verify no old single-project mode code exists
7. Project-scoped indexes → verify each project maintains its own index file
8. **Database doesn't exist** → verify worker creates database automatically and continues startup
9. **Empty database** → verify worker handles gracefully (no projects to process, continues to next cycle)

**Checklist**:
- [ ] Test new project discovered after server startup
- [ ] Test worker processes projects from database
- [ ] Test worker processes files correctly
- [ ] Test chunks and vectors are created
- [ ] Test FAISS index rebuild works correctly
- [ ] Test no old code paths are executed
- [ ] Test multiple projects processed correctly
- [ ] Test project-scoped indexes work correctly
- [ ] Test database auto-creation
- [ ] Test empty database handling
- [ ] Test error handling and recovery
- [ ] Test PID file protection
- [ ] Test MCP command works correctly
- [ ] Test worker registration
- [ ] Test all edge cases

**Tests**:
1. **Integration test: New project after startup**
   - Start server with empty database
   - Add new project via file watcher
   - Wait for processing cycle
   - Verify project discovered by worker
   - Verify files chunked
   - Verify chunks vectorized
   - Verify FAISS index created

2. **Integration test: Multiple projects**
   - Create database with 3 projects
   - Start worker
   - Verify all projects processed
   - Verify processing order (sorted by count)
   - Verify each project has own FAISS index

3. **Integration test: FAISS index rebuild**
   - Create database with project and vectors
   - Manually corrupt FAISS index
   - Start worker
   - Verify index rebuilt on startup
   - Verify all vectors in index
   - Verify index matches database

4. **Integration test: Database-only operation**
   - Start worker
   - Monitor filesystem operations
   - Verify no filesystem access (except FAISS index files)
   - Verify all data from database
   - Verify no watch_dirs used

5. **Integration test: Worker startup**
   - Start worker
   - Verify no project_id required
   - Verify worker queries database for projects
   - Verify universal mode active
   - Verify PID file created

6. **Integration test: Code verification**
   - Run code analysis tools
   - Verify no old single-project mode code
   - Verify no dataset_id references
   - Verify no watch_dirs usage
   - Verify all tests pass

7. **Integration test: Project-scoped indexes**
   - Create database with 2 projects
   - Process both projects
   - Verify index files: `{faiss_dir}/{project_id1}.bin` and `{faiss_dir}/{project_id2}.bin`
   - Verify indexes contain correct vectors
   - Verify no cross-project contamination

8. **Integration test: Database auto-creation**
   - Start worker with non-existent database
   - Verify database created
   - Verify schema initialized
   - Verify worker continues normally

9. **Integration test: Empty database**
   - Start worker with empty database
   - Verify no errors
   - Verify worker continues to next cycle
   - Verify graceful handling

10. **Integration test: Error handling**
    - Create test scenarios with various errors
    - Verify errors logged correctly
    - Verify worker recovers from errors
    - Verify other projects still processed

11. **Integration test: PID file protection**
    - Start worker (creates PID file)
    - Try to start second worker
    - Verify second worker not started
    - Verify warning logged
    - Kill first worker
    - Verify stale PID file removed
    - Verify new worker can start

12. **Integration test: MCP command**
    - Call MCP command `start_worker` with `worker_type="vectorization"`
    - Verify no project_id required
    - Verify universal worker started
    - Verify worker registered correctly
    - Verify PID file created

13. **Performance test: Large number of projects**
    - Create database with 10+ projects
    - Start worker
    - Measure processing time
    - Verify all projects processed
    - Verify reasonable performance

14. **Stress test: Concurrent operations**
    - Start worker
    - Add new projects while worker running
    - Verify new projects discovered in next cycle
    - Verify no race conditions
    - Verify data consistency

## Implementation Order

1. **Step 0**: **EXCLUDE all dataset parameters** from vectorization worker (change FAISS paths, datasets **EXCLUDED** from code)
2. **Step 1**: Add database method `get_projects_with_vectorization_count()` (foundation)
3. **Step 4**: Update worker initialization for universal mode (remove project_id, watch_dirs, change faiss_index_path to faiss_dir)
4. **Step 2**: Modify processing loop to query DB for all projects (remove filesystem access)
5. **Step 3**: Update FAISS manager management (dynamic creation per project, use faiss_dir)
6. **Step 5**: Implement FAISS index rebuild strategy (rebuild each project index atomically)
7. **Step 6**: Update server startup to start single universal worker
8. **Step 7**: Remove filesystem dependencies (remove watch_dirs completely)
9. **Step 8**: Add logging throughout
10. **Step 9**: Remove old code and verify cleanup (critical - ensure no legacy code remains)
11. **Step 10**: Test and verify

## Edge Cases to Handle

1. **FAISS index rebuild failure**: If rebuild fails, keep old index
   - Solution: Only delete old index after successful rebuild and rename

2. **Large number of projects**: Single worker processing all projects might be slow
   - Solution: Process projects sorted by count (smallest first) - faster feedback
   - Future: Can still scale to multiple workers if needed (each handles subset)

3. **FAISS index directory doesn't exist**: Need to create it
   - Solution: Create directory structure when creating temp index file

4. **Database connection issues**: Worker should handle DB unavailability gracefully
   - Solution: Already implemented - worker has retry logic and backoff

5. **Project deleted while processing**: Worker should skip deleted projects
   - Solution: Check project exists in DB before processing (query validates this)

6. **No projects in database**: Worker should handle gracefully
   - Solution: Log info message and continue to next cycle
   - **Database doesn't exist or is old**: Worker should delete old database (if exists) and create new one
     - Solution: Check if database file exists before connecting
     - If exists: delete old database file (`Path(db_path).unlink()`)
     - Create parent directory and initialize new database (schema will be created automatically by `CodeDatabase.__init__()`)
     - Log info message about database creation
     - Continue with worker startup (empty database is valid - no projects to process yet)
     - **Note**: For test database, always start fresh - no migration needed

7. **Temp directory full**: FAISS rebuild might fail
   - Solution: Check disk space before rebuild, log error if insufficient

8. **Multiple vectorization workers**: PID file check prevents multiple workers
   - Solution: PID file check in `main.py` and `worker_launcher.py` ensures only one universal worker runs
   - If PID file exists and process is alive, worker startup is skipped
   - If PID file exists but process is dead, stale PID file is removed and worker starts
   - **Note**: Only universal worker is supported - no project-specific workers

## Files to Modify

1. `code_analysis/core/database/projects.py` or `chunks.py` - Add `get_projects_with_vectorization_count()` method
2. `code_analysis/core/vectorization_worker_pkg/processing.py` - Modify to query DB for all projects, remove filesystem access, add FAISS rebuild logic, remove old conditional code
3. `code_analysis/core/vectorization_worker_pkg/base.py` - Remove project_id parameter, remove watch_dirs, remove all conditional logic
4. `code_analysis/core/vectorization_worker_pkg/runner.py` - Remove project_id parameter, remove watch_dirs, change faiss_index_path to faiss_dir, remove old initialization code
5. `code_analysis/main.py` - Start single universal worker (no project_id), remove project discovery, remove FAISS rebuild loop, remove all per-project loops, update worker registration name, update log file path, update restart function (if exists)
6. `code_analysis/core/vectorization_worker_pkg/watch_dirs.py` - May be removed or significantly simplified (no longer used by worker)
7. `code_analysis/core/worker_launcher.py` - Update `start_vectorization_worker()` function:
   - Remove `project_id`, `faiss_index_path` parameters
   - Add `faiss_dir` parameter
   - Add PID file check before starting worker (same logic as in main.py)
   - Update worker registration name to `"vectorization_universal"`
   - Update function call to `run_vectorization_worker()` without project_id
8. `code_analysis/commands/worker_management_mcp_commands.py` - Update `StartWorkerMCPCommand`:
   - Remove `project_id` parameter from schema (universal worker only)
   - Update command to start only universal worker
   - Remove all project-specific worker logic

## Code Cleanup Checklist

After implementation, verify the following old code is completely removed:

- [ ] All `project_id` parameters in worker functions (except database query methods)
- [ ] All calls to `get_faiss_index_path()` (replace with `faiss_dir / f"{project_id}.bin"`)
- [ ] All `watch_dirs` parameters and usage
- [ ] All conditional checks: `if project_id`, `if project_id is None`
- [ ] All loops over `project_ids` in `main.py`
- [ ] All per-project FAISS manager creation in main.py
- [ ] All `_enqueue_watch_dirs` calls
- [ ] All project discovery logic in worker startup
- [ ] All single-project mode code paths
- [ ] All commented-out legacy code
- [ ] All unused imports related to old functionality
- [ ] Run `grep -r "project_id.*="` to verify no old parameter usage
- [ ] Run `grep -r "watch_dirs"` to verify no filesystem access
- [ ] Update type hints for all modified functions (remove project_id, add faiss_dir)
- [ ] Update docstrings to reflect universal mode (remove references to "single project", **EXCLUDE** all dataset mentions)
- [ ] Verify FAISS index paths use format `{faiss_dir}/{project_id}.bin` (datasets **EXCLUDED** from path structure)
- [ ] Run `mypy` and `flake8` to catch any issues

## Performance Considerations

- **Single worker for all projects**: May become bottleneck with many projects
  - Solution: Process projects sorted by count (smallest first) - provides faster feedback
  - Future enhancement: Can still run multiple universal workers (each handles subset)
  
- **FAISS index rebuild**: Rebuilding all project indexes each cycle may be slow
  - Solution: Rebuild only at end of cycle (not per project)
  - Optimization: Could rebuild only changed project indexes in future if needed
  - Current approach: Simple and ensures consistency for all projects

## Available Database Methods

The following methods already exist in `code_analysis/core/database/projects.py` and can be used:

1. **Get project ID by path**:
   - `database.get_project_id(root_path: str) -> Optional[str]`
   - Returns project ID for given root path, or None if not found

2. **Get project by ID** (includes root_path):
   - `database.get_project(project_id: str) -> Optional[Dict[str, Any]]`
   - Returns project record with fields: `id`, `root_path`, `name`, `comment`, `updated_at`
   - Returns None if project not found

3. **Get all projects**:
   - `database.get_all_projects() -> List[Dict[str, Any]]`
   - Returns all projects with fields: `id`, `root_path`, `name`, `comment`, `updated_at`

These methods provide bidirectional conversion between project ID and root path.

## Notes

- **ONLY UNIVERSAL MODE** - no single-project mode, no backward compatibility, no optional parameters
- **File watcher remains unchanged** - no modifications to file watcher code needed
- Both workers are independent processes that work only with the database
- Single universal vectorization worker automatically discovers new projects through database queries
- No inter-process communication needed - database is the only shared resource
- Workers are daemon processes, so they'll be cleaned up if parent dies
- **Vectorization worker has no filesystem dependencies** - works purely with database
- **No watch_dirs** - worker does not access filesystem at all
- **No project_id parameters** - worker always processes all projects from database
- **Project-scoped FAISS indexes** - each project maintains its own index file: `{faiss_dir}/{project_id}.bin`
- **Processing order**: Projects sorted by pending count (smallest first) for faster feedback
- **FAISS index path**: `{faiss_dir}/{project_id}.bin` (datasets **EXCLUDED** from path structure)
- **Datasets EXCLUDED** - vectorization worker **completely EXCLUDES** dataset concept from all processing, paths, and method calls
- **watch_dirs in config**: Keep `watch_dirs` in config file (file watcher needs them), but vectorization worker ignores them
- **MCP Command `start_worker`**: **Universal worker only** - `project_id` and `dataset_id` parameters **EXCLUDED** completely, always starts universal worker
- **PID file protection**: Before starting worker, check if PID file exists and if process is alive. If alive, skip startup. If dead, remove stale PID file and start worker.
