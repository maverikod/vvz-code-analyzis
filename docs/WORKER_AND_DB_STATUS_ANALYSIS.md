# Worker and database status analysis (5-minute interval)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

This document analyses two snapshots of `get_database_status` and `get_worker_status` taken ~5 minutes apart to explain the observed drop in "indexed" files and total chunks, and to document how metrics are defined and what can cause them to decrease.

## Snapshot comparison (summary)

| Metric | T1 (02:44–02:45) | T2 (02:50) | Delta |
|--------|-------------------|------------|--------|
| **Files total** | 13,992 | 14,064 | +72 |
| **Files indexed** (needs_chunking=0) | 4,413 | 3,538 | **−875** |
| **Files needing_indexing** (needs_chunking=1) | 9,618 | 10,527 | +909 |
| **Files chunked** (have rows in code_chunks) | 66 | 48 | −18 |
| **Chunks total** | 272 | 152 | **−120** |
| **Chunks vectorized** | 72 | 66 | −6 |
| **DB size** | 54.1 MB | 54.1 MB | 0 |

**Workers:** Same PIDs (file_watcher 91575, vectorization 91569, indexing 91563); all running. Indexing worker current file changed from `cli_app/runner.py` to `vast_srv/update_test_files.py`.

## How metrics are defined

- **indexed:** `COUNT(*) FROM files WHERE (deleted=0 OR deleted IS NULL) AND (needs_chunking=0 OR needs_chunking IS NULL)` (see `worker_status_mcp_commands.py`).
- **needing_indexing:** `COUNT(*) FROM files WHERE (deleted=0 OR deleted IS NULL) AND needs_chunking=1`.
- **chunked:** Files that have at least one row in `code_chunks`.
- **total chunks:** `COUNT(*) FROM code_chunks`; vectorized = `vector_id IS NOT NULL`.

So a decrease in "indexed" and an increase in "needing_indexing" means many files were set to `needs_chunking=1`. A decrease in total chunks means chunk rows were deleted (per file or in bulk).

## Root cause analysis

### 1. What sets needs_chunking=1

- **File watcher** (`file_watcher_pkg/processor.py`): for each file that is **new** or **changed** (by mtime vs DB `last_modified`), it calls logic that ends with `UPDATE files SET needs_chunking = 1` for that file. It does **not** set needs_chunking=1 for all files on every scan; only new/changed.
- **mark_file_needs_chunking** (`database/files.py`): sets needs_chunking=1 and **deletes all chunks** for that file. Used by:
  - `code_mapper_mcp_command.py` (update_indexes): after indexing each file it calls `database.mark_file_needs_chunking(rel_path, project_id)`, so every file processed by update_indexes is marked for chunking and loses its chunks.
  - Other call sites in `files.py` (e.g. after update_file_data, restore, etc.).

So a large drop in "indexed" and in "chunks" in a short window is consistent with:

- **update_indexes (code_mapper)** having been run over a large set of files: each file is indexed and then marked for chunking (needs_chunking=1) and its chunks are deleted. That would:
  - Decrease "indexed" (more files with needs_chunking=1).
  - Decrease "chunked" and "total chunks" (chunks deleted per file).
- Alternatively, a **bug or one-off** that set needs_chunking=1 (or deleted chunks) for many files.

### 2. last_modified and false "changed" detection

The file watcher treats a file as "changed" when:

- `db_mtime` is None, or  
- `abs(disk_mtime - float(db_mtime)) > 0.1`

(`processor.py` compute_delta). So if `last_modified` in the DB were stored in a different scale (e.g. Julian day ~2.46e6) while the scanner uses Unix mtime (~1.7e9), every file would be considered changed and would get needs_chunking=1 on each scan. In the current code, the file watcher writes **Unix mtime** when it inserts/updates files; if all files were only ever written by the watcher, format should be consistent. If some import or other path wrote `last_modified` in another format, that could cause a mass "changed" effect. Recommendation: ensure `files.last_modified` is always stored as Unix timestamp and that any reader used in the watcher path (e.g. `get_project_files` → `File.last_modified`) exposes the same scale for comparison.

### 3. Project-level picture

- **vast_srv:** indexed dropped from 4,416 to 3,530 (−886); file_count rose from 13,950 to 14,022 (+72). So the drop in global "indexed" is almost entirely in vast_srv, plus 72 new files (consistent with file watcher adding files).
- **cli_app:** small project; indexed went to 100% (42/42), chunked 100%, vectorized ~51%.

So the dominant effect is in vast_srv: many files moved from "indexed" to "needing_indexing" and chunks decreased; at the same time the watcher added 72 new files.

## Root cause (determined)

The only code path that **both** sets `needs_chunking=1` for many files **and** deletes their chunks is **`mark_file_needs_chunking`**. It is called in bulk only from:

1. **`UpdateIndexesMCPCommand.execute`** (update_indexes) — after each file it processes: `database.mark_file_needs_chunking(rel_path, project_id)`. So a run over N files causes N files to get the flag and have their chunks deleted.
2. **File watcher auto-indexing** — when the file watcher **creates a new project** (no row in `projects` for that `project_id` and no row for that `root_path`), it runs **update_indexes** in a background thread for that project (`multi_project_worker.py` ~691–740). So all Python files in the newly created project are processed by update_indexes → each gets `mark_file_needs_chunking` → chunks deleted, needs_chunking=1.

The file watcher **does not** call `mark_file_needs_chunking`; it only does `UPDATE files SET needs_chunking = 1` (no chunk deletion). So mass chunk deletion can only come from update_indexes (manual or auto).

**Conclusion:** The drop (indexed −875, chunks −120) was caused by **update_indexes** running over a large set of files — either:
- **Explicit:** A user or script called the `update_indexes` command (e.g. via MCP) for vast_srv, or
- **Automatic:** The file watcher treated vast_srv as a **newly created project** (e.g. project row was missing after DB restore, or first scan with empty `projects` table, or path mismatch so lookup by `root_path` failed) and started auto-indexing, which runs full update_indexes for that project.

To confirm in logs: search for:
- `[update_indexes START]` and `[update_indexes END]` — include `trigger=manual` or `trigger=auto_indexing`
- `[AUTO_INDEXING]` — logged when file watcher starts update_indexes for a newly created project (before background thread)
- `Auto-created project` and `[AUTO_INDEXING] Started background thread` — same event

## Conclusions

1. **Cause of the 5-minute drop:** update_indexes (manual or via file watcher auto-indexing for a “new” project) ran over many files; each call to `mark_file_needs_chunking` set needs_chunking=1 and deleted that file’s chunks.
2. **last_modified mismatch:** Would only cause the file watcher to set needs_chunking=1 for many files; it does not delete chunks. Normalization to Unix was still implemented to avoid mass false “changed” and to keep semantics correct.
3. **Recommendations (implemented):**
   - **update_indexes logging:** Start and end of `update_indexes` are logged with `[update_indexes START]` / `[update_indexes END]` (project_id, files_total / files_processed, errors). See `code_mapper_mcp_command.py`.
   - **last_modified as Unix:** In the file watcher path, `last_modified` is normalized to Unix in `processor.py` via `_last_modified_to_unix()`. This handles DB values stored as Unix, or exposed as datetime/Julian from the client, so comparison with scan mtime is correct and mass false "changed" is avoided.
   - **Per-project scan counts:** Each scan logs `per_project: project_id new=N changed=M deleted=K | ...` in `[SCAN END]` so mass re-marking per project is visible. See `multi_project_worker.py`.

## Why files are classified as "new" vs "changed"

In `processor.compute_delta`, for each file from the scan:

- **New:** `db_files_map.get(file_path_str)` is `None` — the path from the scanner is **not present** in the DB. So the file is treated as newly added on disk.
- **Changed:** The path **is** in `db_files_map`, but `db_mtime is None` or `abs(disk_mtime - db_mtime) > 0.1`. So the file is considered modified.

**Path format must match.** The scanner uses `path_key = normalized.absolute_path` (absolute resolved string from `normalize_file_path`). The DB stores `files.path` as absolute path (see `database/files.py` add_file). So both use the same convention. If they ever differed (e.g. relative in DB, absolute in scan, or different resolution of symlinks), existing files would not be found in `db_files_map` and would be classified as **new** (high "new" count, zero "changed" for those).

**Observed case (vast_srv):** Logs showed `new=0 changed=490` — paths matched, but almost all files were "changed" because `last_modified` from the client was interpreted as Julian day instead of Unix timestamp, so `abs(mtime - db_mtime) > 0.1` for every file. Fix: use `get_project_file_rows()` (raw `last_modified`) in the file watcher so comparison is Unix vs Unix; `_last_modified_to_unix()` remains as fallback when raw rows are not available.

**Summary:**

| Classification | Condition | Typical cause if mass |
|----------------|-----------|------------------------|
| **new**        | Path not in DB | Path format mismatch (scanner path ≠ DB path), or file really new. |
| **changed**    | Path in DB, mtime diff > 0.1s | `last_modified` scale mismatch (e.g. Julian vs Unix), or file really modified. |

## References

- `code_analysis/commands/worker_status_mcp_commands.py` — get_database_status queries (indexed, chunked, chunks).
- `code_analysis/core/file_watcher_pkg/processor.py` — compute_delta (mtime vs last_modified), _queue_file_for_processing (sets needs_chunking=1).
- `code_analysis/core/database/files.py` — mark_file_needs_chunking (sets flag and deletes chunks).
- `code_analysis/commands/code_mapper_mcp_command.py` — update_indexes calls mark_file_needs_chunking after each file.
