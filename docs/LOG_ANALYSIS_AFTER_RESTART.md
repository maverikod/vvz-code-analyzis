# Log analysis after server restart

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Restart

- **Command:** `python -m code_analysis.cli.server_manager_cli --config config.json restart`
- **Result:** `started pid=122657` (previous pid 91472 stopped)
- **Logs:** `logs/mcp_server.log`, `logs/file_watcher.log`, `logs/indexing_worker.log`, `logs/vectorization_worker.log`

## Findings

### 1. Shutdown and startup (file_watcher.log)

- **02:59:45** — `Received signal 15, stopping all workers...` → `Server shutdown: stopping all workers` → `Stopping all workers...`
- **02:59:57** — File watcher worker logging configured; `Starting multi-project file watcher worker | pid=122775 | watch_dirs=1 | scan_interval=60s`
- **02:59:58** — `Database is now available`; watch directories init; projects discovered: `620f7fc4...` (cli_app), `928bcf10...` (vast_srv)
- **02:59:59** — `Counting total files on disk across all projects...`

Shutdown was clean (SIGTERM); new file watcher process started and reconnected to DB and watch dirs.

### 2. Indexing worker (mcp_server.log / indexing_worker.log)

- **CYCLE #1:** 1 project with **3491 pending** items (vast_srv); 5 files needing chunking; processing started.
- **Index errors (same files repeatedly):**
  - `test_ftp_commands.py` line 168: **invalid syntax** (RPC index_file error)
  - `update_test_files.py` line 30: **unexpected character after line continuation character**
- **Success:** e.g. `fix_commands_simple.py` → chunker 7 docstrings → chunks persisted; `test_enhanced_integration.py` indexed.
- **CYCLE #2:** `files_total_at_start (needs_chunking=1)=10645` — large backlog of files needing indexing.

Conclusion: Indexing worker is running; a few test files in vast_srv have syntax errors and fail index_file every cycle; the rest are processed. Backlog ~10.6k files with `needs_chunking=1`.

### 3. Vectorization worker (vectorization_worker.log)

- Chunker calls to `https://localhost:8009/api/jsonrpc` return HTTP 200.
- Example: `[FILE 27] Chunker returned 7 chunks in 19.249s` → `Persisting 7 chunks to database...`
- Log level DEBUG (httpcore/httpx) is verbose; INFO shows normal chunk+embed flow.

Conclusion: Vectorization and chunker are working; chunking latency ~19s for one file in the sample.

### 4. File watcher queue before restart

- Just before shutdown: many `[CHANGED FILE]` for vast_srv (e.g. `docker_logs_command.py`, `queue_health_command.py`, `ollama_memory_command.py`) with `UPDATE files SET needs_chunking = 1`.
- Files are queued with Unix mtime (e.g. `1757945441.7560005`); `last_modified` is written correctly for comparison.

### 5. New logging (from WORKER_AND_DB_STATUS_ANALYSIS)

- **per_project** in `[SCAN END]`: Present in code; after the next full scan cycle the active `file_watcher.log` will show lines like `per_project: <project_id> new=N changed=M deleted=K | ...`.
- **update_indexes START/END**: Not seen in the captured tail (no update_indexes run in the restart window).

## Recommendations

1. **Syntax errors in test_data:** Fix or exclude:
   - `test_data/vast_srv/test_ftp_commands.py` (line 168 — invalid syntax)
   - `test_data/vast_srv/update_test_files.py` (line 30 — line continuation character)
   so they stop failing index_file every cycle and reduce log noise.

2. **Backlog:** ~10.6k files with `needs_chunking=1`; indexing and vectorization are progressing but slowly. Consider running `update_indexes` for a full re-index only when needed (it will mark all processed files for chunking and delete chunks; see WORKER_AND_DB_STATUS_ANALYSIS.md).

3. **Vectorization latency:** 19s for 7 chunks for one file suggests chunker/embedding or network latency; already documented in VECTORIZATION_SLOWDOWN_ROOT_CAUSES.md / CHUNKER_TIMING_BENCHMARK.md.

4. **Log location:** Main daemon stderr → `logs/mcp_server.log`; worker-specific logs in `logs/file_watcher.log`, `logs/indexing_worker.log`, `logs/vectorization_worker.log` (paths from config).
