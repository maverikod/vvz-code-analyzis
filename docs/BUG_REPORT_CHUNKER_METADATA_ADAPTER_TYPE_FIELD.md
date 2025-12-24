# Bug Report: chunk_metadata_adapter Missing 'type' Field

## Summary
The chunker service returns chunks without the required `type` field, causing deserialization failures when `chunk_metadata_adapter` tries to create `SemanticChunk` objects.

## Error Message
```
Failed to deserialize chunk using chunk_metadata_adapter: 1 validation error for SemanticChunk
type
  Field required [type=missing, input_value={'body': '...', 'text': '...', ...}, input_type=dict]
```

## Root Cause
1. The `ChunkerClient.chunk_text()` method returns chunks that are deserialized using `chunk_metadata_adapter.parse_chunk_static()`.
2. `parse_chunk_static()` uses `ChunkMetadataBuilder.json_dict_to_semantic()`, which calls `SemanticChunk(**d)`.
3. `SemanticChunk` (Pydantic model) requires a `type` field, but the chunker service response does not include it.
4. The chunker returns chunks with fields: `body`, `text`, `embedding`, `tokens`, `bm25_tokens`, `start`, `end`, `language`, `sha256`, but **not** `type`.

## Affected Code
- `svo_client/result_parser.py`: `parse_chunk_static()` function
- `svo_client/chunker_client.py`: `chunk_text()` method
- `code_analysis/core/svo_client_manager.py`: `chunk_text()` method
- `code_analysis/core/docstring_chunker.py`: `_save_chunks()` method

## Example Chunk Data (from logs)
```python
{
    'body': 'CLI interface for MCP server manager (systemd-style).\n\nAuthor: Vasiliy Zdanovskiy\nemail: vasilyvz@gmail.com',
    'text': 'CLI interface for MCP server manager (systemd-style).  Author: Vasiliy Zdanovskiy email: vasilyvz@gmail.com',
    'sv_pair': None,
    'tokens': [...],
    'embedding': [...],
    'start': 0,
    'end': 107,
    'language': 'en',
    'sha256': '69e69a87e0733d6152278c2d8a022b396a827839cdfc70367aebb28410b2695e',
    'bm25_tokens': [...]
    # Missing: 'type' field
}
```

## Impact
- All chunking operations fail with deserialization errors
- Docstrings cannot be processed and saved to database
- Vectorization worker cannot process chunks
- Semantic search cannot find chunks

## Expected Behavior
The chunker service should return chunks that include the `type` field when it is provided as a parameter to `chunk_text()`. Alternatively, `svo_client` should handle the deserialization gracefully when `type` is missing, either by:
1. Making `type` field optional in `SemanticChunk` model, OR
2. Extracting `type` from the request parameters and adding it to chunks during deserialization, OR
3. The chunker service should always return `type` field in response chunks

## Required Fix
The issue must be fixed in one of the following places:
1. **Chunker Service**: Always include `type` field in response chunks (matches the `type` parameter from request)
2. **svo_client/result_parser.py**: Handle missing `type` field during deserialization (extract from params or make field optional)
3. **chunk_metadata_adapter**: Make `type` field optional in `SemanticChunk` model, or provide default value during deserialization

## Recommended Action
Report this bug to the maintainers of:
- `svo_client` library (handles chunker client and result parsing)
- `chunk_metadata_adapter` library (defines SemanticChunk model)
- Chunker service (should return complete chunk data including `type`)

## Related Files
- `code_analysis/core/svo_client_manager.py`
- `code_analysis/core/docstring_chunker.py`
- `.venv/lib/python3.12/site-packages/svo_client/result_parser.py`
- `.venv/lib/python3.12/site-packages/chunk_metadata_adapter/...`

## Test Cases
1. Chunk text with `type="DocBlock"` parameter - chunks should include `type="DocBlock"` in response
2. Chunk text without `type` parameter - should either return chunks with default `type` or handle gracefully
3. Chunk text with `type="CodeBlock"` parameter - chunks should include `type="CodeBlock"` in response
4. Process chunks from chunker - should not fail on deserialization regardless of `type` field presence

## Status
**OPEN** - Reported to library/service maintainers

## Priority
**HIGH** - Blocks all chunking operations

## Reproduction Steps
1. Call `chunker_client.chunk_text(text="Some text", type="DocBlock")`
2. Server returns chunks without `type` field
3. `svo_client` tries to deserialize chunks using `chunk_metadata_adapter`
4. `SemanticChunk` validation fails because `type` field is required but missing

## Example Request/Response

**Request:**
```python
await chunker_client.chunk_text(
    text="CLI interface for MCP server manager.",
    type="DocBlock"
)
```

**Response (actual - missing `type`):**
```json
{
  "chunks": [
    {
      "body": "CLI interface for MCP server manager.",
      "text": "CLI interface for MCP server manager.",
      "embedding": [...],
      "tokens": [...],
      "bm25_tokens": [...],
      "start": 0,
      "end": 37,
      "language": "en",
      "sha256": "..."
    }
  ]
}
```

**Response (expected - with `type`):**
```json
{
  "chunks": [
    {
      "type": "DocBlock",
      "body": "CLI interface for MCP server manager.",
      "text": "CLI interface for MCP server manager.",
      "embedding": [...],
      "tokens": [...],
      "bm25_tokens": [...],
      "start": 0,
      "end": 37,
      "language": "en",
      "sha256": "..."
    }
  ]
}
```

