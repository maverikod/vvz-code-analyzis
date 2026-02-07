# SVO client batch API (chunk_batch)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Client package: `svo_client` (site-packages)

The **svo_client** (ChunkerClient) in `.venv/lib/python3.12/site-packages/svo_client` supports **batch chunking**:

| Method | Server command | Description |
|--------|----------------|--------------|
| `chunk_text(text, **params)` | `chunk` | Single text → one list of SemanticChunk. |
| **`chunk_texts(texts, **params)`** | **`chunk_batch`** | **List of texts → list of lists of SemanticChunk (one list per text).** |
| `submit_chunk_batch_job(texts, **params)` | `chunk_batch` | Submit batch job; returns `job_id`. |
| `wait_for_batch_result(job_id, ...)` | (queue) | Wait for batch job; returns `List[List[SemanticChunk]]`. |

**Parameters for batch:** `texts` (list of strings) plus the same optional params as single chunk: `type`, `language`, `window`, `source_id`, `project`, `unit_id`, `chunking_version`.

**Result of `chunk_texts`:** `List[List[SemanticChunk]]` — same length as `texts`; each element is the chunk list for the corresponding text (with embeddings when the server returns them).

## Integration in this project

- **SVOClientManager** (`code_analysis/core/svo_client_manager.py`) now exposes:
  - **`get_chunks(text, **kwargs)`** — single text, calls `_chunker_client.chunk_text`.
  - **`get_chunks_batch(texts, **kwargs)`** — list of texts, calls `_chunker_client.chunk_texts`; returns `List[List[Any]]` (one list per input text). Texts below `min_chunk_length` get an empty list at that index.

- The **vectorization batch_processor** still uses one `get_chunks()` per chunk (serial). To use the batch API and remove the “at least 3×” slowdown, the batch_processor should:
  1. Collect up to N chunk texts that need embeddings (e.g. from the current batch).
  2. Call `get_chunks_batch(texts)` once.
  3. Map the returned list of chunk lists back to chunk IDs and write embeddings / vector_id.

## Server requirement

The chunker server (svo-chunker) must expose the **`chunk_batch`** command with parameter **`texts`** (array of strings). If the server does not support `chunk_batch`, `get_chunks_batch` will fail at runtime; the client API is already available in svo_client.
