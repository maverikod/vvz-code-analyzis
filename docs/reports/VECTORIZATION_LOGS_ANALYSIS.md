# Vectorization Worker Logs Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

Analysis of `logs/vectorization_worker.log` and `logs/vectorization_worker.log.1` explains why the **vectorized** count stays at 250 while **chunked** files and **total chunks** grow.

---

## 1. Two main causes

### 1.1 Chunks written without embeddings (chunker/embedding failures)

- In **vectorization_worker.log.1** there are **1,029+** lines:  
  `(persisting one row without embedding)`.
- Typical message:  
  `Failed to get chunks: SVO server error [-32603]: Model RPC server failed after 3 attempts (persisting one row without embedding)`.
- When the chunker or embedding service fails, the worker still persists chunks with **`embedding_vector = NULL`** so that chunking progress is not lost.
- **Step 5** (`process_embedding_ready_chunks`) selects only rows with  
  `embedding_vector IS NOT NULL AND vector_id IS NULL`.  
  Chunks stored without embedding are never selected, so they never get `vector_id` or FAISS.

So a large share of chunks are in the DB with **no vector**, and by design they are excluded from Step 5 until something later fills `embedding_vector` (e.g. Step 0 “fill missing params” or a future re-embed pass).

### 1.2 Step 5 sees 0 chunks right after a successful file

- In **vectorization_worker.log** (current, 20:20:30):
  - `[FILE 14732] Persisted 7 docstring chunks to database in 15.357s`
  - `[FILE 14732] Successfully chunked file ... in 26.757s total`
  - Immediately after:  
    `Getting non-vectorized chunks from DB (project=928bcf10-db1c-47a3-8341-f60a6d997fe7), limit=10`
  - Then: **`[TIMING] Retrieved 0 chunks in 1.107s`**

So Step 5 is invoked right after the file (as intended), but the SELECT returns **0** rows. That implies either:

- The 7 chunks for that file were written with **`embedding_vector = NULL`** (e.g. chunker returned chunks without embedding, or response was treated as failure and fallback “without embedding” was used), or  
- A **visibility/commit** issue: the process that does the SELECT (via the same DatabaseClient/driver) does not yet see the just-committed INSERTs (e.g. different connection or transaction in the driver, or read-your-writes not guaranteed).

So even when the pipeline runs correctly (Step 5 right after each file), the DB state at SELECT time often has no rows satisfying `embedding_vector IS NOT NULL AND vector_id IS NULL` for that project.

---

## 2. Log evidence

### 2.1 “No chunks needing vector_id assignment”

- Repeated message:  
  `No chunks needing vector_id assignment in this cycle (iteration 1/3)`  
  and  
  `[TIMING] Step 2: Retrieved 0 chunks from DB`.
- So in many cycles, **Step 2 / process_embedding_ready_chunks** finds **0** chunks to process. That is consistent with:
  - Most new chunks being stored with `embedding_vector IS NULL`, and/or  
  - The SELECT for “ready” chunks returning nothing (e.g. visibility or project_id/embedding_vector not set as expected).

### 2.2 Chunker failures

- Recurrent errors:
  - `SVO server error [-32603]: Model RPC server failed after 3 attempts`
  - `Timeout error: Command 'chunk_batch' job ... did not finish within 60.0 seconds`
- After batch failure, fallback is per-docstring `get_chunks`; when that also fails, the worker persists **one row without embedding** per docstring.
- So a single file can add many chunks with **no** embedding, which again are invisible to Step 5.

### 2.3 Step 0 “fill missing params”

- Log lines like:  
  `[TIMING] Retrieved 10 chunks missing params in 1.09xs`  
  show that **process_chunks_missing_embedding_params** does find chunks that are missing embedding (or model, etc.).
- So the pipeline for “re-embed and then Step 5” is active; the bottleneck is that many chunks are created without embedding in the first place, and for files that do get embeddings, Step 5 still sometimes sees 0 chunks (see 1.2).

---

## 3. Conclusions

| Finding | Impact |
|--------|--------|
| Many chunks persisted **without embedding** due to chunker/embedding failures | They never match `embedding_vector IS NOT NULL`, so Step 5 never assigns `vector_id` or adds them to FAISS. |
| Step 5 runs **immediately** after each file (and after Step 0) | Pipeline order is correct. |
| Step 5 often gets **0 chunks** right after a file that “Persisted N docstring chunks” | Either those chunks were stored with `embedding_vector = NULL`, or there is a commit/visibility issue between INSERT and SELECT. |
| Chunker/embedding service often fails (timeouts, Model RPC -32603) | High fraction of new chunks have no vector; vectorized count cannot grow until embeddings exist. |

So:

1. **Stability of chunker and embedding service** is the main lever: fewer “persisting without embedding” → more chunks with `embedding_vector` → Step 5 can process them.
2. **Verify** that when the chunker returns chunks with embeddings, `add_code_chunk` is always called with non-NULL `embedding_vector` (no silent fallback to NULL).
3. **Verify** in the driver that after the last `add_code_chunk` INSERT for a file, the transaction is committed and the same or next SELECT (in process_embedding_ready_chunks) sees those rows (read-your-writes).

---

## 4. Recommendations

1. **Operational:** Reduce chunker/embedding timeouts or load so that “Model RPC server failed” and “chunk_batch did not finish within 60s” are rare; then fewer chunks will be stored without embedding.
2. **Code:** In the path that persists chunks after a successful chunker response, ensure we never write a chunk with embeddings in the response but `embedding_vector = NULL` in the DB (log and fix any such branch).
3. **Code:** The SQLite driver already commits after each `execute()` when not inside an explicit transaction (see `database_driver_pkg/drivers/sqlite.py`), so the SELECT in `process_embedding_ready_chunks` should see rows written by the preceding `add_code_chunk` calls. No change needed unless the worker uses a different connection or transaction. The main explanation for "Retrieved 0 chunks" remains: chunks for that file were stored with `embedding_vector = NULL`.
4. **Monitoring:** Log when we persist chunks **with** vs **without** embedding (e.g. count or flag per file) so that “Retrieved 0 chunks” can be correlated with “all chunks for this file were stored without embedding” vs “chunks had embedding but SELECT saw 0”.
