# Indexing worker: how it sees work and why it might "sleep"

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

The indexer **only** learns about work from the **same database** that the file watcher writes to. Work = rows in `files` with `needs_chunking = 1`. If the indexer sleeps for 30 seconds, it is because in that cycle it saw **no** such rows (or no rows in the batch). The chain from "files on disk" to "indexer processes them" is: **file watcher scan → DB `files` + `needs_chunking=1` → indexer query → batch → index_file → driver clears `needs_chunking`**.

---

## 1. How the indexer sees that there is work

The indexer does **not** look at the filesystem. It only talks to the **database** via the **database driver** (RPC over socket).

Each cycle it:

1. Connects to the driver: `DatabaseClient(socket_path)` → driver uses one SQLite file (same for all workers).
2. Runs:
   - `SELECT COUNT(*) FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1` → **files_total_at_start**.
   - `SELECT DISTINCT project_id FROM files WHERE ... AND needs_chunking = 1` → **project_ids**.
3. For each `project_id`, runs:
   - `SELECT id, path, project_id FROM files WHERE project_id = ? AND ... AND needs_chunking = 1 ORDER BY updated_at ASC LIMIT ?` (batch_size, e.g. 5).
4. For each row: calls `database.index_file(path, project_id)`. On success, the **driver** sets `needs_chunking = 0` for that file.

So: **the only source of "work" for the indexer is the table `files` with `needs_chunking = 1`**. If that count is 0 (or the batch returns 0 rows), the indexer does no work in that cycle and then sleeps **poll_interval** (default 30s). If it did work, it sleeps 2s and continues.

---

## 2. Who sets `needs_chunking = 1`?

Only the **file watcher** (and in some code paths, the vectorization worker or other code that marks files for re-chunking). The important path is:

- **File watcher** (e.g. `file_watcher_pkg/processor.py`):
  - Scans watch directories (only `.py` after the recent change; see `CODE_FILE_EXTENSIONS` in `constants.py`).
  - For each new/changed file: `compute_delta` → `queue_changes` → `_queue_file_for_processing`.
  - There it:
    - Inserts/updates the row in `files` (path, project_id, etc.).
    - Runs `UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?`.

So **unprocessed files** that the indexer can see are exactly those that:

1. Have been **scanned** by the file watcher (under a watch dir, matching `CODE_FILE_EXTENSIONS`).
2. Have been **written** to `files` and **marked** with `needs_chunking = 1` by the file watcher.

If "огромное число необработанных файлов" are **on disk** but **not** in `files` with `needs_chunking = 1`, the indexer will **not** see them and will sleep 30s when it finds no work.

---

## 3. Same database for file watcher and indexer

Both workers get **the same** `db_path` from `main.py`:

- `startup_indexing_worker`: `db_path = storage.db_path` → `worker_manager.start_indexing_worker(db_path=...)`.
- `startup_file_watcher_worker`: `db_path = storage.db_path` → `worker_manager.start_file_watcher_worker(db_path=...)`.

`storage` comes from `resolve_storage_paths(config)` in both cases. So they use the **same** SQLite file. The indexer connects to it **via the database driver** (socket); the file watcher also uses `DatabaseClient(socket_path)` with the same logical DB. So they see the same `files` table and the same `needs_chunking` values.

---

## 4. Why the indexer might "sleep" despite many files on disk

Possible reasons:

| Cause | Explanation |
|-------|-------------|
| **Files not yet in DB** | File watcher has not yet scanned those directories, or scan interval is long (e.g. 60s). Until the watcher runs and writes `files` + `needs_chunking=1`, the indexer has nothing to do. |
| **Files not matching scanner** | Only paths with extension in `CODE_FILE_EXTENSIONS` are scanned (now only `.py`). Other files are never added to `files` by the watcher. |
| **Different DB path** | If in some deployment the file watcher and indexer were started with different configs (different `db_path`), they would use different DBs; the indexer would not see the watcher’s `needs_chunking=1`. In the standard main.py startup this does not happen. |
| **All work in same cycle** | Indexer takes only **batch_size** files per project per cycle (e.g. 5). So it might clear 5 × N projects in one cycle; if the next cycle runs and the watcher hasn’t added new work yet, **files_total_at_start** can be 0 → 30s sleep. So "огромное число" is processed over many cycles (2s sleep each), with possible 30s sleeps when the queue is temporarily empty. |
| **Path / project_id mismatch** | File watcher stores **absolute** path in `files.path`. Indexer queries by `project_id` and uses `path` as returned. If project_id or path differed between watcher and indexer logic, rows could be missed; in the current code both use the same DB and same schema, so this is unlikely unless there is a bug in project_id or path. |
| **deleted = 1** | Indexer filters `(deleted = 0 OR deleted IS NULL)`. If files were marked deleted, they are ignored. |

---

## 5. Chain diagram (how indexer "sees" work)

```
[ Disk: .py files ]
        │
        ▼
[ File watcher: scan_directory (CODE_FILE_EXTENSIONS) ]
        │
        ▼
[ compute_delta → queue_changes → _queue_file_for_processing ]
        │
        ▼
[ DB: INSERT/UPDATE files, then UPDATE files SET needs_chunking = 1 ]
        │
        ▼
[ Indexer cycle: SELECT ... WHERE needs_chunking = 1 ]
        │
        ▼
[ Batch of files → index_file(path, project_id) ]
        │
        ▼
[ Driver: index file, then UPDATE files SET needs_chunking = 0 ]
```

If the indexer sleeps 30s, the break is either: (1) no rows with `needs_chunking = 1` in this cycle (empty queue), or (2) DB/driver/connection problem so the query fails or returns nothing.

---

## 6. What to check when "indexer sleeps with many unprocessed files"

1. **Logs**  
   In indexing worker logs, look for:
   - `[CYCLE #N] files_total_at_start (needs_chunking=1)=X`  
   If X is 0, the indexer correctly sees no work in the DB.
2. **Same DB**  
   Confirm file watcher and indexer use the same `db_path` (e.g. from config / startup logs).
3. **File watcher activity**  
   Check file watcher logs: are the directories with "огромное число" files being scanned? Are files being added/updated and marked for chunking?
4. **Direct DB check**  
   Query the same DB the driver uses:  
   `SELECT COUNT(*), project_id FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1 GROUP BY project_id;`  
   If this shows many rows but the indexer still reports `files_total_at_start=0`, the indexer might be talking to a different DB or the driver might be using a different path.

With this chain, "почему индексатор спит при наличии огромного числа необработанных файлов" is answered by: **он смотрит только в таблицу `files` с `needs_chunking=1`; если там пусто в этом цикле — он спит 30 секунд. Работа появляется только после того, как file watcher просканировал файлы и выставил им `needs_chunking=1`.**
