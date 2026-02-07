# Log analysis: four 5-minute polls and root cause of indexed/chunk drops

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Poll summary (2026-02-07)

| Metric        | T1 (03:14) | T2 (03:19) | T3 (03:25) | T4 (03:30) |
|---------------|------------|------------|------------|------------|
| Files total   | 14 320     | 14 372     | 14 446     | 14 520     |
| Indexed       | 3 255      | 2 865      | 3 032      | 3 693      |
| Needing index | 11 065     | 11 509     | 11 415     | 10 828     |
| Chunked files | 60         | 46         | 58         | 63         |
| Chunks total  | 204        | 142        | 187        | 243        |
| Vectorized    | 66         | 66         | 66         | 66         |

Intervals: T1→T2 indexed −390, chunks −62; T2→T3 indexed +167, chunks +45; T3→T4 indexed +661, chunks +56.

## Log findings

### 1. File watcher: 490 files “changed” every scan

In `logs/file_watcher.log`:

- **03:02:51** `[SCAN END]` … `per_project: 620f7fc4... new=0 changed=1 deleted=0 | 928bcf10... new=0 changed=490 deleted=37`
- **03:15:37** `[SCAN END]` … `per_project: 620f7fc4... new=0 changed=1 deleted=0 | 928bcf10... new=0 changed=490 deleted=37`

So at every scan the file watcher treats **490 files in vast_srv** (and 1 in cli_app) as “changed” and runs `UPDATE files SET needs_chunking = 1` for each. That explains:

- **Indexed drop (e.g. T1→T2 −390):** Those files move from “indexed” (needs_chunking=0) to “needing_indexing” (needs_chunking=1).
- **Chunk drop (e.g. −62):** The indexing worker then runs `index_file` on batches of these files. Each `index_file` calls `update_file_data` in the driver, which calls **`clear_file_data(file_id)`** and thus **deletes all code_chunks for that file**. So as index_file runs over dozens of previously chunked files, total chunk count drops until vectorization recreates chunks.

### 2. Why 490 files are always “changed”

Comparison is done in `compute_delta`: disk `mtime` vs DB `last_modified`. The file watcher uses `get_project_files()` from the **DatabaseClient**, which builds **File** objects via `_parse_timestamp(last_modified)`. In the client, `_parse_timestamp` treats the value as **Julian day**. But `files.last_modified` is stored as **Unix timestamp** by the file watcher (and by the driver in `update_file_data`). So:

- DB holds e.g. `1757945441.0` (Unix).
- Client parses it as Julian → wrong datetime.
- `_last_modified_to_unix(datetime)` returns `datetime.timestamp()` → still wrong.
- Comparison with real disk mtime then almost always differs → file “changed”.

So the file watcher was effectively re-marking almost all files in vast_srv as changed every scan.

### 3. No AUTO_INDEXING or update_indexes in window

Searched logs for `[AUTO_INDEXING]`, `[update_indexes START]`, `[update_indexes END]`: **no matches**. So the drops in this run are **not** from auto-indexing for a new project or from a manual update_indexes; they are from the file watcher + indexing worker loop above.

## Fix implemented

1. **`get_project_file_rows(project_id, include_deleted=False)`** added to the database client. It returns a list of dicts with **raw** `id`, `path`, `last_modified` (no conversion to File, no Julian parsing). So `last_modified` stays as Unix float from the driver.

2. **File watcher processor** now prefers `get_project_file_rows()` when available. So `compute_delta` gets Unix `last_modified` and compares it correctly to disk mtime; only truly new/changed files are marked as changed.

3. **Fallback:** If `get_project_file_rows` is not available, the processor still uses `get_project_files()` and `_last_modified_to_unix()` (so existing deployments keep working, but may still see mass “changed” until they use a client that exposes the raw rows).

## Conclusions

- **Cause of indexed and chunk drops in the four polls:** File watcher marks ~490 files as changed every scan because `last_modified` was compared in the wrong scale (Julian vs Unix). That sets needs_chunking=1 and reduces “indexed”. The indexing worker then runs index_file on those files; each index_file clears file data including code_chunks, so total chunks drop until vectorization recreates them.
- **Fix:** Use raw project file rows (Unix `last_modified`) in the file watcher so only real changes are queued. After restart with the new code, [SCAN END] per_project should show small “changed” counts (only actually modified files).

## References

- `code_analysis/core/file_watcher_pkg/processor.py` — compute_delta, get_project_file_rows / get_project_files usage.
- `code_analysis/core/database_client/client_api_files.py` — get_project_file_rows, get_project_files.
- `code_analysis/core/database/files.py` — update_file_data → clear_file_data → DELETE FROM code_chunks.
- `docs/WORKER_AND_DB_STATUS_ANALYSIS.md` — root cause and recommendations.
