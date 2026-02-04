# Order of Implementation, Risks, Success Criteria

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## 0. Flags: single flag, no conflicts

There is **one** flag for "file needs background work" in table `files`:

| Flag | Meaning | Set by | Cleared by | Read by |
|------|---------|--------|------------|---------|
| **needs_chunking** (0/1) | File changed; needs indexing (AST/code_content) and/or chunking (code_chunks) | File watcher, `mark_file_needs_chunking` | **Indexer** (after successful index), **Vectorization** (after successful chunking) | Indexer (select `= 1`), Vectorization (select `= 1` OR no rows in `code_chunks`) |

- **No other flags** for this workflow (no `needs_indexing`, no duplicate semantics). The `deleted` flag is separate (soft delete).
- **Conflict**: Both indexer and vectorization clear `needs_chunking` to 0. If vectorization clears it **before** the indexer runs, the indexer will never select that file (it only selects `needs_chunking = 1`), so the file gets chunks but no fulltext/code_content.
- **Mitigation**: Run the **indexer before vectorization** in the cycle (e.g. startup order: indexing worker → vectorization worker; or ensure indexer processes files with `needs_chunking = 1` before vectorization does). Then indexer clears the flag after index; vectorization still sees the file via "no code_chunks" and chunks it, then clears the flag. No second flag required if ordering is guaranteed.
- **Optional future**: If ordering cannot be guaranteed, introduce a second flag (e.g. `needs_indexing`) so indexer selects/clears only that, and vectorization selects/clears only `needs_chunking`; file watcher would set both.

## 1. Order of Implementation

1. **Phase A**: RPC "index_file" in driver + `DatabaseClient.index_file` (and optionally clear `needs_chunking` in driver).
2. **Phase B**: Add `indexing_worker_pkg` (base, processing, runner).
3. **Phase C**: Wire lifecycle (WorkerLifecycleManager, WorkerManager, main.py startup, config if any).
4. **Phase D**: MCP start/stop and status for `indexing`.
5. **Phase E**: Docs and tests.

---

## 2. Risks and Mitigations

| Risk | Mitigation |
|------|-------------|
| **Driver loading app code** | If the driver imports `code_analysis.core.database.files` or `CodeDatabase`, ensure the driver's process has the same Python env and that there are no circular imports. Keep the "index_file" handler in the driver minimal and call one function that receives (connection, file_path, project_id). Project root is obtained from the DB (projects.root_path) when needed. |
| **Concurrent indexing and vectorization** | Both read/clear the same flag `needs_chunking`. Indexer must run **before** vectorization for the same file so that after indexer clears the flag, vectorization still selects the file by "no code_chunks". Ensure startup order and/or cycle order: indexing worker before vectorization worker. |
| **Long-running update_file_data** | Indexing one large file can take time; batch size and poll_interval limit how many files are processed per cycle. If needed, add a per-file timeout or skip files over N lines (optional). |

---

## 3. Success Criteria

- When a file is created or changed on disk and the file watcher sets `needs_chunking = 1`, within a few cycles (e.g. 2 × poll_interval) the indexing worker has run "index_file" for that file and fulltext search returns the new content without manual `update_indexes`.
- Starting/stopping the indexing worker via MCP or server config works; worker runs in a separate process and writes to its own log file.
- Existing behaviour (vectorization, file watcher, CST save, manual update_indexes) remains unchanged.
