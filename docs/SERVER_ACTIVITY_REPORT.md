# Server Activity Report

**Generated:** 2025-12-29 01:15:00  
**Author:** Vasiliy Zdanovskiy  
**Email:** vasilyvz@gmail.com

## Executive Summary

The code-analysis-server is currently operational and functioning normally. The server has successfully registered with the MCP Proxy and is processing commands. However, background workers (file_watcher and vectorization) are not currently running.

## 1. Server Status

### 1.1 MCP Server Status
- **Status:** ✅ Running
- **Server ID:** `code-analysis-server_1`
- **Server URL:** `https://172.28.0.1:15000`
- **Protocol:** mTLS
- **UUID:** `550e8400-e29b-41d4-a716-446655440000`
- **Capabilities:** `jsonrpc`, `health`
- **Total Commands:** 71 registered commands

### 1.2 Proxy Registration
- **Status:** ✅ Successfully registered
- **Proxy URL:** `https://172.28.0.2:3004`
- **Registration Time:** 2025-12-29 01:13:57
- **Heartbeat Status:** ✅ Active (sending every ~30 seconds)
- **Last Heartbeat:** 2025-12-29 01:14:58

### 1.3 Queue Manager
- **Status:** ✅ Initialized
- **Mode:** In-memory mode
- **Integration:** Active

## 2. Recent Activity

### 2.1 Command Execution (Last 10 commands)
Based on log analysis, the following commands were executed recently:

1. **`list_worker_logs`** (4 executions)
   - Execution times: 0.003s, 0.001s, 0.000s, 0.001s
   - Status: ✅ All successful

2. **`view_worker_logs`** (6 executions)
   - Execution times: 0.018s, 0.013s, 0.001s, 0.001s, 0.001s
   - Status: ✅ All successful

### 2.2 Command Performance
- **Average execution time:** < 0.02s
- **Fastest command:** `list_worker_logs` (0.000s)
- **Slowest command:** `view_worker_logs` (0.018s)
- **Total commands processed:** 10+ in the last 2 minutes

## 3. Worker Status

### 3.1 File Watcher Worker
- **Status:** ❌ Not Running
- **Process Count:** 0
- **Last Activity:** 2025-12-29 01:13:34
- **Last Cycle:** Cycle #3
- **Issues:**
  - **1396 errors** in last cycle
  - Multiple "Failed to queue" errors for files in `code_analysis/commands/ast/`
  - Files affected:
    - `code_analysis/commands/ast/dependencies.py`
    - `code_analysis/commands/ast/__init__.py`
    - `code_analysis/commands/ast/get_ast.py`
    - `code_analysis/commands/ast/entity_info.py`
- **Last Scan:**
  - Duration: 3.50s
  - Files scanned: 2252
  - New files: 0
  - Changed files: 0
  - Deleted files: 0

### 3.2 Vectorization Worker
- **Status:** ❌ Not Running
- **Process Count:** 0
- **Last Activity:** 2025-12-29 01:13:33
- **Last Cycle:** Cycle #251
- **Performance:**
  - Last cycle duration: 0.275s
  - Chunks processed: 21
  - Total processed: 4801 chunks
  - Errors: 0
- **FAISS Index:**
  - Status: ✅ Saved successfully
  - Location: `/home/vasilyvz/projects/tools/code_analysis/data/faiss_index`
  - Last save: 2025-12-29 01:13:33 (took 0.010s)

## 4. Error Analysis

### 4.1 Server Errors (mcp_proxy_adapter_error.log)
Recent errors found:

1. **Validation Errors (3 occurrences):**
   - `UpdateIndexesMCPCommand`: Missing `root_dir` parameter (2025-12-29 00:06:23)
   - `JobStatusCommand`: Missing `job_id` parameter (2025-12-29 00:06:29)
   - `GetWorkerStatusMCPCommand`: Missing `worker_type` parameter (2025-12-29 01:11:08)

2. **Historical Errors:**
   - `OSError: [Errno 98] Address already in use` (from previous server instance)
   - `asyncio.exceptions.CancelledError` (from previous server instance)

### 4.2 Worker Errors
- **File Watcher:** 1396 errors in last cycle (all "Failed to queue" errors)
- **Vectorization:** 0 errors (clean operation)

## 5. System Health

### 5.1 Log Files Status
- **Total log files:** 15
- **Server logs:** 3 files
  - `mcp_proxy_adapter.log`: 2.8 MB (22,260 lines)
  - `mcp_proxy_adapter_access.log`: 2.8 MB (22,246 lines)
  - `mcp_proxy_adapter_error.log`: 171 KB (1,913 lines)
- **Worker logs:** 12 files
  - `file_watcher.log`: 9.2 MB (59,413 lines)
  - `vectorization_worker.log`: 3.7 MB (24,027 lines)
  - Plus 10 archived log files

### 5.2 Resource Usage
- **Workers:** Not running (0 CPU, 0 memory)
- **Server:** Normal operation (no resource issues reported)

## 6. Recommendations

### 6.1 Immediate Actions
1. **Investigate File Watcher Queue Errors:**
   - 1396 "Failed to queue" errors need investigation
   - Check queue system connectivity
   - Verify file watcher worker can connect to database

2. **Restart Workers:**
   - File watcher worker should be restarted to clear error state
   - Vectorization worker appears healthy but is not running

### 6.2 Monitoring
1. **Track Command Execution:**
   - Commands are executing successfully
   - Performance is excellent (< 0.02s average)

2. **Watch for Validation Errors:**
   - Some commands are being called with missing parameters
   - Consider adding client-side validation

### 6.3 Maintenance
1. **Log Rotation:**
   - Log files are growing (largest is 9.2 MB)
   - Consider implementing log rotation or cleanup

2. **Error Tracking:**
   - File watcher errors should be investigated
   - Queue connectivity issues need resolution

## 7. Conclusion

The server is **operational and healthy** from a server perspective:
- ✅ Successfully registered with proxy
- ✅ Heartbeat active
- ✅ Commands executing successfully
- ✅ 71 commands available
- ✅ Queue manager initialized

However, **background workers need attention**:
- ❌ File watcher not running (with 1396 errors)
- ❌ Vectorization worker not running (but was healthy when last active)

**Overall Status:** 🟡 **Operational with Warnings**

---

**Report Generated By:** AI Assistant  
**Data Source:** Server logs via MCP Proxy commands  
**Next Review:** Recommended after worker restart

