# Bug Report: ChunkerClient Connection Error with mTLS

**Author:** Vasiliy Zdanovskiy  
**Email:** vasilyvz@gmail.com  
**Date:** 2025-12-13  
**Severity:** High  
**Status:** Open

## Summary

ChunkerClient fails to connect to SVO chunker service via mTLS, returning "Connection error: localhost:8009/cmd" even though mTLS handshake is successful and `/health` endpoint works correctly.

## Environment

- **OS:** Linux 6.8.0-88-generic
- **Python:** 3.12
- **Package:** code_analysis
- **Chunker Service:** localhost:8009 (mTLS)
- **Embedding Service:** localhost:8001 (mTLS)
- **Library:** svo_client (ChunkerClient)

## Configuration

```json
{
  "chunker": {
    "enabled": true,
    "url": "localhost",
    "port": 8009,
    "protocol": "mtls",
    "cert_file": "mtls_certificates/client/svo-chunker.crt",
    "key_file": "mtls_certificates/client/svo-chunker.key",
    "ca_cert_file": "mtls_certificates/ca/ca.crt"
  },
  "embedding": {
    "enabled": true,
    "url": "localhost",
    "port": 8001,
    "protocol": "mtls",
    "cert_file": "mtls_certificates/client/embedding-service.crt",
    "key_file": "mtls_certificates/client/embedding-service.key",
    "ca_cert_file": "mtls_certificates/ca/ca.crt"
  }
}
```

## Steps to Reproduce

1. Configure mTLS certificates in `config.json`
2. Start MCP server with chunker and embedding services enabled
3. Run project analysis: `analyze_project` tool
4. Check server logs

## Expected Behavior

- ChunkerClient successfully connects to chunker service via mTLS
- `chunk_text()` method works correctly
- Chunks are created and stored in database
- Embeddings are generated and added to FAISS index

## Actual Behavior

- mTLS handshake is successful (verified with curl)
- `/health` endpoint returns 200 OK
- ChunkerClient fails with error: `Connection error: localhost:8009/cmd`
- No chunks are created
- Analysis completes but without semantic chunks

## Error Messages

```
ERROR:code_analysis.core.svo_client_manager:Error chunking text: Connection error: localhost:8009/cmd
```

## Verification Results

### ✅ Working

1. **mTLS Connection:**
   ```bash
   curl --cert mtls_certificates/client/svo-chunker.crt \
        --key mtls_certificates/client/svo-chunker.key \
        --cacert mtls_certificates/ca/ca.crt \
        https://localhost:8009/health
   ```
   - Returns: `200 OK` with health status JSON
   - TLS handshake: Successful (TLSv1.3)
   - Certificate verification: OK

2. **Service Availability:**
   ```bash
   netstat -npl | grep 8009
   ```
   - Port 8009 is listening on 0.0.0.0:8009

3. **Certificates:**
   - All certificate files exist and are readable
   - Certificate chain is valid
   - Client certificate matches service certificate

### ❌ Not Working

1. **ChunkerClient Methods:**
   - `chunk_text()` - fails with connection error
   - `get_embeddings()` - not tested (depends on chunker)
   - `health()` - not tested via ChunkerClient

2. **Endpoint `/cmd`:**
   ```bash
   curl --cert ... --key ... --cacert ... \
        -X POST https://localhost:8009/cmd \
        -H "Content-Type: application/json" \
        -d '{"command": "health"}'
   ```
   - Returns: `404 Not Found`

## Code Analysis

### Methods Used

The following ChunkerClient methods are called in the codebase:

1. **`chunk_text(text, **params)`** - Used in:
   - `code_analysis/core/svo_client_manager.py:82`
   - `code_analysis/core/docstring_chunker.py:307`

2. **`get_embeddings(chunks, **params)`** - Used in:
   - `code_analysis/core/svo_client_manager.py:105`
   - `code_analysis/core/docstring_chunker.py:317`
   - `code_analysis/core/faiss_manager.py:288`
   - `code_analysis/commands/semantic_search.py:95`

3. **`health()`** - Used in:
   - `code_analysis/core/svo_client_manager.py:143,150`

4. **`close()`** - Used in:
   - `code_analysis/core/svo_client_manager.py:160,162`

### Client Initialization

```python
# code_analysis/core/chunker_client_wrapper.py:83
client = ChunkerClient(url=base_url, port=config.port)
# base_url = "https://localhost" for mTLS
# config.port = 8009

# Result: client.base_url = "https://localhost:8009"
```

### SSL Context Setup

```python
# code_analysis/core/chunker_client_wrapper.py:87-96
if config.protocol == "mtls":
    ssl_context = create_ssl_context(...)
    if ssl_context:
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        client.session = aiohttp.ClientSession(connector=connector)
```

## Root Cause Analysis

### Hypothesis 1: Wrong Endpoint
- ChunkerClient tries to use `/cmd` endpoint
- Service returns 404 for `/cmd`
- **Status:** Confirmed - `/cmd` returns 404

### Hypothesis 2: URL Formation Issue
- ChunkerClient may be forming incorrect URL
- Base URL: `https://localhost:8009`
- Error mentions: `localhost:8009/cmd`
- **Status:** Needs investigation - URL format may be incorrect

### Hypothesis 3: Session Not Applied
- SSL context created but session may not be used
- ChunkerClient may create its own session internally
- **Status:** Possible - session assignment may be overridden

### Hypothesis 4: API Version Mismatch
- ChunkerClient may use different API version
- Service may expect different endpoint structure
- **Status:** Needs investigation

## Investigation Needed

1. **Check ChunkerClient source code:**
   - How does it form URLs for `chunk_text()`?
   - What endpoint does it use?
   - Does it respect custom session?

2. **Check service API:**
   - What endpoints are available?
   - What is the correct endpoint for chunking?
   - Check OpenAPI schema: `https://localhost:8009/docs` or `/openapi.json`

3. **Test ChunkerClient directly:**
   ```python
   from svo_client import ChunkerClient
   import aiohttp
   import ssl
   
   ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
   ssl_context.load_cert_chain(cert_file, key_file)
   ssl_context.load_verify_locations(ca_cert_file)
   ssl_context.verify_mode = ssl.CERT_REQUIRED
   ssl_context.check_hostname = False
   
   connector = aiohttp.TCPConnector(ssl=ssl_context)
   client = ChunkerClient(url="https://localhost", port=8009)
   client.session = aiohttp.ClientSession(connector=connector)
   
   # Test chunk_text
   result = await client.chunk_text("test text")
   ```

4. **Check service logs:**
   - What requests does service receive?
   - What errors are logged on server side?

## Workaround

Currently, analysis works but without semantic chunks:
- Files are analyzed
- AST trees are stored
- Classes, functions, methods are extracted
- But docstrings/comments are not chunked
- No embeddings are generated
- FAISS index remains empty

## Proposed Solutions

1. **Fix endpoint in ChunkerClient:**
   - Identify correct endpoint for chunking
   - Update ChunkerClient configuration if possible
   - Or create wrapper that uses correct endpoint

2. **Fix session handling:**
   - Ensure ChunkerClient uses custom session with SSL context
   - Check if ChunkerClient recreates session internally

3. **Update svo_client library:**
   - Report issue to library maintainers
   - Request fix for mTLS support or endpoint configuration

4. **Alternative implementation:**
   - Use direct HTTP client (aiohttp) instead of ChunkerClient
   - Implement chunking API calls manually
   - This would give full control over endpoints and SSL

## Related Files

- `code_analysis/core/chunker_client_wrapper.py` - Client creation
- `code_analysis/core/svo_client_manager.py` - Client usage
- `code_analysis/core/docstring_chunker.py` - Chunking logic
- `config.json` - Configuration

## Logs

### Server Logs
```
INFO:code_analysis.core.svo_client_manager:Initialized chunker client: mtls://localhost:8009
INFO:code_analysis.core.svo_client_manager:Initialized embedding client: mtls://localhost:8001
ERROR:code_analysis.core.svo_client_manager:Error chunking text: Connection error: localhost:8009/cmd
```

### Curl Test
```
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
* Server certificate verify ok
< HTTP/1.1 200 OK
{"status":"ok","version":"1.0.0",...}
```

## Additional Notes

- Same issue likely affects embedding service (port 8001)
- Both services use same mTLS configuration pattern
- Problem is specific to ChunkerClient library usage
- Direct HTTP calls work correctly

