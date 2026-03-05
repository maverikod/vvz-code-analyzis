# Why `embedding_model` is missing (root cause)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

**Chunks get no `embedding_model` and vectors are not persisted because the chunker server (svo-chunker) does not include the `"model"` (or `"embedding_model"`) field in each chunk object in its JSON response.**

The fix is on the **chunker server side**: the server must add `"model"` or `"embedding_model"` to every chunk when returning chunks that have embeddings.

---

## Data flow

1. **code_analysis** calls `svo_client_manager.get_chunks(text)` or `get_chunks_batch(texts)`.
2. **svo_client** (library) sends a request to the chunker server (e.g. `chunk` or `chunk_batch`).
3. The **chunker server** returns JSON, e.g. `{ "result": { "chunks": [ ... ] } }`. Each element of `chunks` is a chunk object (dict).
4. **svo_client** parses the response in `result_parser.py`:
   - `extract_chunks_or_raise()` / `extract_batch_results_or_raise()` get the raw list of chunk dicts.
   - For each dict, `parse_chunk_static(chunk)` is called.
   - In `parse_chunk_static` (lines 102–104):
     - If the chunk dict has `"model"`, it is copied to `"embedding_model"` and passed to `SemanticChunk.from_dict_with_autofill_and_validation(chunk_data)`.
     - If the chunk dict has **no** `"model"` (and no `"embedding_model"`), then `SemanticChunk.embedding_model` stays **None**.
5. **code_analysis** (DocstringChunker) receives `SemanticChunk` objects. It sets `self.embedding_model` from the first chunk that has `ch.embedding_model`. If no chunk has it, `self.embedding_model` remains `None`.
6. When persisting to DB, `add_code_chunk(..., embedding_vector=..., embedding_model=...)` requires `embedding_model` when `embedding_vector` is set. If `embedding_model` is `None`, we **raise `ChunkerResponseError`** (missing model is treated as an error). The vector is not persisted; the chunking step fails for that file.

---

## Root cause

The **chunker server** response shape for each chunk does not include `"model"` (or `"embedding_model"`). So:

- svo_client never sets `embedding_model` on `SemanticChunk`.
- DocstringChunker never gets a model name from the chunker.
- We cannot persist the vector and vectorization metrics show 0.

---

## Required fix (chunker server)

In the **svo-chunker** (or whatever service implements the chunker API):

- For every chunk object in the response that contains an embedding (e.g. `embedding`, `vector`), include one of:
  - `"model": "<embedding_model_name>"`, or  
  - `"embedding_model": "<embedding_model_name>"`

in that chunk’s JSON object. The client normalizes `"model"` → `"embedding_model"` in `svo_client.result_parser.parse_chunk_static`.

Example expected chunk shape (minimal):

```json
{
  "body": "...",
  "embedding": [ 0.1, ... ],
  "model": "your-embedding-model-id"
}
```

---

## Checking chunker response via MCP proxy

1. Call **chunk** or **chunk_batch** on server `svo-chunker`; you get `job_id` and `status: "pending"`.
2. Wait a few seconds (e.g. 5–15 s), then call **queue_get_job_status** (not `job_status`) with that `job_id`.
3. When `status` is `"completed"`, the payload contains `result.result.data.chunks` — each element is a chunk object. Check for `"model"` or `"embedding_model"` and whether they are non-empty when `embedding` is present.

Example: a run returned a chunk with `"embedding": null`, `"embedding_model": ""`, and `"_embedding_error": "..."` (embedding service failed). So the chunker does send `embedding_model` but as empty string when there is no embedding. When the chunk **has** an embedding, the chunker must set `embedding_model` (or `model`) to the actual model name.

---

## References

- **svo_client** (site-packages): `result_parser.parse_chunk_static` — copies `chunk["model"]` to `chunk["embedding_model"]` before building `SemanticChunk`.
- **code_analysis**: `DocstringChunker` uses `getattr(ch, "embedding_model", None)` from each chunk. If a chunk has an embedding but no `embedding_model`, **`ChunkerResponseError` is raised** (see `docstring_chunker_pkg/docstring_chunker.py` and `core/exceptions.py`).
