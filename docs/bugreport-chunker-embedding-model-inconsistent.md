# Bug report: Chunker returns empty `embedding_model` for chunks that have `embedding`

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Summary

**Component:** svo-chunker (chunker service)  
**Issue:** For chunks that contain an embedding vector (`embedding` array present), the field `embedding_model` is sometimes an empty string `""` instead of the embedding model name. This is inconsistent: in the same batch response, some chunks have `embedding_model: "all-MiniLM-L6-v2"`, others have `embedding_model: ""` despite having a non-null `embedding`.

**Impact:** Clients (e.g. code_analysis) require a non-empty `embedding_model` when persisting chunks with vectors. Empty or missing model leads to `ChunkerResponseError`, vectors are not stored, and vectorization metrics stay zero.

---

## Environment

- **Chunker server:** svo-chunker (via MCP proxy), URL e.g. `https://svo-chunker:8009`
- **Client used for reproduction:** MCP Proxy → `call_server(server_id="svo-chunker", ...)`
- **Date observed:** 2026-02-07
- **Embedding model name when present:** `all-MiniLM-L6-v2`

---

## Steps to reproduce

1. **Call `chunk_batch`** on server `svo-chunker` with a list of texts long enough to be chunked (each ≥ 15 characters per chunker config):

   ```json
   {
     "texts": [
       "This is a longer docstring that explains the function. It has several words so the chunker may return a chunk with an embedding.",
       "Another brief one."
     ],
     "type": "DocBlock"
   }
   ```

2. From the response, take **`job_id`** (e.g. `073dd3c2-2a80-417a-8799-c989d067ceb4`).

3. **Wait** ~15–30 seconds for the batch job to complete.

4. **Call `queue_get_job_status`** (not `job_status`) with the same `job_id`:

   ```json
   { "job_id": "<job_id from step 1>" }
   ```

5. When `data.status` is `"completed"`, inspect **`data.result.result.data.results`**: each element has `chunks`. For each chunk that has a non-null **`embedding`** array, check **`embedding_model`**.

---

## Expected behaviour

- Every chunk object that has a non-null, non-empty **`embedding`** MUST have **`embedding_model`** (or **`model`**) set to the actual embedding model name (e.g. `"all-MiniLM-L6-v2"`), not an empty string.

---

## Actual behaviour

- In the same batch response:
  - Some chunks with non-null **`embedding`** have **`embedding_model`: ""**.
  - At least one chunk with **`embedding`** has **`embedding_model`: "all-MiniLM-L6-v2"`**.
- So the chunker can return the model name but does not do so consistently for all chunks that have embeddings.

---

## Observed response (excerpt)

- **Result structure:** `result.result.data.results` is an array; each item has `success`, `chunks` (array of chunk objects).
- **Chunk object fields (relevant):**
  - `embedding`: array of floats (when present) or `null`.
  - `embedding_model`: string — observed values: `""` (empty) and `"all-MiniLM-L6-v2"` in the same batch.
- **Short text:** A text shorter than `min_chunk_length` (e.g. 15) returns `success: false` with an error (e.g. "Text is too short for chunking"); that case is expected and not part of this bug.

---

## MCP commands used (reproduction)

| Step | Tool / Command        | Params |
|------|------------------------|--------|
| 1    | `call_server`         | `server_id="svo-chunker", command="chunk_batch", params={"texts": ["...", "..."], "type": "DocBlock"}` |
| 2    | (wait ~15–30 s)       | —      |
| 3    | `call_server`         | `server_id="svo-chunker", command="queue_get_job_status", params={"job_id": "<job_id>"}` |

---

## References

- **code_analysis:** `docs/CHUNKER_MODEL_FIELD.md` — why `embedding_model` is required and how to check chunker response via MCP.
- **code_analysis:** `ChunkerResponseError` raised when a chunk has `embedding` but no usable `embedding_model` (see `core/exceptions.py`, `core/docstring_chunker_pkg/docstring_chunker.py`).
- **svo_client:** `result_parser.parse_chunk_static` maps `chunk["model"]` → `embedding_model`; empty string remains empty and is treated as “no model” by the client.
