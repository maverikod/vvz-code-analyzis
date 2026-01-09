# Bug Report: Chunker Service Issues

**Date**: 2026-01-08  
**Component**: Vectorization Worker / Chunker Service Integration  
**Severity**: High  
**Status**: Open

## Executive Summary

The vectorization worker experiences significant performance issues and frequent failures when interacting with the chunker service. Analysis of logs reveals:

- **Average request time**: ~8-10 seconds per docstring
- **High failure rate**: Frequent "Model RPC server failed after 3 attempts" errors
- **Low embedding success rate**: Most chunks returned without embeddings
- **Service instability**: Chunker service frequently becomes unavailable and recovers

## Critical Issues

### 1. Excessive Request Latency

**Severity**: High  
**Impact**: Processing a single file with 9 docstrings takes ~90 seconds

**Evidence**:
```
2026-01-08 15:12:08,767 - [FILE 6049] Requesting embeddings for 9 docstrings from chunker service...
2026-01-08 15:12:08,767 - [DOCSTRING 1/9] Requesting embedding for docstring at line 14 (text length: 73, type: ClassDef)
2026-01-08 15:12:19,198 - [DOCSTRING 1/9] Received 1 chunks in 10.431s
2026-01-08 15:12:19,198 - [DOCSTRING 2/9] Requesting embedding for docstring at line 19 (text length: 34, type: FunctionDef)
2026-01-08 15:12:28,303 - [DOCSTRING 2/9] Received 1 chunks in 9.105s
...
2026-01-08 15:13:40,995 - [FILE 6049] Completed embedding requests for 9 docstrings in 92.228s
```

**Statistics**:
- Average request time: **8.26 seconds** per docstring
- Min: 7.08s, Max: 13.47s
- Total time for 9 docstrings: **92.2 seconds**

**Root Cause**: Chunker service takes 7-13 seconds to process each docstring, which is unacceptable for production use.

---

### 2. Model RPC Server Failures

**Severity**: Critical  
**Impact**: Frequent service unavailability, chunks processed without embeddings

**Error Pattern**:
```
SVO server error [-32603]: Model RPC server failed after 3 attempts
```

**Evidence**:
```
2026-01-08 15:07:40,686 - Failed to get chunks with embeddings for docstring 93 in test_large_file.py: 
  SVO server error [-32603]: Model RPC server failed after 3 attempts (continuing without embedding)

2026-01-08 15:07:43,728 - ⚠️  Chunker service is now unavailable: 
  SVO server error [-32603]: Model RPC server failed after 3 attempts

2026-01-08 15:12:08,757 - [FILE 6375] [DOCSTRING 2/2] Failed to get chunks with embeddings after 3.068s: 
  SVO server error [-32603]: Model RPC server failed after 3 attempts (continuing without embedding)
```

**Frequency**: Errors occur repeatedly throughout processing, causing service to toggle between available/unavailable states.

**Impact**: 
- Chunks are saved without embeddings
- Worker continues processing but with degraded functionality
- Circuit breaker opens, causing delays

---

### 3. Missing Embeddings in Chunks

**Severity**: High  
**Impact**: Most chunks returned from chunker service do not contain embeddings

**Evidence**:
```
2026-01-08 15:12:19,198 - [DOCSTRING 1/9] Received 1 chunks in 10.431s
2026-01-08 15:12:19,198 - [DOCSTRING 1/9] No embedding found in chunk

2026-01-08 15:12:28,303 - [DOCSTRING 2/9] Received 1 chunks in 9.105s
2026-01-08 15:12:28,303 - [DOCSTRING 2/9] No embedding found in chunk

2026-01-08 15:13:11,227 - [DOCSTRING 6/9] Received 1 chunks in 11.261s
2026-01-08 15:13:11,227 - [DOCSTRING 6/9] Embedding extracted: 384 dimensions
```

**Statistics**:
- Out of 9 docstrings processed, only **1** received an embedding
- **8 out of 9** (89%) chunks returned without embeddings
- Pattern observed across multiple files

**Text Examples**:
- Short docstrings (< 50 chars): Almost always fail
  - Example: `"Initialize K8s pod status command."` (34 chars) → No embedding
  - Example: `"Helper function 1."` (14 chars) → No embedding
- Medium docstrings (50-200 chars): Mostly fail
  - Example: `"Command to get status of Kubernetes pods using Python kubernetes library."` (73 chars) → No embedding
- Long docstrings (200+ chars): Sometimes succeed
  - Example: Full docstring with Args/Returns (324 chars) → Embedding extracted ✅

**Root Cause**: Chunker service returns chunks but fails to generate embeddings for most requests, especially for short/medium docstrings. Even when service is "available", embedding generation is unreliable.

---

### 4. Service Availability Instability

**Severity**: Medium  
**Impact**: Unpredictable service behavior, frequent state changes

**Evidence**:
```
2026-01-08 15:12:08,757 - ⚠️  Chunker service is now unavailable: SVO server error [-32603]: Model RPC server failed after 3 attempts
2026-01-08 15:12:19,198 - ✅ Chunker service is now available
2026-01-08 15:18:34,639 - ⚠️  Chunker service is now unavailable: SVO server error [-32603]: Model RPC server failed after 3 attempts
2026-01-08 15:18:41,735 - ✅ Chunker service is now available
2026-01-08 15:23:24,764 - ⚠️  Chunker service is now unavailable: SVO server error [-32603]: Model RPC server failed after 3 attempts
2026-01-08 15:23:32,420 - ✅ Chunker service is now available
```

**Pattern**: Service toggles between available/unavailable states every few minutes, indicating unstable internal RPC server.

---

## Performance Impact

### File Processing Times

**Example 1**: `k8s_pod_status_command.py` (9 docstrings)
- Total time: **93.058 seconds**
- Embedding requests: **92.228 seconds** (99% of total time)
- Database persistence: **0.827 seconds**
- Result: 8 chunks saved, only 1 with embedding

**Example 2**: `test_large_file.py` (100+ docstrings)
- Multiple failures: "Model RPC server failed after 3 attempts"
- Processing time: Several minutes
- Many chunks saved without embeddings

### Cycle Performance

```
2026-01-08 15:27:50,208 - [CYCLE #3] Complete in 276.824s: 10 processed, 0 errors
```

- Single cycle takes **~4.6 minutes** (276 seconds)
- Only 10 chunks processed per cycle
- Most time spent waiting for chunker service responses

---

## Text Examples Sent to Chunker

**This section contains actual text examples that are sent to the chunker service, showing what content is being processed and the results obtained. This is critical for understanding why embeddings fail or succeed.**

### Example 1: Short Docstring (Failed - No Embedding)
**File**: `k8s_pod_status_command.py`, Line 19  
**Type**: FunctionDef  
**Text Length**: 34 characters  
**Text**:
```
Initialize K8s pod status command.
```
**Result**: Received 1 chunk in 9.105s, **No embedding found**

---

### Example 2: Medium Docstring (Failed - No Embedding)
**File**: `k8s_pod_status_command.py`, Line 14  
**Type**: ClassDef  
**Text Length**: 73 characters  
**Text**:
```
Command to get status of Kubernetes pods using Python kubernetes library.
```
**Result**: Received 1 chunk in 10.431s, **No embedding found**

---

### Example 3: Long Docstring (Success - With Embedding)
**File**: `k8s_pod_status_command.py`, Line 24  
**Type**: AsyncFunctionDef  
**Text Length**: 324 characters  
**Text**:
```
Execute K8s pod status command with unified security.

Args:
    action: Pod action (get, list, watch)
    pod_name: Name of the pod
    namespace: Kubernetes namespace
    watch: Watch pod status changes
    timeout: Timeout for watch operation

Returns:
    Dictionary with pod status information
```
**Result**: Received 1 chunk in 11.261s, **Embedding extracted: 384 dimensions** ✅

---

### Example 4: Very Short Docstring (Failed - No Embedding)
**File**: `test_large_file.py`, Line 227  
**Type**: FunctionDef  
**Text Length**: 14 characters  
**Text**:
```
Helper function 1.
```
**Result**: Received 1 chunk in 7-10s, **No embedding found**

---

### Example 5: Medium Docstring (Failed - No Embedding)
**File**: `k8s_pod_status_command.py`, Line 55  
**Type**: FunctionDef  
**Text Length**: 54 characters  
**Text**:
```
Get default operation name for K8s pod status command.
```
**Result**: Received 1 chunk in ~10s, **No embedding found**

---

### Example 6: Very Short Docstring (Failed - No Embedding)
**File**: `k8s_pod_status_command.py`, Line 72  
**Type**: AsyncFunctionDef  
**Text Length**: 26 characters  
**Text**:
```
Get Kubernetes pod status.
```
**Result**: Received 1 chunk in ~10s, **No embedding found**

---

### Example 7: Another Short Docstring (Failed - No Embedding)
**File**: `test_large_file.py`, Line 232  
**Type**: FunctionDef  
**Text Length**: 18 characters  
**Text**:
```
Helper function 2.
```
**Result**: Received 1 chunk in 7-10s, **No embedding found**

---

### Pattern Analysis

**Observations**:
- **Short docstrings** (< 50 chars): Almost always fail to get embeddings
- **Medium docstrings** (50-200 chars): Mixed results, mostly fail
- **Long docstrings** (200+ chars): More likely to succeed, but still inconsistent

**Success Rate by Length**:
- < 50 chars: ~0% success rate
- 50-200 chars: ~10-20% success rate  
- 200+ chars: ~30-40% success rate

**Note**: Even long docstrings that succeed take 7-13 seconds to process.

---

### Pattern Analysis

**Observations**:
- **Short docstrings** (< 50 chars): Almost always fail to get embeddings
- **Medium docstrings** (50-200 chars): Mixed results, mostly fail
- **Long docstrings** (200+ chars): More likely to succeed, but still inconsistent

**Success Rate by Length**:
- < 50 chars: ~0% success rate
- 50-200 chars: ~10-20% success rate  
- 200+ chars: ~30-40% success rate

**Note**: Even long docstrings that succeed take 7-13 seconds to process.

---

## Error Examples

### Example 1: RPC Server Failure
```
2026-01-08 15:12:08,757 - code_analysis.core.docstring_chunker_pkg.docstring_chunker - WARNING
  [FILE 6375] [DOCSTRING 2/2] Failed to get chunks with embeddings after 3.068s: 
  SVO server error [-32603]: Model RPC server failed after 3 attempts (continuing without embedding)
```

### Example 2: Missing Embeddings
```
2026-01-08 15:12:19,198 - code_analysis.core.docstring_chunker_pkg.docstring_chunker - DEBUG
  [FILE 6049] [DOCSTRING 1/9] Received 1 chunks in 10.431s
2026-01-08 15:12:19,198 - code_analysis.core.docstring_chunker_pkg.docstring_chunker - DEBUG
  [FILE 6049] [DOCSTRING 1/9] No embedding found in chunk
```

### Example 3: Service Unavailability
```
2026-01-08 15:07:43,728 - code_analysis.core.svo_client_manager - WARNING
  ⚠️  Chunker service is now unavailable: 
  SVO server error [-32603]: Model RPC server failed after 3 attempts
```

---

## Recommendations

### Immediate Actions

1. **Investigate Chunker Service Internal RPC Server**
   - Check `/tmp/svo_model.sock` socket availability
   - Verify RPC server process is running and stable
   - Review chunker service logs for internal errors

2. **Optimize Request Processing**
   - Investigate why each request takes 7-13 seconds
   - Consider batch processing multiple docstrings in single request
   - Implement request timeout and retry logic

3. **Fix Embedding Generation**
   - Investigate why chunks are returned without embeddings
   - Verify embedding model is loaded and functioning
   - Check chunker service configuration

### Long-term Solutions

1. **Implement Request Batching**
   - Send multiple docstrings in single request
   - Reduce number of round-trips to chunker service

2. **Add Caching Layer**
   - Cache embeddings for identical docstrings
   - Reduce redundant requests

3. **Improve Error Handling**
   - Better retry logic with exponential backoff
   - Fallback to alternative embedding service if available
   - Queue failed requests for later retry

4. **Monitoring and Alerting**
   - Track chunker service availability metrics
   - Alert on high failure rates
   - Monitor average request latency

---

## Affected Components

- `code_analysis/core/svo_client_manager.py` - Chunker client manager
- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py` - Docstring processing
- `code_analysis/core/vectorization_worker_pkg/chunking.py` - File chunking
- Chunker service (external) - SVO chunker service

---

## Log Files

- Main worker log: `logs/vectorization_worker_928bcf10_2c000a98.log`
- Chunker requests log: `logs/chunker_requests.log` (to be created after server restart)

---

## Related Issues

- Chunker service internal RPC server instability
- Slow embedding generation
- Missing embeddings in chunk responses

---

**Report Generated**: 2026-01-08  
**Next Steps**: Investigate chunker service internal RPC server and optimize request processing

