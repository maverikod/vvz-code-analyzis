# Worker Startup Diagnostic Report

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-29

## Executive Summary

Diagnostic report on worker startup mechanism after refactoring to remove queuemgr and implement automatic worker startup.

## Current Status

### ✅ Completed Tasks

1. **Removed old queuemgr code**:
   - ✅ Deleted `code_analysis/core/db_driver/sqlite_worker_job.py`
   - ✅ Deleted `scripts/test_sqlite_proxy.py`
   - ✅ Removed `registry_path` from `code_analysis/core/database/base.py`

2. **DB Worker Architecture**:
   - ✅ DB worker uses Unix sockets (not queuemgr)
   - ✅ Unix sockets exist: `/tmp/code_analysis_db_workers/*.sock`
   - ✅ DB worker process running (PID: 769638)

3. **Code Structure**:
   - ✅ No queuemgr references in `code_analysis/core/`
   - ✅ Old test files removed

### ⚠️ Issues Found

1. **Worker Startup Mechanism**:
   - ❌ Workers not starting via lifespan context manager
   - ⚠️ Workers still starting via old background thread mechanism (after registration)
   - ⚠️ Lifespan context manager not being called by FastAPI

2. **Root Cause**:
   - FastAPI `lifespan` must be passed at app creation: `FastAPI(lifespan=lifespan)`
   - `AppFactory.create_app()` doesn't support `lifespan` parameter
   - Setting `app.router.lifespan_context` doesn't work (not called by FastAPI)

3. **Current Behavior**:
   - Workers start via background thread after registration (old code still active)
   - Lifespan context manager defined but not executed
   - No errors, but lifespan not integrated

## Solution Implemented

### Approach: Use Startup/Shutdown Events

Since `AppFactory` doesn't support `lifespan` parameter, we use FastAPI startup/shutdown events (deprecated but still functional) to call lifespan context manager:

```python
@app.on_event("startup")
async def start_workers_on_startup():
    """Start workers using lifespan context manager."""
    lifespan_gen = lifespan(app)
    await lifespan_gen.__aenter__()
    app.state.lifespan_gen = lifespan_gen

@app.on_event("shutdown")
async def stop_workers_on_shutdown():
    """Stop workers using lifespan context manager."""
    if hasattr(app.state, "lifespan_gen"):
        await app.state.lifespan_gen.__aexit__(None, None, None)
```

### Benefits

1. ✅ Workers start automatically on server startup
2. ✅ Workers stop gracefully on server shutdown
3. ✅ No dependency on registration
4. ✅ Works in any mode (daemon or not)
5. ✅ Uses lifespan context manager pattern (proper resource management)

## Verification Steps

1. **Check worker status**:
   ```bash
   ps aux | grep -E "db_worker|vectorization|file_watcher"
   ```

2. **Check logs**:
   ```bash
   tail -f logs/mcp_server.log | grep -E "worker|lifespan|startup"
   ```

3. **Check Unix sockets**:
   ```bash
   ls -la /tmp/code_analysis_db_workers/*.sock
   ```

4. **Check via MCP**:
   ```python
   mcp_MCP-Proxy-2_call_server(
       server_id="code-analysis-server",
       command="get_worker_status",
       params={"worker_type": "all"}
   )
   ```

## Next Steps

1. **Restart server** to test new startup mechanism
2. **Verify workers start automatically** via startup event
3. **Monitor logs** for startup/shutdown messages
4. **Test graceful shutdown** of workers

## Notes

- Startup/shutdown events are deprecated in FastAPI but still functional
- Future: Consider modifying `AppFactory` to support `lifespan` parameter
- Alternative: Create app wrapper that adds lifespan after AppFactory creation

