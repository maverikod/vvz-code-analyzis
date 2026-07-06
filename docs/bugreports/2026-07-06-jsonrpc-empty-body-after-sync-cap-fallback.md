# Bug report — server delivers EMPTY request body to ASGI app after a sync-cap → queue fallback

- **Date:** 2026-07-06
- **Host / instance:** prod `casmgr` @ 192.168.254.26:15010 (all-in-one container), server `code-analysis-server-vvz`
- **Component (owner):** `mcp_proxy_adapter` **8.10.17** — `api/handlers.py` (sync-cap timeout → queue fallback) + `api/core/app_factory_routes.py` (`_read_json_body`). Contributing: `code_analysis/core/command_offload.py` (fire-and-forget thread pool).
- **Severity:** Critical — the entire JSON-RPC / command API of a *running* server becomes permanently unusable until restart. Background workers (indexing/vectorization/watcher) keep running, so the outage is silent.

## Symptom

After ~2h of healthy operation, **every** `POST /api/jsonrpc` (and `POST /api/async`, `POST /api/jsonrpc/batch`) returns, instantly (~4 ms), regardless of payload:

```json
{"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid Request: command is required","data":null},"id":1}
```

Observations that pin the mechanism:

- The response `id` is **always `1`** even when the request sends `"id":777`. `id:1` is the default of the *simplified* branch in `handle_json_rpc` (`request_data.get("id", 1)`), reached only when `request_data` has **neither** `jsonrpc` **nor** `command` key → i.e. `request_data == {}`.
- Sending intentionally malformed JSON (`not json at all`) does **not** produce the expected `400 Invalid JSON body`; it produces the same `-32600` with `id:1`. So `_read_json_body` is **not** seeing the real bytes.
- `Content-Length: 54` is sent and accepted (`hypercorn-h11`, HTTP/1.1), yet the app sees an empty body.
- `GET /health`, `GET /commands` (no request body) work fine and report `registered_count: 194`. Only request paths that read a POST body are affected.
- `curl --cert … https://localhost:15010` **inside the container** (fresh connection, bypassing the external proxy and docker-proxy) reproduces it → not a keep-alive / per-connection framing issue, not a proxy issue.
- Process is healthy: worker threads idle (`WCHAN -`, 0 % CPU), 4 ms responses.

**Net:** `await request.body()` returns empty for every POST → `handle_json_rpc` gets `{}` → simplified branch → "command is required".

## It is a runtime state corruption, NOT a defect reproducible from the current source

The on-disk code (this adapter build + `code_analysis`) parses request bodies **correctly** in every isolated reproduction attempted:

- adapter `setup_routes` on a bare FastAPI (TestClient) — `method` parsed, reaches `execute_command`;
- full `AppFactory().create_app(...)` + OpenAPI priming (`prime_openapi_cache`) — `echo` returns, `id` echoed;
- full `code_analysis.main_app_factory.create_app_with_events(...)` — zero user middleware, body OK;
- **real Hypercorn** (plain HTTP) — body OK;
- **real Hypercorn + mTLS** (identical transport to prod: server/client/ca certs, `CERT_REQUIRED`) — body OK;
- concurrent load (40 parallel POSTs) **while hammering `GET /openapi.json` + `GET /commands`** (simulating the proxy) — 40/40 OK;
- with the adapter global config singleton set (`get_config().config_data`, `feature_manager.config_data`) as `apply_global_config` does — body OK.

So the app object and transport are fine cold. The **live process** started healthy and degraded during its life.

## Timeline (from `docker logs casmgr`) — the transition

The same PID 142 served commands correctly for ~1.5h:

```
09:30:51  Executing command: help                (×many — proxy discovery, OK)
09:30:18  Executing command: tools/call          (body parsed; only fails MethodNotFound)
…         search / search_get_status / list_watch_dirs / list_project_files … all OK
11:05:54  Executing command: list_project_files   <-- LAST command ever executed
```

Then, on the large `code-analyzis` project (**1286 pending items / 1576 files**):

```
11:06:14  WARNING  Command 'list_project_files' timed out after 20.0s (sync cap=20.0s), falling back to queue
11:06:14  Background start for job d340… (command=list_project_files) completed
11:06:14  ✅ mcp_security_framework available in middleware
11:06:14  Registered builtin command: queue_add_job … Registered server engine: hypercorn …   (queue worker bootstrap)
11:06:16  CommandExecutionJob d340…: Starting command execution
```

**After 11:06:14 the main HTTP server (PID 142) never executes another command.** `Executing command:` count by hour: 09h=648, 10h=150, 11h=15 (last at 11:05:54). Background project cycles / scans / bulk-sync continue normally the whole time.

Defunct (zombie) python children appeared at 11:03 / 11:04 / 11:06, coincident with the fallback activity.

## Suspected mechanism

`execute_command` (adapter `api/handlers.py`) runs commands under a hard sync cap:

```python
result_obj = await asyncio.wait_for(
    command_class.run(**params, context=context),
    timeout=effective_timeout,          # _resolve_sync_command_timeout_seconds() → 20s
)
```

For `code_analysis` commands, `command_class.run` → `base_mcp_command.run` → `command_offload.offload_command_run(super().run, kwargs)`, which submits the *blocking* command body to a `ThreadPoolExecutor` and returns `await asyncio.wrap_future(future)`. Its own docstring notes the hazard:

> `command_offload.py`: "if the caller is cancelled (wait_for timeout) CancelledError propagates here **while the worker [thread keeps running]**."

When the 20s `wait_for` fires it **cancels** the coroutine that is parked in `asyncio.wrap_future(future)`, but the `concurrent.futures` worker **thread keeps executing** the slow `list_project_files`. The adapter then calls `_enqueue_command(..., queued_after_timeout=True)`, re-running the same heavy command in the queue worker.

The exact line that leaves `await request.body()` returning empty for **all future** requests has not been isolated to a single statement, but it is deterministically produced by this sync-cap-timeout → cancel → queue-fallback path on a slow offloaded command, and it corrupts request-body handling **process-wide** (not per-connection). Candidate root causes to investigate in the adapter:

1. Cancelling a request handler coroutine mid-flight (via `wait_for`) whose underlying work is a fire-and-forget thread, then re-entering the queue path on the **same** request — the abandoned `wrap_future` done-callback later fires `call_soon_threadsafe` on the loop against an already-cancelled future.
2. The queue-fallback / queuemgr integration re-running adapter bootstrap (`register_builtin_commands`, engine registration) reachable in the serving process and mutating a shared singleton used by request parsing.

## Requested fixes (adapter — do not hand-edit the installed package)

1. **Do not run a fire-and-forget thread under a cancelling `wait_for`.** When the sync cap fires, either (a) let the offloaded future keep the reservation and reuse its result when the queue job would run, or (b) hard-stop enrolling cancel-immune work on the serving loop. Never leave a `wrap_future` whose thread outlives the request.
2. **Isolate the sync cap from body handling.** Verify that a `TimeoutError`/`CancelledError` in `execute_command` cannot leave any per-loop/global state (receive wrappers, cached request, transfer store `_CACHED_TRANSFER_STORE`, config singleton) altered for subsequent requests. Add a regression test: fire the sync-cap timeout on a slow offloaded command under real Hypercorn, then assert a following `POST /api/jsonrpc` still receives its body.
3. **Prevent the trigger:** heavy directory-scale commands (e.g. `list_project_files` on large projects) should be `use_queue=True` (enqueue immediately) rather than relying on the 20s sync-cap fallback. This is a `code_analysis` change and avoids the adapter path entirely for these commands.

## Immediate remediation

Restart the server process (`40-casmgr`). Service returns to normal; the on-disk code is correct. The bug recurs whenever a command breaches the sync cap and takes the offloaded queue-fallback path, so remediation is not durable until fixes 1–3 land.
