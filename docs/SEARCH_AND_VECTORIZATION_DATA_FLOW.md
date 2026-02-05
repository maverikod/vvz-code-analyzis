# Search and Vectorization: Data Flow and Why Fulltext Was Empty

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

- **Vectorization worker** only writes to `code_chunks` (and FAISS). It does **not** write to `code_content` / `code_content_fts`.
- **Indexing worker** fills **code_content** and **code_content_fts** in the background when files have `needs_chunking = 1` (same effect as `update_file_data` for one file). It runs in a separate process, before the vectorization worker (startup order). Manual **update_indexes** remains for full project refresh or recovery.
- **Fulltext search** reads from `code_content_fts` (FTS5). That table is filled by the **indexing worker** (for files with `needs_chunking = 1`), by **update_indexes**, or by **update_file_data_atomic** when saving a file via CST.
- **Semantic search** uses `code_chunks` + FAISS index. Data is written by the vectorization worker (after chunking). Until all chunks have `vector_id` and the FAISS index is rebuilt, semantic results can be incomplete.

So: after creating/editing files, the **indexing worker** will update fulltext for those files (within a cycle). For a full project refresh use **update_indexes**. Vectorization runs in the background and fills semantic search over time (or use **revectorize** if you need to force refresh).

---

## Why vectorizer seems "not to trigger automatically"

It **does** trigger automatically. The delay is the **cycle interval**.

- **Vectorization worker** runs a cycle every **30 seconds** (configurable `poll_interval`, default 30). At the start of each cycle it finds projects that have:
  - files with a docstring (or class/function/method with docstring) and **no** rows in `code_chunks` for that file, or
  - chunks that have `embedding_vector` but **no** `vector_id`.
- It then requests chunking for those files (creates `code_chunks`) and assigns `vector_id` / FAISS. So new files are picked up within **one or two cycles** (up to ~30–60 s after the files appear in the DB).
- **File watcher** runs every **60 seconds** (`scan_interval`). It sets `needs_chunking = 1` for new/changed files. The vectorization worker selects files where **(`needs_chunking = 1` OR the file has no rows in `code_chunks`)** and the file (or its classes/functions/methods) has a docstring (see `processing.py`: `get_files_needing_chunking`). So new files are picked up as soon as they are in `files` with docstring data; `needs_chunking` speeds up re-chunking after edits.

If you check **check_vectors** or **semantic_search** immediately after creating files, you may see 0 chunks or 0% vectorized. Wait for the next cycle (e.g. 30–40 s) and recheck; chunks and then vectors will appear without calling **update_indexes** or **revectorize**.

---

## What the vectorization worker does

1. Finds files that have a docstring (module/class/function/method) and either `needs_chunking = 1` (set by file watcher) or no rows in `code_chunks` yet.
2. Extracts docstrings, gets embeddings (via chunker/embedding service), writes rows into **code_chunks** (with `embedding_vector`, `embedding_model`).
3. Assigns `vector_id` and adds vectors to the project’s **FAISS** index.
4. Periodically **rebuilds FAISS** from DB for all projects.

It does **not** touch `code_content` or `code_content_fts`.

---

## Where data lives

| Table / index       | Filled by                    | Used by           |
|---------------------|-----------------------------|-------------------|
| **code_chunks**     | Vectorization worker        | Semantic search   |
| **FAISS index**     | Vectorization worker        | Semantic search   |
| **code_content**    | Indexing worker, update_indexes, update_file_data_atomic | (internal) |
| **code_content_fts**| same as code_content        | Fulltext search   |

The **indexing worker** processes files with `needs_chunking = 1` (set by the file watcher), calls the driver RPC `index_file` (same logic as `update_file_data`), and clears `needs_chunking` after success. So fulltext is updated automatically when files change; **update_indexes** is for full refresh or when the indexing worker is disabled.

---

## Why fulltext returned 0 results

- `code_content_fts` can be empty if the **indexing worker** has not yet run a cycle for the project, or **update_indexes** was never run.
- File watcher sets `needs_chunking = 1` for new/changed files. The **indexing worker** picks those up (via driver `index_file` RPC) and fills `code_content` / `code_content_fts`, then clears `needs_chunking`. The vectorization worker only updates `code_chunks` and FAISS.

**Fix:** Ensure the indexing worker is running; wait for its next cycle (e.g. default 30 s), or run **update_indexes** for the project for an immediate full refresh.

---

## Why semantic seemed “not to work”

- At first check, **check_vectors** reported `chunks_pending_vectorization: 5` and `vectorization_percentage: 53.85`.
- The vectorization worker runs in cycles (with ~30 s pause). Until it finishes processing all chunks and rebuilding FAISS, semantic search can miss some content or use a stale index.
- After the worker completed: `chunks_pending_vectorization: 0`, `vectorization_percentage: 100`, and **semantic_search** returned 5 results for "run command".

So semantic search **does** work once the worker has processed all chunks and rebuilt FAISS.

---

## Commands to verify

- **get_worker_status** (worker_type = indexing): PID, log path, last cycle stats (files indexed, etc.). Same for `vectorization` and `file_watcher`.
- **check_vectors** (project_id): total_chunks, chunks_with_vector, chunks_pending_vectorization, vectorization_percentage.
- **view_worker_logs** (log_path = logs/indexing_worker.log, worker_type = indexing, tail = 80): see what the indexing worker is doing. Same for vectorization_worker.log and vectorization.
- **update_indexes** (project_id): full refresh of entities and **code_content** / **code_content_fts** (use when indexing worker is disabled or for recovery).
- **fulltext_search** / **semantic_search**: after indexing and vectorization have run, both should return results when data exists.
