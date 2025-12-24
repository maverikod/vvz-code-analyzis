# Bug Report: chunk_metadata_adapter metrics.tokens Validation Error

## Summary
The chunker service returns chunks with `metrics.tokens` as a list of dictionaries (token objects), but `SemanticChunk` model expects `metrics.tokens` to be a list of strings. This causes deserialization failures when `chunk_metadata_adapter` tries to create `SemanticChunk` objects.

## Error Message
```
ValueError: Failed to deserialize chunk using chunk_metadata_adapter factory methods: 9 validation errors for SemanticChunk
metrics.tokens.0
  Input should be a valid string [type=string_type, input_value={'text': 'Test', 'lemma': 'test', 'start_char': 0, 'end_char': 4}, input_type=dict]
metrics.tokens.1
  Input should be a valid string [type=string_type, input_value={'text': 'class', 'lemma': 'class', 'start_char': 5, 'end_char': 10}, input_type=dict]
...
```

## Root Cause
1. The `ChunkerClient.chunk_text()` method returns chunks from the server.
2. Server response includes `metrics.tokens` as a list of token objects (dictionaries) with structure:
   ```python
   {
       'text': 'Test',
       'lemma': 'test',
       'start_char': 0,
       'end_char': 4
   }
   ```
3. `chunk_metadata_adapter.parse_chunk_static()` uses `SemanticChunk.from_dict_with_autofill_and_validation()` to deserialize chunks.
4. `SemanticChunk` model contains `ChunkMetrics` which defines `tokens` field as `Optional[List[str]]` (confirmed: `typing.Optional[typing.List[str]]`).
5. The chunker service returns `metrics.tokens` as `List[Dict[str, Any]]` (token objects with `text`, `lemma`, `start_char`, `end_char` fields).
6. Pydantic validation fails because `List[Dict]` cannot be automatically converted to `List[str]`.

## Affected Code
- `svo_client/result_parser.py`: `parse_chunk_static()` function
- `svo_client/chunker_client.py`: `chunk_text()` method
- `chunk_metadata_adapter/semantic_chunk.py`: `SemanticChunk` model validation
- `code_analysis/core/svo_client_manager.py`: `chunk_text()` method
- `code_analysis/core/docstring_chunker.py`: `_save_chunks()` method

## Example Error Messages (from logs)
```
Error getting embeddings: Failed to deserialize chunk using chunk_metadata_adapter factory methods: 24 validation errors for SemanticChunk
metrics.tokens.0
  Input should be a valid string [type=string_type, input_value={'text': 'List', 'lemma': 'list', 'start_char': 0, 'end_char': 4}, input_type=dict]
metrics.tokens.1
  Input should be a valid string [type=string_type, input_value={'text': 'all', 'lemma': 'all', 'start_char': 5, 'end_char': 8}, input_type=dict]
...
```

## Example Chunk Data (from logs)
```python
{
    'type': 'DocBlock',
    'body': 'Test class-methods with missing database file.',
    'text': 'Test class-methods with missing database file.',
    'language': 'en',
    'start': 0,
    'end': 44,
    'sha256': '...',
    'embedding': [...],
    'ordinal': 0,
    'metrics': {
        'tokens': [
            {'text': 'Test', 'lemma': 'test', 'start_char': 0, 'end_char': 4},
            {'text': 'class', 'lemma': 'class', 'start_char': 5, 'end_char': 10},
            {'text': '-', 'lemma': '-', 'start_char': 10, 'end_char': 11},
            {'text': 'methods', 'lemma': 'method', 'start_char': 11, 'end_char': 18},
            # ... more tokens
        ]
    },
    # ... other fields
}
```

## Expected vs Actual

### Expected (by SemanticChunk model):
```python
{
    'metrics': {
        'tokens': ['Test', 'class', '-', 'methods', 'with', ...]  # List[str]
    }
}
```

### Actual (from chunker service):
```python
{
    'metrics': {
        'tokens': [
            {'text': 'Test', 'lemma': 'test', 'start_char': 0, 'end_char': 4},
            {'text': 'class', 'lemma': 'class', 'start_char': 5, 'end_char': 10},
            # ... more token objects
        ]  # List[Dict[str, Any]]
    }
}
```

## Impact
- All chunking operations fail with deserialization errors
- Docstrings cannot be processed and saved to database
- Vectorization worker cannot process chunks (though it continues running)
- Semantic search cannot find chunks
- Analysis process continues but chunks are not saved properly

## Error Frequency
- **High**: Errors occur for every chunk returned by the chunker service
- **Pattern**: All chunks with `metrics.tokens` field fail validation
- **Workaround**: Chunks are skipped with warning messages, but processing continues

## Full Error Traceback
```
Traceback (most recent call last):
  File "/home/vasilyvz/projects/tools/code_analysis/.venv/lib/python3.12/site-packages/svo_client/result_parser.py", line 92, in parse_chunk_static
    return SemanticChunk.from_dict_with_autofill_and_validation(chunk_data)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/vasilyvz/projects/tools/code_analysis/.venv/lib/python3.12/site-packages/chunk_metadata_adapter/semantic_chunk.py", line 437, in from_dict_with_autofill_and_validation
    return cls(**prepared)
           ^^^^^^^^^^^^^^^
  File "/home/vasilyvz/projects/tools/code_analysis/.venv/lib/python3.12/site-packages/chunk_metadata_adapter/semantic_chunk.py", line 322, in __init__
    super().__init__(**data)
  File "/home/vasilyvz/projects/tools/code_analysis/.venv/lib/python3.12/site-packages/pydantic/main.py", line 250, in __init__
    validated_self = self.__pydantic_validator__.validate_python(data, self_instance=self)
  ...
ValueError: Failed to deserialize chunk using chunk_metadata_adapter factory methods: 9 validation errors for SemanticChunk
metrics.tokens.0
  Input should be a valid string [type=string_type, input_value={'text': 'Test', 'lemma': 'test', 'start_char': 0, 'end_char': 4}, input_type=dict]
```

## Required Fix
The issue must be fixed in one of the following places:

### Option 1: Fix in chunk_metadata_adapter (Recommended)
Modify `SemanticChunk` model to accept both formats:
- Accept `List[str]` (current format)
- Accept `List[Dict[str, Any]]` and extract `text` field automatically
- Or make `metrics.tokens` field optional or more flexible

### Option 2: Fix in svo_client/result_parser.py
Transform token objects to strings during deserialization:
```python
def parse_chunk_static(chunk: Any) -> "SemanticChunk":
    # ... existing code ...
    
    # Transform metrics.tokens if present
    if isinstance(chunk, dict) and 'metrics' in chunk:
        metrics = chunk.get('metrics', {})
        if isinstance(metrics, dict) and 'tokens' in metrics:
            tokens = metrics['tokens']
            if tokens and isinstance(tokens[0], dict):
                # Extract 'text' field from token objects
                metrics['tokens'] = [t.get('text', str(t)) if isinstance(t, dict) else t for t in tokens]
    
    # ... continue with deserialization ...
```

### Option 3: Fix chunker service (Server-side fix)
Modify the chunker service to return `metrics.tokens` as `List[str]` instead of `List[Dict]`, or provide both formats.

## Recommended Action
**Option 2** (fix in `svo_client/result_parser.py`) is recommended as immediate fix, since it handles the transformation at the deserialization layer. However, this should be reported to the `chunk_metadata_adapter` maintainers for a proper fix in the model definition (Option 1).

## Related Files
- `.venv/lib/python3.12/site-packages/svo_client/result_parser.py`
- `.venv/lib/python3.12/site-packages/chunk_metadata_adapter/semantic_chunk.py`
- `code_analysis/core/svo_client_manager.py`
- `code_analysis/core/docstring_chunker.py`

## Test Cases
1. Chunk text with `type="DocBlock"` parameter - should deserialize successfully
2. Chunk text with `type="CodeBlock"` parameter - should deserialize successfully
3. Process chunks from chunker - should not fail on `metrics.tokens` validation
4. Verify that token objects are properly converted to strings or handled gracefully

## Environment
- **Python Version**: 3.12
- **svo_client Version**: >=2.2.2
- **chunk_metadata_adapter Version**: 3.3.2
- **Pydantic Version**: 2.12+

## Error Statistics
- **Total errors in logs**: 121+ occurrences
- **Error rate**: 100% of chunks with `metrics.tokens` field fail validation
- **Affected chunks**: All chunks returned by chunker service that include token information

## Status
**OPEN** - Needs immediate fix

## Priority
**HIGH** - Blocks all chunking operations, though system continues with warnings

## Additional Notes
- The system continues to work despite these errors (chunks are skipped with warnings)
- This affects all chunks returned by the chunker service that include `metrics.tokens`
- The issue is consistent and reproducible (121+ errors observed in logs)
- Workaround: Chunks without `metrics.tokens` or with empty `metrics.tokens` may work, but most chunks fail
- The chunker service correctly returns token information, but the format doesn't match the expected schema

## Reproduction Steps
1. Call `chunker_client.chunk_text(text="Some text", type="DocBlock")`
2. Server returns chunks with `metrics.tokens` as list of token objects
3. `svo_client` tries to deserialize chunks using `chunk_metadata_adapter`
4. `SemanticChunk` validation fails because `metrics.tokens` contains dictionaries instead of strings
5. Error is logged and chunk is skipped, but processing continues

## Suggested Fix Implementation

### For svo_client/result_parser.py:
```python
def parse_chunk_static(chunk: Any, default_type: Optional[str] = None) -> "SemanticChunk":
    """Parse a chunk from various formats into SemanticChunk."""
    from chunk_metadata_adapter import ChunkMetadataBuilder, SemanticChunk
    
    if isinstance(chunk, SemanticChunk):
        return chunk
    
    # Normalize chunk data
    if isinstance(chunk, dict):
        chunk = chunk.copy()  # Don't modify original
        
        # Transform metrics.tokens from List[Dict] to List[str] if needed
        if 'metrics' in chunk and isinstance(chunk['metrics'], dict):
            metrics = chunk['metrics'].copy()
            if 'tokens' in metrics and isinstance(metrics['tokens'], list) and len(metrics['tokens']) > 0:
                if isinstance(metrics['tokens'][0], dict):
                    # Extract 'text' field from token objects
                    metrics['tokens'] = [
                        token.get('text', str(token)) if isinstance(token, dict) else token
                        for token in metrics['tokens']
                    ]
                    chunk['metrics'] = metrics
    
    try:
        builder = ChunkMetadataBuilder()
        return builder.json_dict_to_semantic(chunk)
    except Exception as exc:
        raise ValueError(
            "Failed to deserialize chunk using chunk_metadata_adapter: "
            f"{exc}\nChunk: {chunk}"
        ) from exc
```

This fix would:
1. Check if `metrics.tokens` contains dictionaries
2. Extract the `text` field from each token object
3. Convert to list of strings as expected by `SemanticChunk`
4. Preserve all other chunk data unchanged

