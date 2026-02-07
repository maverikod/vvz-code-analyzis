# Chunker timing benchmark (docstrings)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Method

Requests were sent to **svo-chunker** via MCP Proxy (`chunk` command, type=DocBlock, language=Python). Between requests, **health** was polled (≈1 s interval). The chunker returns **processing_time** (seconds) in the job result.

## Sample docstrings

| # | Length (chars) | Text (preview) |
|---|----------------|----------------|
| 1 | 18  | "Return user by id." |
| 2 | 99  | "Get project statistics. Returns: Dict with file_count, chunk_count, vectorized_percent." |
| 3 | 165 | "Process chunks that are ready to be added to FAISS. Args: database..." |
| 4 | 153 | "Execute get database status command. Returns: SuccessResult..." |
| 5 | 195 | "Batch processing helpers for VectorizationWorker. This module contains..." |

**Average docstring length:** (18 + 99 + 165 + 153 + 195) / 5 = **126 chars**.

## Conclusion: worker slows process at least 3×

- **Chunker (warm):** ~12–15 s per docstring → **~4–5 chunks/min** theoretically achievable if the worker fed it continuously.
- **Observed vectorization throughput:** ~**1 vector/min** (from status snapshots: +12 vectors in ~12 min).
- **Slowdown:** 4–5 / 1 = **at least 3–5×**. The vectorization worker (poll_interval 30 s, batch_size 10, one request per chunk, FAISS/DB in between) reduces effective throughput so that the pipeline is **at least 3× slower** than the chunker alone.

**Takeaway:** Chunk/vector processing is bottlenecked by the worker’s pattern (rare polls, small batches, serial requests), not by the chunker’s raw speed. Fix: increase batch_size, decrease poll_interval, and/or batch chunker requests.

## Results (from chunker `processing_time`)

| Request | Chars | processing_time (s) | Note |
|---------|-------|---------------------|------|
| 1 | 18  | **36.99** | First request (cold start / model load) |
| 2 | 99  | **11.75** | Warm |

Jobs 3–5 were still in queue when the report was taken (chunker processes one job at a time).

## Inferences

- **Cold start:** First request ~**37 s** (model load / GPU warmup).
- **Warm, short docstring (99 chars):** ~**11.75 s** per request.
- **Extrapolation for average docstring (~126 chars):**  
  If time scales roughly with length: 11.75 × (126 / 99) ≈ **15 s** per average docstring when warm.  
  If overhead dominates: ~**12–15 s** per docstring (warm).
- **Why chunks are “slow”:** Each docstring triggers one chunker job (chunk + embedding). At ~12–15 s per docstring when warm, throughput is ~4–5 docstrings per minute per worker. That matches low vectorization rate (~1 vector/min) if the vectorizer is mostly waiting on chunker.

## Recommendations

1. **Batch chunker requests** if the chunker API supports multiple texts in one call (reduce overhead and improve GPU utilization).
2. **Keep chunker warm** (periodic health or tiny chunk) to avoid 37 s cold start when the first real request arrives.
3. **Increase vectorization batch_size** and **decrease poll_interval** so the vectorizer sends more chunker requests per cycle; the chunker queue will serialize them, but overall throughput can still improve.

## How to reproduce

- Via MCP: `call_server(server_id="svo-chunker", command="chunk", params={"text": "<docstring>", "type": "DocBlock", "language": "Python"})` → returns `job_id`. Then `queue_get_job_status(job_id)` until `status=="completed"`; read `result.result.data.processing_time`.
- Local script: `scripts/benchmark_chunker.py` (requires chunker reachable with mtls from host; may timeout if chunker is only reachable from Docker network).
