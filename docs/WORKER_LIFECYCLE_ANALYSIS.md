# Worker Lifecycle Analysis: File Watcher, Indexer, Vectorizer

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes what each background worker reads, writes, and in what order. It clarifies responsibility boundaries and data flow so that "who writes where" is unambiguous.

---

## 1. Overview

| Worker         | Role |
|----------------|------|
| **File watcher** | Scans filesystem, discovers new/changed/deleted files and projects; enqueues files for processing by setting flags and writing/updating `files` rows. |
| **Indexer**      | Consumes files with `needs_chunking=1`, runs full file index (AST, CST, entities, code_content) in the DB driver, then clears `needs_chunking`. Does **not** create chunks or embeddings. |
| **Vectorizer**  | (1) Chunks files that have no `code_chunks` (or `needs_chunking=1`), writes `code_chunks` with `embedding_vector`. (2) For chunks that already have `embedding_vector` but no `vector_id`, adds vectors to FAISS and writes `vector_id` back. |

**Important:** Only the **vectorizer** writes to `code_chunks`. The indexer only updates `files`, AST/CST/entities/code_content; it does not touch `code_chunks`.

---

## 2. File Watcher

**Where it runs:** Separate process (`MultiProjectFileWatcherWorker`), started by `WorkerLifecycleManager.start_file_watcher_worker`. Connects to DB via socket (DatabaseClient), does **not** spawn the DB worker.

### 2.1 What it reads

- **Config:** `watch_dirs` (list of directories to scan), `scan_interval`, `version_dir`, `ignore_patterns`.
- **Filesystem:** Recursive scan under each watch dir; file mtime/size; presence of `projectid` to discover projects.
- **Database:** For each project, existing `files` rows (path, `last_modified`) to compute delta (new / changed / deleted).

### 2.2 What it writes

- **`files`**
  - **New or changed files (queue phase):**  
    `INSERT OR REPLACE INTO files (path, lines, last_modified, has_docstring, project_id, created_at, updated_at)`  
    then  
    `UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?`  
    So: new/changed files get `needs_chunking = 1`.
  - **Deleted files:**  
    `UPDATE files SET deleted = 1, updated_at = julianday('now') WHERE path = ? AND project_id = ?`  
    (only when `version_dir` is set).
- **`projects`**  
  When a new project is discovered (projectid under a watch dir):  
  `INSERT INTO projects (id, root_path, name, comment, watch_dir_id, updated_at)`.  
  Then it starts a background run of **update_indexes** for that project (see below).
- **`watch_dirs` / `watch_dir_paths`**  
  Updated from config when syncing watch directories.
- **`file_watcher_stats`**  
  `INSERT INTO file_watcher_stats (...)` per cycle (scanned, added, changed, deleted, errors).

### 2.3 New project and update_indexes

When the file watcher creates a new project, it runs **update_indexes** (UpdateIndexesMCPCommand) in a background thread. That command:

- Adds/updates rows in `files` via `add_file`.
- For each analyzed file calls `mark_file_needs_chunking(file_path, project_id)`.

`mark_file_needs_chunking` (in `database/files.py`):

- Deletes existing chunks: `DELETE FROM code_chunks WHERE file_id = ?`
- Updates file: `UPDATE files SET updated_at = julianday('now') WHERE id = ?`
- It does **not** set `needs_chunking = 1` (that is only set by the file watcher in `queue_changes`).

So for a **new project**, files may have no `code_chunks` but still have `needs_chunking = 0`. The **vectorizer** still picks them for chunking because it selects files with **no** `code_chunks` (see below). The **indexer** only selects `needs_chunking = 1`; those files get that flag when the file watcher later sees them as new/changed in its scan and runs `queue_changes`.

---

## 3. Indexer (Indexing Worker)

**Where it runs:** Separate process, started by `WorkerLifecycleManager.start_indexing_worker`. Uses DatabaseClient (socket) to call the DB driver's **index_file** RPC.

### 3.1 What it reads

- **Database:**  
  - Projects with pending work:  
    `SELECT DISTINCT project_id FROM files WHERE (deleted=0 OR deleted IS NULL) AND needs_chunking=1`.  
  - Per project, batch of files:  
    `SELECT id, path, project_id FROM files WHERE project_id=? AND (deleted=0 OR deleted IS NULL) AND needs_chunking=1 ORDER BY updated_at ASC LIMIT ?`.

So the indexer **only** consumes files that have **`needs_chunking = 1`** (set by the file watcher).

### 3.2 What it does (no direct DB writes from worker)

For each selected file the worker calls the driver RPC **index_file(file_path, project_id)**. The **driver** (in its process):

1. Resolves `projects.root_path` for `project_id`.
2. Calls **CodeDatabase.update_file_data(file_path, project_id, root_path)**:
   - Finds `file_id` by path.
   - **clear_file_data(file_id):** deletes all data for that file: classes, methods, functions, imports, issues, usages, code_content, code_content_fts, ast_trees, cst_trees, **code_chunks**, vector_index.
   - Updates `files`: `last_modified`, `updated_at`.
   - Calls **UpdateIndexesMCPCommand._analyze_file** (force=True) to repopulate AST, CST, entities, code_content (and related tables).
3. On success: **clears the flag**  
   `UPDATE files SET needs_chunking = 0 WHERE path = ? AND project_id = ?`.

So the indexer (via the driver) **writes**:

- **`files`:** `last_modified`, `updated_at` (during update_file_data), then `needs_chunking = 0`.
- **Entity and content tables:** `ast_trees`, `cst_trees`, `classes`, `functions`, `methods`, `imports`, `usages`, `code_content`, `code_content_fts`, `vector_index`, and any cleanup from `clear_file_data` (including **deletion** of `code_chunks` for that file).

The indexer **does not** insert or update `code_chunks`; it only deletes them as part of `clear_file_data` before re-indexing the file.

### 3.3 Stats

- **indexing_worker_stats:** Cycle start/end and counts (e.g. `start_indexing_cycle`, `update_indexing_stats`) are written by the driver/DB layer when the worker runs its cycle (via `database.execute(...)` from the worker process using DatabaseClient).

---

## 4. Vectorizer (Vectorization Worker)

**Where it runs:** Separate process, started by `WorkerLifecycleManager.start_vectorization_worker`. Uses DatabaseClient and creates per-project FAISS managers. Does **not** spawn the DB worker.

### 4.1 What it reads

- **Database:**  
  - Projects with pending work (files needing chunking **or** chunks needing `vector_id`):  
    - Files with docstrings (or classes/functions/methods with docstrings) and **no** row in `code_chunks`, **or**
    - Chunks with `embedding_vector IS NOT NULL` and `vector_id IS NULL`.  
  - Per project, for **Step 1 (chunking):**  
    `SELECT f.id, f.path, f.project_id FROM files f WHERE f.project_id=? AND (deleted=0 OR deleted IS NULL) AND (has_docstring/classes/functions/methods docstring conditions) AND (needs_chunking=1 OR NOT EXISTS (SELECT 1 FROM code_chunks cc WHERE cc.file_id = f.id)) LIMIT 30`.  
  - For **Step 2 (assign vector_id):**  
    Chunks with `embedding_vector IS NOT NULL AND vector_id IS NULL` (in `batch_processor.process_embedding_ready_chunks`).
- **Filesystem:** Only to **read file content** when chunking (Step 1); path comes from DB.

### 4.2 Step 1: Chunking (and writing chunks with embeddings)

- Selects up to 30 files per project that need chunking (`needs_chunking=1` **or** no `code_chunks`).
- For each file: reads file from disk, parses AST, calls **DocstringChunker.process_file**.
- **DocstringChunker** calls external chunker/embedding services and then **add_code_chunk** (DatabaseClient or CodeDatabase) to insert/update rows in **`code_chunks`** with at least: `file_id`, `project_id`, content fields, **`embedding_vector`**, **`embedding_model`**, etc. (no `vector_id` yet).
- After successfully chunking a file, the vectorizer clears the flag:  
  `UPDATE files SET needs_chunking = 0 WHERE id = ?`.

So **Step 1** **writes**:

- **`code_chunks`:** INSERT/REPLACE with `embedding_vector` and `embedding_model` set; `vector_id` remains NULL.
- **`files`:** `needs_chunking = 0` for the chunked file.

Only the **vectorizer** (via DocstringChunker + add_code_chunk) writes **new** chunk rows with embeddings. The indexer never does that.

### 4.3 Step 2: Assigning vector_id (FAISS + DB update)

- **process_embedding_ready_chunks** (in `batch_processor.py`):  
  Selects chunks where `embedding_vector IS NOT NULL AND vector_id IS NULL`, loads embedding from DB, adds to the project's FAISS index, then runs:  
  `UPDATE code_chunks SET vector_id = ?, embedding_model = ? WHERE id = ?`.

So **Step 2** **writes**:

- **FAISS index file** (per project): new vectors appended.
- **`code_chunks`:** `vector_id` and `embedding_model` updated for processed chunks.

### 4.4 Order of steps and why "vectorized" count lags

- In each cycle, per project, the vectorizer runs **Step 1** (chunking up to 30 files) and only after that runs **Step 2** (process_embedding_ready_chunks).
- So chunks created in Step 1 get `vector_id` only when Step 2 runs, i.e. **after** the current chunking batch for that project is done. Until then they have `embedding_vector` but `vector_id IS NULL` and are not counted as "vectorized" in status queries that use `vector_id IS NOT NULL`.
- If you want the "vectorized" count to grow more frequently, Step 2 could be called after each file (or every N files) instead of only after the full batch of 30 files.

### 4.5 Stats

- **vectorization_stats:** Cycle and counts (e.g. chunks_total_at_start, files_vectorized) are written at cycle start and updated during/after the cycle (via `database.execute(...)` from the worker).

---

## 5. Summary Table: Who Writes What

| Table / store       | File watcher | Indexer (via driver) | Vectorizer |
|---------------------|--------------|------------------------|------------|
| **files**           | INSERT/REPLACE; UPDATE needs_chunking=1; UPDATE deleted=1 | UPDATE last_modified, updated_at; UPDATE needs_chunking=0 | UPDATE needs_chunking=0 |
| **projects**        | INSERT (new project) | — | — |
| **watch_dirs** etc. | Yes (from config) | — | — |
| **file_watcher_stats** | INSERT | — | — |
| **ast_trees, cst_trees, classes, functions, methods, imports, usages, code_content, code_content_fts, vector_index** | — | Yes (via clear_file_data + _analyze_file) | — |
| **code_chunks**     | — | Only **deleted** (in clear_file_data) | **INSERT/REPLACE** (embedding_vector, embedding_model); **UPDATE** (vector_id, embedding_model) |
| **indexing_worker_stats** | — | Yes (cycle stats) | — |
| **vectorization_stats** | — | — | Yes |
| **FAISS index**     | — | — | Yes (add vectors, update code_chunks.vector_id) |

---

## 6. End-to-end flow (one file)

1. **File watcher** sees new/changed file → INSERT/REPLACE into `files`, then `UPDATE files SET needs_chunking = 1`.
2. **Indexer** sees `needs_chunking = 1` → calls **index_file** → driver runs **update_file_data** (clear_file_data → _analyze_file) → driver sets **needs_chunking = 0**. File now has AST/CST/entities/code_content, and **no** code_chunks (they were deleted in clear_file_data).
3. **Vectorizer** sees file with docstrings and **no** code_chunks (and/or needs_chunking=1) → **Step 1:** chunking → **add_code_chunk** writes `code_chunks` with `embedding_vector`; vectorizer sets **needs_chunking = 0** for that file. Then **Step 2:** process_embedding_ready_chunks selects chunks with embedding but no vector_id → FAISS add → **UPDATE code_chunks SET vector_id**, embedding_model.

So: **File watcher** enqueues; **indexer** refreshes structure and clears needs_chunking; **vectorizer** is the only one that writes chunks and embeddings and then assigns vector_id in FAISS and DB.
