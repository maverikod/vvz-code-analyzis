# Vectorization worker profiling

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

The vectorization worker processes code chunks (load embeddings from DB or SVO, add to FAISS, write back `vector_id`). When GPU load is low (&lt;10%), profiling helps see where time is spent and why the vectorizer is “almost not working”.

## Profile log format

After each batch, the worker logs one **INFO** line with prefix `[PROFILE]`:

```
[PROFILE] batch_size=X processed=Y errors=Z total_s=T chunks_per_sec=... db_read_s=... svo_s=... svo_requests=N faiss_s=... db_update_s=... faiss_save_s=...
```

| Field | Meaning |
|-------|--------|
| `batch_size` | Max chunks requested from DB for this batch (config `batch_size`). |
| `processed` | Chunks successfully added to FAISS and DB in this batch. |
| `errors` | Chunks that failed in this batch. |
| `total_s` | Wall-clock time for the whole batch (loop + FAISS save). |
| `chunks_per_sec` | `processed / total_s`; throughput of the batch. |
| `db_read_s` | Total time spent reading chunk/embedding data from DB (per chunk). |
| `svo_s` | Total time spent in chunker/SVO calls (embedding requests). |
| `svo_requests` | Number of requests to chunker/SVO in this batch (one per chunk that needed embedding). |
| `faiss_s` | Total time spent in `faiss_manager.add_vector`. |
| `db_update_s` | Total time for DB updates (save embedding + update `vector_id`). |
| `faiss_save_s` | Time to save the FAISS index after the batch. |

All `*_s` values are in seconds. If `total_s` is large but `svo_s` is small, most time is in DB/FAISS or waiting; if `svo_s` dominates, chunker/SVO (often GPU) is the bottleneck.

## Why GPU is underutilized

Current design:

- Chunks are processed **one by one** inside the batch.
- For each chunk that does not yet have an embedding in the DB, **one request** is sent to the chunker/SVO service (which uses the GPU for embeddings).
- So: **one chunk → one GPU request**. Small batches (e.g. `batch_size=10`) and long pauses between batches (`poll_interval=30s`) mean few GPU calls per minute.

So the vectorizer “almost doesn’t work” from the GPU’s point of view: it feeds the GPU with very few, separate requests instead of a steady stream of batched work.

## Conclusion: worker slows process at least 3×

Measured chunker throughput (warm): ~4–5 chunks/min. Observed vectorization throughput: ~1 vector/min. The worker (poll_interval, batch_size, one request per chunk) therefore **slows chunk/vector processing at least 3×** compared to what the chunker could do. See `docs/CHUNKER_TIMING_BENCHMARK.md` for timings and the same conclusion.

## Recommendations

1. **Increase `batch_size`** (e.g. 50–200) so each batch does more chunks and more GPU calls per cycle (still one call per chunk, but more chunks per batch).
2. **Decrease `poll_interval`** (e.g. 5–10s) so batches start more often when there is work.
3. **Keep an eye on `[PROFILE]`**: if `svo_s` is a small fraction of `total_s`, the bottleneck is DB or FAISS; if `svo_s` dominates, the bottleneck is the chunker/SVO (GPU).
4. **Future**: If the chunker/SVO API supports **batch embedding** (many chunks in one request), the worker should be changed to send batched requests instead of one request per chunk; that would increase GPU utilization significantly.

## Where the code runs

- Profiling and `[PROFILE]` log: `code_analysis/core/vectorization_worker_pkg/batch_processor.py`, in `process_embedding_ready_chunks` (per-batch timing and the INFO log after FAISS save).
- Batch size and poll interval: worker config (e.g. `config.json`: `worker` / vectorization section: `batch_size`, `poll_interval`).
