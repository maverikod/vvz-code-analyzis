# Commands: Queue + WebSocket (WS) — Tesis-style spec

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## 1. Adapter (mcp-proxy-adapter) — summary

### 1.1 Server entry points

| Entry point | Role |
|-------------|------|
| **POST /api/jsonrpc** | Single command. If `command_class.use_queue == True`: enqueue job, return `job_id` immediately (or server-side poll if `poll_interval > 0`). If `use_queue == False`: run `command_class.run()` in-process with 30s timeout (sync, holds HTTP). |
| **WebSocket /ws** | Client sends `{"action": "subscribe", "job_id": "..."}`. Server pushes `job_completed` / `job_failed` / `job_stopped` (and optionally `job_progress`) to subscribers. Contract: `core/job_push/events.py`. |
| **POST /api/async** | Async execution with `deliver_id`; result delivered via WS to subscribers of that `deliver_id` (separate flow from queue `job_id`). |

### 1.2 Queue + WS flow (use_queue=True)

1. Client calls command via POST /api/jsonrpc.
2. Server: `execute_command()` sees `use_queue=True` → enqueues `CommandExecutionJob`, returns `{ "success": true, "job_id": "<uuid>", "status": "pending" }` without running the command in the HTTP process.
3. Queue worker process runs the command; result is stored in queue manager state.
4. **Job push:** `lifespan_wiring` starts a poll loop that, for each subscribed `job_id`, calls `queue_manager.get_job_status(job_id)`. On terminal state (completed/failed/stopped) it calls `notify_job_state_changed` → listeners build a message (see `events.build_push_message`) and send it to all subscribers of that `job_id` via `/ws`.
5. Client: either subscribes to `/ws` for `job_id` and waits for the push, or polls `queue_get_job_status` (HTTP). Adapter client: `execute_command_unified(..., auto_poll=True)` uses **WebSocket** (`wait_for_job_via_websocket(job_id)`) to get the result — no HTTP polling.

### 1.3 Client (adapter) — execute_command_unified

- First call: `execute_command(command, params)` → JSON-RPC.
- If response contains `job_id` and `auto_poll=True`: connects to `/ws`, sends `{"action": "subscribe", "job_id": job_id}`, waits for terminal event (`job_completed` / `job_failed` / `job_stopped`), returns result. So the **intended** path for queued commands is WS, not HTTP polling.

### 1.4 Examples (in adapter)

- `examples/websocket_examples/client_websocket_job_status.py`: submits a job (e.g. `embed_queue`), gets `job_id`, then `client.wait_for_job_via_websocket(job_id, timeout=60)`.
- `client/jsonrpc_client/command_api.py`: `execute_command_unified` uses `wait_for_job_via_websocket` when it detects `job_id` and `auto_poll=True`.

### 1.5 Job push infrastructure in this project

- Lifespan (adapter) calls `startup_job_push(app, current_config)` → creates `app.state.job_push_registry`, starts poll loop. So **job push is already enabled** when the server runs; no extra config in code_analysis for that.
- `/ws` is registered by adapter when `handle_websocket_job_push` is available.

---

## 2. Current state in code_analysis

- **use_queue = True:** `update_indexes`, `restore_database` (database_restore), `comprehensive_analysis`.
- **use_queue = False:** `list_projects` (fast read-only; sync), and all other custom MCP commands (~75+ command classes in `code_analysis/commands`).
- Sync path: HTTP connection is held until `command_class.run()` finishes (adapter timeout 30s). Long or blocking work leads to timeouts or “Server unavailable” when proxy/client disconnects.

---

## 3. Tesis-style requirements (ТЗ)

### 3.1 Goal

- **All** code_analysis MCP commands must use the **queue + WebSocket** path: no long-held HTTP for command execution.
- HTTP only: accept request → enqueue → return `job_id`. Result delivery via WebSocket `/ws` (or client polling `queue_get_job_status` if it does not use WS).

### 3.2 Constraints

- Do **not** change adapter code; only change code_analysis command classes (attribute `use_queue` and any docs/comments).
- Built-in adapter commands (echo, help, queue_*, etc.) are out of scope; only commands registered by code_analysis.
- Client contract: caller must handle `job_id` (e.g. use `execute_command_unified` with `auto_poll=True`, or subscribe to `/ws` by `job_id`, or poll `queue_get_job_status`). MCP Proxy / Cursor side must be able to pass through job_id and then get result via WS or polling.

### 3.3 Per-command change

- For each command class in `code_analysis/commands` that currently has `use_queue = False`, set `use_queue = True`.
- No change to command logic (e.g. `execute()` / `run()`); only the flag so that the adapter enqueues the command and returns `job_id` instead of running it in the HTTP handler.

### 3.4 Exclusions / checks

- Identify any command that **must** remain sync (e.g. if adapter or proxy cannot handle job_id for that command). Document and leave `use_queue = False` only for those.
- After bulk change: run tests (including pipeline/client tests that use `execute_command_unified` or queue); ensure job push and `/ws` are used and results are returned correctly.

### 3.5 Verification

- Server: queue manager and job push already start in lifespan; `/ws` must be in security public paths if the project restricts unauthenticated routes.
- Client: when calling any code_analysis command, response must contain `job_id`; final result must be obtained via WebSocket (or polling) and not by waiting on the initial HTTP response body.

---

## 4. Plan (high level, no code yet)

1. **Inventory**  
   List all command classes under `code_analysis/commands` with `use_queue = False` (file path, class name, command name).

2. **Exclusions**  
   Decide if any command must stay sync (e.g. health/readiness used by proxy before WS is available). If none, no exclusions.

3. **Bulk change**  
   Set `use_queue = True` for every command in the inventory (except exclusions). Update docstrings/comments where they mention “use_queue” or “queue”.

4. **Config / security**  
   Confirm `/ws` is allowed for the client (e.g. in `security.public_paths` or equivalent) so that subscribers can connect.

5. **Tests**  
   Run existing tests (integration, pipeline mcp_client with `expect_queue=True` / `auto_poll=True`). Fix any that assume sync response (e.g. expect result in first JSON-RPC response without job_id).

6. **Docs**  
   Update project docs to state that all code_analysis commands are queued and result is delivered via WebSocket (or queue_get_job_status).

---

## 5. References

- Adapter: `mcp_proxy_adapter.api.handlers.execute_command` (use_queue branch), `api/core/app_factory_routes.py` (/ws, /api/jsonrpc).
- Adapter: `core/job_push/events.py`, `core/job_push/notifier.py`, `core/job_push/lifespan_wiring.py`.
- Adapter client: `client/jsonrpc_client/command_api.py` (`execute_command_unified`, `wait_for_job_via_websocket`), `client/jsonrpc_client/ws_job_status.py`.
- Example: `examples/websocket_examples/client_websocket_job_status.py`.
- This project: `scripts/pipeline/mcp_client.py` (`call_command` with `use_queue=True` → `execute_command_unified(..., expect_queue=True, auto_poll=True)`).
