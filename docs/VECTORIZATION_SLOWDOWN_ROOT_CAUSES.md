# Root causes: why the vectorization worker slows chunk/vector processing at least 3×

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

The worker is **at least 3× slower** than the chunker’s raw throughput because of: (1) **strictly serial** SVO calls (one chunk → one request, no batching, no concurrency), (2) **small batch size** and (3) **long idle sleep** when there is no work.

---

## Cause 1: One chunk → one SVO request (serial, no batching)

**Where:** `code_analysis/core/vectorization_worker_pkg/batch_processor.py`

- The inner loop over chunks is strictly sequential. For each chunk that has no embedding in DB, the code calls the chunker **once** and **waits** for the result before moving to the next chunk.

```python
# batch_processor.py, ~line 118
for chunk in chunks:
    ...
    # ~line 211: single await per chunk, no batching
    chunks_with_emb = await self.svo_client_manager.get_chunks(
        text=chunk_text, type=chunk_type
    )
```

- There is **no batch API** used (e.g. multiple texts in one `get_chunks` call) and **no concurrency** (e.g. `asyncio.gather` for several chunks). So N chunks ⇒ N sequential round-trips to the chunker.
- Chunker can do ~4–5 chunks/min when fed continuously; the worker feeds it one chunk at a time and does DB/FAISS in between, so effective rate drops to ~1 vector/min.

**Conclusion:** The main cause of the slowdown is **serial, one-request-per-chunk** use of the chunker.

---

## Cause 2: Small batch size per project per cycle

**Where:** `batch_processor.py` and config.

- Each call to `process_embedding_ready_chunks` loads at most **`self.batch_size`** chunks (default **10**) for the current project (`batch_processor.py` ~lines 58–71: `LIMIT ?` with `self.batch_size`).
- After processing these 10 chunks, the function returns; the outer loop then moves to the next project or ends the cycle. So **per project, per cycle**, we process at most 10 chunks.
- Default `batch_size=10` is taken from `config.json` → `code_analysis.worker.batch_size` and from `runner.py` (~line 111, 366) / `base.py` (~line 33, 67).

**Conclusion:** Small batch size caps how many chunks are handled per project per cycle and increases the share of “cycle overhead” (DB, FAISS load, sleep) relative to useful work.

---

## Cause 3: Long sleep when there is no activity

**Where:** `code_analysis/core/vectorization_worker_pkg/processing.py`

- After each cycle, the worker sleeps before the next poll (~lines 664–687).
- If **no** work was done in the cycle (`cycle_activity` is False), it sleeps the full **`poll_interval`** (default **30 s**). So when the queue is empty or no chunk was processed, the worker idles for 30 s.
- If work was done (`cycle_activity` True), it sleeps only **2 s** (`actual_poll_interval = min(actual_poll_interval, 2)`).
- So in the “no work” case, **poll_interval=30** adds long idle gaps and reduces effective throughput when work arrives in bursts.

**Conclusion:** A 30 s poll interval when there is no activity increases latency and lowers effective throughput.

---

## Cause 4: Per-chunk DB and FAISS work inside the loop

**Where:** `batch_processor.py`, inside `for chunk in chunks`.

- For **each** chunk the worker: (1) reads from DB (embedding check), (2) optionally calls SVO, (3) writes embedding to DB if from SVO, (4) calls `faiss_manager.add_vector`, (5) updates `vector_id` in DB.
- All of this is **sequential** per chunk. So total time per batch = sum of (DB + SVO + DB + FAISS + DB) per chunk. There is no batching of DB or FAISS operations, and no overlapping of SVO with the next chunk.

**Conclusion:** Serial per-chunk DB/FAISS work adds latency and prevents overlapping with the next chunk’s SVO call.

---

## Cause 5: Chunking of new files is also serial

**Where:** `code_analysis/core/vectorization_worker_pkg/chunking.py` and processing loop.

- `_request_chunking_for_files` iterates over files **one by one** (~line 46: `for file_record in files`). For each file it calls `chunker.process_file` (which typically involves multiple docstrings and thus multiple SVO calls per file, again sequential).
- The number of files sent to chunking per project per cycle is limited (e.g. **5** in the query in `processing.py` ~line 447: `LIMIT ?` with 5).

**Conclusion:** Chunking is serial per file and per docstring, which also limits how fast new chunks are produced and then vectorized.

---

## Summary table

| Cause | Location | Effect |
|-------|----------|--------|
| 1. One chunk → one SVO request, serial | `batch_processor.py` ~118, 211 | No batching/concurrency; chunker underused |
| 2. Small batch_size (10) | `batch_processor.py` 70; config; `base.py` 67 | Few chunks per project per cycle |
| 3. poll_interval 30 s when no activity | `processing.py` 667–687 | Long idle between cycles when queue empty |
| 4. Serial DB/FAISS per chunk | `batch_processor.py` inside `for chunk` | No overlap; extra latency per chunk |
| 5. Serial chunking per file | `chunking.py` 46; `processing.py` 447 (LIMIT 5) | Slow feed of new chunks |

---

## Recommended changes (in order of impact)

1. **Batch or parallelize SVO calls** in `batch_processor.py`: either call chunker with multiple texts in one request (if API allows), or issue several `get_chunks` in parallel (e.g. `asyncio.gather`) with a concurrency limit.
2. **Increase `batch_size`** (e.g. 50–100) and **decrease `poll_interval`** (e.g. 5–10 s) in config so the worker processes more chunks per cycle and polls more often.
3. **Overlap** SVO with DB/FAISS where possible (e.g. prepare next chunk while waiting for SVO, or batch DB updates).
4. Optionally increase the limit on files sent to chunking per project per cycle (currently 5) so more new chunks are created each cycle.

These changes address the root causes above and should reduce the factor by which the worker slows chunk/vector processing (goal: remove the “at least 3×” slowdown).
