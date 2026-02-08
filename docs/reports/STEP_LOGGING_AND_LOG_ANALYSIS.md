# Step-by-Step Logging and Log Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## 1. Step-by-step logging added

### 1.1 Processing loop (`processing.py`)

- **Cycle:** `[STEP] Cycle #N started` right after `[CYCLE #N] Starting vectorization cycle`.
- **Step 0:**  
  - `[STEP] Step 0: Re-embed chunks missing params (project=...)`  
  - `[STEP] Step 0 done: filled=X, errors=Y`
- **Step 5 after Step 0:**  
  - `[STEP] Step 5 after Step 0: process_embedding_ready_chunks (project=...)`  
  - `[STEP] Step 5 after Step 0 done: processed=X, errors=Y`
- **Step 1:**  
  - `[STEP] Step 1: Query files needing chunking (project=..., limit=N)`  
  - `[STEP] Step 1: Found M files to chunk`
- **Step 2:**  
  - `[STEP] Step 2: process_embedding_ready_chunks (project=..., assign vector_id)`  
  - `[STEP] Step 2 done: processed=X, errors=Y, duration=Zs`

### 1.2 Batch processor (`batch_processor.py`)

- **Step 0:**  
  - `[STEP] Step 0: Retrieved N chunks missing params`  
  - `[STEP] Step 0: Sending batch of N texts to chunker`  
  - `[STEP] Step 0 done: updated M rows with embedding_vector/model/token_count`
- **Step 5 (embedding_ready):**  
  - When SELECT returns 0 rows:  
    `[STEP] Step 5 (embedding_ready): 0 chunks selected (criteria: embedding_vector IS NOT NULL AND vector_id IS NULL, project=..., limit=...)`  
  - When SELECT returns rows:  
    `[STEP] Step 5: Processing N chunks (add to FAISS, set vector_id)`

### 1.3 Chunking (`chunking.py`)

- **Step 5 after each file:**  
  `[STEP] Step 5 after file: process_embedding_ready_chunks (project=..., file_id=...)`

### 1.4 Docstring chunker (`docstring_chunker.py`)

- **Persist:** Before writing chunks, log counts with vs without embedding:  
  `[FILE id] Persisting N chunks (M with embedding, K without) to database...`

---

## 2. Log analysis (after restart 2026-02-08 ~20:45)

### 2.1 Step sequence observed

| Time     | Message |
|----------|--------|
| 20:45:14 | `[STEP] Cycle #1 started` |
| 20:45:16 | `[STEP] Step 0: Re-embed chunks missing params (project=928bcf10-...)` |
| 20:45:17 | `[STEP] Step 0: Retrieved 10 chunks missing params` |
| 20:45:17 | `[STEP] Step 0: Sending batch of 10 texts to chunker` |
| 20:46:18 | `[STEP] Step 0 done: filled=0, errors=10` |
| 20:46:18 | `[STEP] Step 1: Query files needing chunking (project=928bcf10-..., limit=30)` |
| 20:46:19 | `[STEP] Step 1: Found 30 files to chunk` |
| 20:46:20 | `[FILE 14741] Starting chunking for file .../ftp_security_adapter.py` |

### 2.2 Findings

1. **Step 0 (re-embed):**  
   - Selected 10 chunks missing embedding params and sent them to the chunker.  
   - **Result:** `filled=0, errors=10`.  
   - **Cause in log:** `SVOTimeoutError: Timeout error: Command 'chunk_batch' job ... did not finish within 60.0 seconds.`  
   - So the batch re-embed path did not update any row; all 10 are counted as errors.

2. **Step 1:**  
   - Query and step logs show 30 files selected for chunking; the worker started with file 14741 (`ftp_security_adapter.py`).

3. **Chunker responses for file 14741:**  
   - First docstring requests: HTTP 200 with `content-length: 181` (typical error payload size).  
   - Later requests: HTTP 200 with `content-length: 212` (successful chunk response).  
   - So for the first file after restart, the chunker sometimes returns an error (181) and sometimes success (212). When the file completes, the new log line  
     `[FILE 14741] Persisting N chunks (M with embedding, K without) to database...`  
     will show how many chunks were stored with vs without embedding.

4. **Step 5 (embedding_ready):**  
   - After Step 0 we had `fill_count=0`, so Step 5 after Step 0 was not run (by design).  
   - When a file is chunked and some chunks have embedding, Step 5 after that file will run; if all chunks for that file were stored without embedding, the new log  
     `[STEP] Step 5 (embedding_ready): 0 chunks selected (criteria: ...)`  
     will appear and the written criteria will confirm why 0 chunks were selected.

### 2.3 Conclusions

- Step logging works and makes the pipeline order and outcomes clear (Cycle → Step 0 → Step 1 → per-file chunking → Step 5 after file / Step 2).
- The main blocker in this run is **chunker/embedding**: Step 0 batch times out (60 s), so no re-embedding; per-file chunking gets a mix of 181 (error) and 212 (success) responses.
- The new “with embedding / without embedding” count at persist time will make it easy to see why Step 5 often gets 0 chunks (all chunks for that file written without embedding).

---

## 3. How to use step logs

- **Trace one cycle:** Search for `[STEP]` and filter by time or cycle number.
- **Explain “0 chunks” in Step 5:** Search for `Step 5 (embedding_ready): 0 chunks selected` and read the logged criteria (project, limit).
- **See why vectorized count does not grow:** Combine `Step 0 done: filled=0`, `Persisting N chunks (0 with embedding, N without)`, and `Step 5 (embedding_ready): 0 chunks selected`.
