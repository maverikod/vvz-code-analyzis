# Lifecycle and pipeline analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

This document describes who does what and in what order: database driver, indexing worker, vectorization worker, file watcher, and how chunks/vectors get into the database. It clarifies that the **chunker returns chunks, vectors, and tokens in one request** and where that data flows.

---

## 1. Startup order (main.py)

1. **Database driver** — started first (background thread). Opens SQLite via proxy; other workers connect to it via socket.
2. **Indexing worker** — separate process. Polls DB for files with `needs_chunking=1`, calls driver `index_file` RPC.
3. **Vectorization worker** — separate process. Polls DB for projects with pending chunking/vectorization work.
4. **File watcher** — separate process. Scans watch_dirs, computes new/changed/deleted files, updates DB and sets `needs_chunking=1` for changed files.

---

## 2. Who writes what to the database

| Data | Written by | When |
|------|------------|------|
| **files** (path, last_modified, has_docstring, needs_chunking) | File watcher (add/update); indexing driver (after index_file clears needs_chunking) | Scan; index_file success |
| **ast_trees, cst_trees** | Indexing path only (`_analyze_file` via driver) | index_file → update_file_data → _analyze_file |
| **classes, functions, methods, imports, code_content** | Indexing path only (`_analyze_file`) | Same as above |
| **code_chunks** (chunk_text, embedding_vector, token_count, vector_id) | **Vectorization worker only** (DocstringChunker → add_code_chunk) | Step 1 of vectorization cycle (chunking) |
| **code_chunks.vector_id** | Vectorization worker (batch_processor) | Step 2: add to FAISS, then UPDATE code_chunks |
| **FAISS index** | Vectorization worker (FaissIndexManager) | Step 2 and rebuild at end of cycle |

**Important:** The **indexing worker never calls the chunker and never inserts into `code_chunks`**. It only runs AST/CST/entity extraction and **deletes** existing chunks (see below).

---

## 3. Indexing worker (indexing_worker_pkg)

**What it does:**

1. Polls DB: `SELECT ... FROM files WHERE needs_chunking = 1` (per project, batch_size files).
2. For each file: calls **driver RPC `index_file(file_path, project_id)`**.
3. Driver executes:
   - **update_file_data(file_path, project_id, root_path)**:
     - **clear_file_data(file_id)** — **deletes** all rows for this file: code_chunks, ast_trees, cst_trees, classes, functions, methods, code_content, etc.
     - **_analyze_file(...)** — reads file from disk, parses AST, saves ast_trees, cst_trees, classes, functions, methods, imports, code_content. **Does not create chunks; does not call chunker.**
   - On success: `UPDATE files SET needs_chunking = 0`.

**Result after indexing worker processes a file:** File has AST, CST, entities, code_content. **Zero rows in code_chunks** (they were deleted by clear_file_data). needs_chunking = 0.

**Conclusion:** Indexing worker is “AST/CST/entities only”. It **removes** chunks; it does **not** create them.

---

## 4. Vectorization worker (vectorization_worker_pkg)

**One loop, per project, two steps.**

### Step 1: Chunking (files → code_chunks with embeddings)

- Query: files that have docstrings (or entities with docstrings) and **(needs_chunking = 1 OR no rows in code_chunks)**. Limit 5 files per project per cycle.
- For each file: **DocstringChunker.process_file(file_id, project_id, file_path, tree, file_content)**:
  - Extracts docstring items from AST (module, class, function, method).
  - For each item: calls **svo_client_manager.get_chunks(text, type="DocBlock")** → **chunker service returns chunks that already include embeddings (and tokens)**.
  - Persists each chunk via **database.add_code_chunk(..., chunk_text=..., embedding_vector=..., token_count=..., vector_id=None)**.

So **chunker returns chunks + vectors + tokens in one response**; we write them in one go into `code_chunks` (embedding_vector and token_count set; vector_id still NULL).

- After chunking: `UPDATE files SET needs_chunking = 0` for that file (in chunking.py).

### Step 2: FAISS vector_id assignment (batch_processor)

- Query: `SELECT ... FROM code_chunks WHERE project_id = ? AND embedding_vector IS NOT NULL AND vector_id IS NULL LIMIT batch_size`.
- For each chunk: add embedding to FAISS index, get vector_id; `UPDATE code_chunks SET vector_id = ?, embedding_model = ? WHERE id = ?`.

So chunks that **already have** embedding_vector (from Step 1) only get a FAISS slot and vector_id. There is also a fallback path in batch_processor that requests the chunker for chunks that have no embedding in DB; but when chunking is done via Step 1, embeddings are already present.

### End of cycle

- Rebuild FAISS indexes from DB for all projects (sync with code_chunks.vector_id and embedding_vector).

**Conclusion:** Chunks and their vectors/tokens enter the DB **only** in the vectorization worker’s Step 1 (chunking), via the chunker’s single response. Step 2 only assigns vector_id and updates FAISS.

---

## 5. File watcher (file_watcher_pkg)

- Scans watch_dirs, discovers new/changed/deleted files per project.
- For **new** and **changed** files: ensures file row exists, sets **needs_chunking = 1** (and does not delete chunks; only the indexing path or mark_file_needs_chunking deletes chunks).
- For **deleted** files: marks file deleted or removes from DB (per implementation).
- **Auto-indexing:** When it creates a **new project** (no row in projects), it starts a background thread that runs **update_indexes** for that project. **update_indexes** calls **_analyze_file** for each file and then **mark_file_needs_chunking** (which deletes chunks and sets needs_chunking=1). So for a newly registered project, chunks are cleared and must be re-created by the vectorization worker.

---

## 6. update_indexes (code_mapper_mcp_command) — manual or auto

- Iterates over Python files in the project.
- For each file: **_analyze_file(...)** (AST, CST, entities, code_content; same as indexing worker’s _analyze_file).
- After each file: **mark_file_needs_chunking(rel_path, project_id)**:
  - Sets **needs_chunking = 1**
  - **Deletes all code_chunks** for that file (`DELETE FROM code_chunks WHERE file_id = ?`).

So **update_indexes** does **not** create chunks; it only refreshes AST/CST/entities and then **removes** chunks and marks the file for chunking. Chunks are re-created later by the **vectorization worker** (Step 1).

---

## 7. End-to-end flow (who does what, in sequence)

```
File change (disk)
    →
File watcher: scan → new/changed → DB: needs_chunking=1 (and file row)
    →
Indexing worker: sees needs_chunking=1 → index_file(path, project_id)
    →
Driver: update_file_data → clear_file_data (DELETE code_chunks) → _analyze_file (AST,CST,entities only)
    → Driver: needs_chunking=0
    →
File now: AST, CST, entities, 0 chunks.

Vectorization worker (next cycle):
  Step 1: Finds file (no chunks or needs_chunking=1) → DocstringChunker.process_file
          → chunker.get_chunks(text) returns chunks+embeddings+tokens
          → add_code_chunk(..., embedding_vector=..., token_count=...)  ← all in one go
  Step 2: Chunks with embedding_vector and vector_id IS NULL → FAISS add → UPDATE vector_id
```

So **chunker gives chunks+vectors+tokens in one request**, and we persist them once in Step 1. The only follow-up is assigning vector_id and updating FAISS in Step 2.

---

## 8. Why “4 files chunked in 5 minutes”?

- **“Chunked”** in metrics = files that **gained** rows in code_chunks. The **only** place that creates those rows is the **vectorization worker, Step 1** (DocstringChunker).
- Step 1 is limited by: **LIMIT 5** files per project per cycle, **poll_interval** (e.g. 30 s), and **sequential** processing (one file after another; per file, one chunker request per docstring item). So throughput is low (e.g. ~1 file per minute or less) unless batch/parallel or limits are increased.

---

## 9. Summary table

| Component | Creates code_chunks? | Calls chunker? | Deletes code_chunks? |
|-----------|----------------------|----------------|----------------------|
| **Indexing worker** (index_file) | No | No | Yes (clear_file_data) |
| **Vectorization worker** Step 1 (chunking) | Yes (add_code_chunk with embedding_vector, token_count) | Yes (get_chunks → chunks+vectors+tokens) | No |
| **Vectorization worker** Step 2 (batch_processor) | No | Fallback only if no embedding in DB | No |
| **update_indexes** (_analyze_file + mark_file_needs_chunking) | No | No | Yes (mark_file_needs_chunking) |
| **File watcher** | No | No | No (only sets needs_chunking=1) |

So the chunker’s single response (chunks + vectors + tokens) is used **only** in the vectorization worker’s chunking step and is persisted there in one go; the rest of the pipeline only uses or clears that data.
