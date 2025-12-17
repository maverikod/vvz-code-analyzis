# Bug Report: Chunker Server Returns Empty Results for All Text Inputs

**Author:** Vasiliy Zdanovskiy  
**Email:** vasilyvz@gmail.com  
**Date:** 2025-12-15  
**Severity:** High  
**Status:** Open

## Summary

The SVO chunker service (localhost:8009) consistently returns empty or invalid results for all text inputs, regardless of text length, content, or type. The service accepts mTLS connections successfully (health check works), but all chunking requests fail with various error messages.

## Environment

- **OS:** Linux 6.8.0-88-generic
- **Python:** 3.12
- **Package:** code_analysis
- **Chunker Service:** localhost:8009 (mTLS)
- **Library:** svo_client (ChunkerClient)
- **mTLS Certificates:** Configured and verified

## Configuration

```json
{
  "chunker": {
    "enabled": true,
    "url": "localhost",
    "port": 8009,
    "protocol": "mtls",
    "cert_file": "mtls_certificates/mtls_certificates/client/code-analysis.crt",
    "key_file": "mtls_certificates/mtls_certificates/client/code-analysis.key",
    "ca_cert_file": "mtls_certificates/mtls_certificates/ca/ca.crt",
    "retry_attempts": 3,
    "retry_delay": 5.0
  }
}
```

## Steps to Reproduce

1. Configure mTLS certificates in `config.json`
2. Start code_analysis server
3. Run project analysis: `analyze_project` command
4. Check server logs for chunking errors
5. Or test directly via CLI:

```bash
python3 -m svo_client.cli \
  --host localhost --port 8009 \
  --cert mtls_certificates/mtls_certificates/client/code-analysis.crt \
  --key mtls_certificates/mtls_certificates/client/code-analysis.key \
  --ca mtls_certificates/mtls_certificates/ca/ca.crt \
  chunk --text "This is a test docstring that should be chunked properly."
```

## Expected Behavior

- ChunkerClient successfully chunks text of any reasonable length (≥30 characters)
- Returns list of `SemanticChunk` objects with:
  - `body` or `text` field containing chunk text
  - `embedding` field with vector embeddings
  - `bm25` field with BM25 scores
- Chunks are stored in database and added to FAISS index

## Actual Behavior

- Health check succeeds: `{"success": true, "status": "ok"}`
- All chunking requests fail with one of the following errors:
  - `SVO server error [empty_result]: Empty or invalid result from server`
  - `SVO server error [-32603]: Model RPC server error after 3 attempts: LanguageChunker: Empty text`
  - `Timeout error: Command 'chunk' job did not finish within 30.0 seconds`
  - `Connection error: Server disconnected without sending a response`
- No chunks are created
- Analysis completes but without semantic chunks

## Error Messages

### Test Results

All test cases (0/5 successful):

1. **Short text (30 characters):**
   ```
   Text: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
   Error: SVO server error [empty_result]: Empty or invalid result from server
   ```

2. **Medium text (50-150 characters):**
   ```
   Text: "This is a longer test docstring that should definitely be chunked properly. It contains more than enough text."
   Error: SVO server error [empty_result]: Empty or invalid result from server
   ```

3. **Long text (300+ characters):**
   ```
   Text: "This is a very long test docstring. " * 10
   Error: SVO server error [-32603]: Model RPC server error after 3 attempts: LanguageChunker: Empty text
   ```

4. **Text with Python code:**
   ```
   Text: "This is a docstring with Python code example.\n\ndef example():\n    return True"
   Error: Timeout error: Command 'chunk' job did not finish within 30.0 seconds
   ```

5. **Real docstrings from codebase:**
   ```
   Text: "Simple HTTPS server with mTLS for testing." (42 chars)
   Error: SVO server error [empty_result]: Empty or invalid result from server
   
   Text: "Create SSL context for mTLS client connections." (47 chars)
   Error: SVO server error [empty_result]: Empty or invalid result from server
   
   Text: "Register server with MCP Proxy." (31 chars)
   Error: SVO server error [empty_result]: Empty or invalid result from server
   ```

### Log Statistics

From server logs analysis:
- **Total chunking errors:** 300+ attempts
- **Error distribution by length:**
  - 31-50 characters: ~40% of errors
  - 51-100 characters: ~25% of errors
  - 101-200 characters: ~20% of errors
  - 200+ characters: ~15% of errors

### Common Error Patterns

```
svo_client.errors.SVOServerError: SVO server error [empty_result]: Empty or invalid result from server
Error chunking text (attempt 1/3, length=42): SVO server error [empty_result]: Empty or invalid result from server
Error chunking text (attempt 2/3, length=42): Connection error: Server disconnected without sending a response
Error chunking text (attempt 3/3, length=42): Connection error: Server disconnected without sending a response
All retry attempts failed for chunk_text (length=42): Connection error: Server disconnected without sending a response
```

## Impact

- **High:** Semantic search functionality is completely non-functional
- **High:** Code analysis cannot create searchable chunks
- **Medium:** FAISS index remains empty
- **Medium:** All docstrings and comments are skipped during analysis

## Workaround

None available. The chunker service must be fixed or replaced.

## Root Cause Analysis

The issue appears to be on the chunker server side:

1. **mTLS connection works:** Health check endpoint responds correctly
2. **Chunking endpoint fails:** All chunking requests return empty/invalid results
3. **No pattern in failures:** Errors occur for texts of all lengths and types
4. **Possible causes:**
   - Chunker service internal error (model not loaded, configuration issue)
   - Language detection failure (all texts detected as empty)
   - Processing pipeline broken (chunker → embedding → response chain)
   - Database or storage backend issue on chunker server

## Related Issues

- Previous bug report: `docs/BUG_REPORT_CHUNKER_CLIENT.md` (connection errors, now resolved)
- This is a different issue: connection works, but processing fails

## Files Affected

- `code_analysis/core/docstring_chunker.py` - Logs warnings for failed chunks
- `code_analysis/core/vectorization_worker.py` - Retries failed chunking requests
- `code_analysis/core/svo_client_manager.py` - Handles retry logic for chunker errors (enhanced logging added)
- `code_analysis/core/chunker_client_wrapper.py` - Creates chunker client with mTLS (dead code removed)
- `scripts/diagnose_chunker_server.py` - Diagnostic script for analyzing chunker server responses (NEW)

## Verification Steps

1. Verify chunker service is running:
   ```bash
   python3 -m svo_client.cli --host localhost --port 8009 \
     --cert mtls_certificates/mtls_certificates/client/code-analysis.crt \
     --key mtls_certificates/mtls_certificates/client/code-analysis.key \
     --ca mtls_certificates/mtls_certificates/ca/ca.crt \
     health
   ```

2. Test chunking with a simple text:
   ```bash
   python3 -m svo_client.cli --host localhost --port 8009 \
     --cert mtls_certificates/mtls_certificates/client/code-analysis.crt \
     --key mtls_certificates/mtls_certificates/client/code-analysis.key \
     --ca mtls_certificates/mtls_certificates/ca/ca.crt \
     chunk --text "This is a test docstring that should be chunked properly. It contains enough text to be processed."
   ```

3. Check chunker service logs for internal errors

4. Verify chunker service configuration and model availability

## Diagnostic Tools

A comprehensive diagnostic script has been created to analyze the issue:

**Script:** `scripts/diagnose_chunker_server.py`

**Usage:**
```bash
# Using command line arguments
python3 scripts/diagnose_chunker_server.py \
  --host localhost --port 8009 \
  --cert mtls_certificates/mtls_certificates/client/code-analysis.crt \
  --key mtls_certificates/mtls_certificates/client/code-analysis.key \
  --ca mtls_certificates/mtls_certificates/ca/ca.crt

# Or using config file
python3 scripts/diagnose_chunker_server.py --config config.json
```

**Features:**
- Tests health check endpoint
- Tests chunking with multiple text types and lengths
- Captures detailed error information (error types, codes, messages)
- Analyzes response structure when chunks are returned
- Saves results to `logs/chunker_diagnostics_results.json`
- Provides comprehensive summary of all tests

**What it checks:**
1. Client initialization and mTLS certificate loading
2. Health check endpoint response
3. Chunking responses for various text types:
   - Short text (30 chars)
   - Medium text (50-150 chars)
   - Long text (300+ chars)
   - Text with Python code
   - Real docstrings from codebase
4. Response structure analysis (chunk attributes, embeddings, BM25 scores)
5. Error type and message capture

## Next Steps

1. **Immediate:** 
   - Run diagnostic script: `python3 scripts/diagnose_chunker_server.py --config config.json`
   - Review diagnostic results in `logs/chunker_diagnostics_results.json`
   - Check chunker service logs for internal errors
2. **Short-term:** 
   - Verify chunker service configuration (model paths, language detection settings)
   - Test chunker service with different text types and languages
   - Check if chunker service requires specific parameters (language, type, etc.)
3. **Medium-term:** 
   - Analyze diagnostic results to identify patterns in failures
   - Test chunker service API directly (bypassing svo_client library)
   - Check chunker service version compatibility
4. **Long-term:** 
   - Implement fallback mechanism or alternative chunking service
   - Consider implementing local chunking as fallback

## Additional Notes

- The code_analysis server correctly handles these errors:
  - Logs warnings for failed chunks
  - Retries with exponential backoff
  - Continues processing other files
  - Does not crash or hang

- mTLS configuration is correct:
  - Certificates exist and are readable
  - Health check succeeds
  - Connection is established

- The issue is isolated to the chunking endpoint, not the connection layer.

