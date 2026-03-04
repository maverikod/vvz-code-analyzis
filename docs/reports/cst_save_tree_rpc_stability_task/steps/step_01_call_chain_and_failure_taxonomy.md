# Step 01 - Call Chain and Failure Taxonomy

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Step metadata

- Chain: `A-BASELINE`
- Step type: `analysis`
- Parallel group: `P2`
- Depends on:
  - `steps/step_00_scope_and_repro_gate.md`
- Unblocks:
  - `steps/step_02_transient_policy_and_contract_gate.md`

## Purpose

Identify exact save-path functions and failure propagation points to avoid speculative fixes.

## Atomic actions

1. Map command entry to persistence:
   - command handler function for `cst_save_tree`,
   - intermediary save orchestrators/services,
   - database client and driver calls.
2. Mark exact points where:
   - socket connect/refusal can occur,
   - SQLite lock errors can surface,
   - exceptions are transformed for MCP response.
3. Determine existing retry behavior:
   - where retries already exist,
   - why they are insufficient for incident scenario.
4. Build precise failure taxonomy table:
   - error signature,
   - source function,
   - transient/non-transient classification,
   - current behavior.

## Required output for this step

Table with columns:
1. `Failure Signature`
2. `Source Module/Function`
3. `Current Handling`
4. `Classification`
5. `Required Change`

## Success criteria

- At least one exact function is identified for each incident class (connect refusal and DB lock).
- No ambiguous statements like "somewhere in DB layer".

## Black stops (hard stop → `STATUS: BLOCKED` for this step)

Stop this step and report block if:

1. **Scope pressure:** Fix would require editing foreign code or files outside repo root.
2. **Step 00 not met:** Baseline evidence or taxonomy from step 00 is missing or contradicted.
3. **Cannot locate code:** Save path or driver/RPC boundary cannot be mapped to concrete modules/functions (codebase opaque or refactor needed first).

Report block with: exact blocker, references to step 00 output if applicable, smallest unblock action.

## Exit criteria

- Proceed only when change points are concrete and reviewable.

---

## Step 01 output (executed 2026-03-04)

### 1. Call chain: command entry → persistence

| Stage | Module / function | Role |
|-------|-------------------|------|
| **Entry** | `code_analysis.commands.cst_save_tree_command.CSTSaveTreeCommand.execute` | MCP command handler; opens DB, resolves path, calls save, returns SuccessResult/ErrorResult. |
| **DB open** | `code_analysis.commands.base_mcp_command.BaseMCPCommand._open_database_from_config` | Resolves socket path from config, creates `DatabaseClient(socket_path)`, calls `db.connect()`. |
| **Socket connect** | `code_analysis.core.database_client.client.DatabaseClient.connect` → `RPCClient.connect` | Pre-creates pool; can raise `ConnectionError` if driver unreachable. |
| **Connect (socket)** | `code_analysis.core.database_client.rpc_client.RPCClient._create_connection` | `socket.socket(AF_UNIX); sock.connect(socket_path)` — **point where "Failed to connect to socket: [Errno 111] Connection refused" originates**. |
| **Save orchestrator** | `code_analysis.core.cst_tree.tree_saver.save_tree_to_file` | Validates, backup, codegen, write temp, begin_transaction, os.replace, update_file_data_atomic_batch, commit_transaction; on any exception logs "Error saving tree to file: {e}" and returns `{success: False, error: str(e)}`. |
| **DB transaction** | `database.begin_transaction()` | RPC `begin_transaction` → driver. |
| **File record** | `database.select("files", ...)`, `database.update_file(file_obj)` or `database.create_file(file_obj)` | RPC select/update/create_file. |
| **File data batch** | `code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch` | Builds batch (clear + AST + CST + classes/methods/functions/imports); calls `database.execute_batch(ops1, transaction_id)` then `execute_batch(ops2)`, `execute_batch(select_ops)`, `execute_batch(ops3)`. |
| **Client execute_batch** | `code_analysis.core.database_client.client_operations.ClientOperationsMixin.execute_batch` | `self.rpc_client.call("execute_batch", rpc_params)` — raises `RPCResponseError` / `RPCClientError` on driver error. |
| **RPC send** | `code_analysis.core.database_client.rpc_client.RPCClient._send_request` | Gets socket from pool or `_create_connection()`; sends request, receives response; raises `ConnectionError` on socket failure, `RPCResponseError` when response contains error. |
| **Driver RPC** | `code_analysis.core.database_driver_pkg.rpc_server` | Dispatches to `handle_execute_batch` (and optionally `handle_update` / `handle_execute` for other code paths). |
| **Driver handler** | `code_analysis.core.database_driver_pkg.rpc_handlers_base.RpcHandlersBase.handle_execute_batch` | Calls `self.driver.execute_batch(operations, transaction_id)`; on exception returns `ErrorResult(description=str(e))` (e.g. "execute_batch failed: database is locked"). |
| **Driver SQL** | `code_analysis.core.database_driver_pkg.drivers.sqlite.SQLiteDriver.execute_batch` | Runs SQL via `cursor.execute` / `cursor.executemany` on SQLite connection; **point where `sqlite3.OperationalError: database is locked` can occur**. |
| **Driver update path** | `code_analysis.core.database_driver_pkg.drivers.sqlite_operations.SQLiteOperations.update` | Used by other flows; raises `DriverOperationError("Failed to update rows: {e}")` — **source of "Failed to update rows: database is locked"** when handler uses update RPC. |
| **Exception → MCP** | `CSTSaveTreeCommand.execute` except block | Catches any exception, logs `logger.exception("cst_save_tree failed: %s", e)`, returns `ErrorResult(message=f"cst_save_tree failed: {e}", code="CST_SAVE_ERROR")`. |

### 2. Retry behaviour

- **Connect (startup):** `RPCClient.connect()` retries for up to `startup_connect_timeout` (default 5s) when creating the first connection; no retry after that for subsequent `_create_connection()` calls used per request.
- **RPC call:** `RPCClient.call()` retries only on `ConnectionError` and `TimeoutError` (up to `max_retries`, default 3, with backoff). It does **not** retry on `RPCResponseError` (e.g. "database is locked" or other driver errors).
- **Save path:** No application-level retry in `save_tree_to_file` or in the command; a single failure (connect or DB lock) immediately returns error to the client.

### 3. Failure taxonomy table

| Failure Signature | Source Module/Function | Current Handling | Classification | Required Change |
|-------------------|------------------------|------------------|----------------|-----------------|
| `Failed to connect to socket: [Errno 111] Connection refused` | `code_analysis.core.database_client.rpc_client.RPCClient._create_connection` (socket.connect) | Exception propagates to `_send_request` → `call()`; `call()` retries on ConnectionError up to max_retries then raises; command catches and returns ErrorResult. Log: "Error saving tree to file: ..." from `tree_saver.save_tree_to_file`. | **Transient** (driver down/restart) | Add bounded retry with backoff for connect/send failures on save path; or centralise in RPCClient with configurable retry for transient socket errors. |
| `Failed to update rows: database is locked` | Driver: `code_analysis.core.database_driver_pkg.drivers.sqlite_operations.SQLiteOperations.update` (cursor.execute + commit). Surfaces via `handle_update` → ErrorResult(description=str(e)). Client: `client_operations.execute_batch` (or update_file) receives RPC error. | Handler returns ErrorResult; client raises RPCResponseError → RPCClientError("RPC call failed: ..."); no retry; tree_saver catches, logs "Error saving tree to file: ...", returns dict; command returns ErrorResult. | **Transient** (SQLite BUSY/locked) | Add retry with backoff for transient DB lock (e.g. in save path or in driver/client for execute_batch) with clear max attempts and idempotency/rollback semantics. |
| `Failed to execute SQL: database is locked` | Driver: `code_analysis.core.database_driver_pkg.drivers.sqlite.SQLiteDriver.execute` or `execute_batch` (cursor.execute/executemany). Surfaces via `handle_execute` / `handle_execute_batch` → ErrorResult(description=str(e)). | Same as above: no retry; error propagates to command as "cst_save_tree failed: RPC call failed: ...". | **Transient** (SQLite BUSY/locked) | Same as above: transient retry policy for lock errors on execute/execute_batch path. |
| `execute_batch failed: database is locked` | Driver: `code_analysis.core.database_driver_pkg.drivers.sqlite.SQLiteDriver.execute_batch` (cursor.execute/executemany in loop). Surfaces via `handle_execute_batch` → ErrorResult(description=str(e)). | Same propagation; logged in driver as "Error in handle_execute_batch: ...". | **Transient** (SQLite BUSY/locked) | Same as above. |
| Tree not found, validation errors, file write errors | `tree_saver.save_tree_to_file` (get_tree, compile, write temp), or BackupManager | Raises ValueError/RuntimeError; tree_saver catches, returns dict with error; command returns ErrorResult. | **Non-transient** (bad input or env) | No retry; keep current behaviour. |
| Database corrupted / schema init failure | `BaseMCPCommand._open_database_from_config` (integrity check, sync_schema) | Raises DatabaseError; command never reaches save. | **Non-transient** | No change for this step. |

### 4. Summary

- **Connect refusal:** Exact origin is `RPCClient._create_connection()` (socket.connect). Retry exists only at startup and for ConnectionError in `call()`; insufficient when driver is down for longer or when pool is exhausted and new connection fails.
- **DB lock:** Exact origin is SQLite in `sqlite_operations.update`, `sqlite.SQLiteDriver.execute`, or `sqlite.SQLiteDriver.execute_batch`; surfaced by `rpc_handlers_base.handle_update` / `handle_execute` / `handle_execute_batch` as ErrorResult(description=str(e)). No retry anywhere for lock errors.
- **MCP response:** All failures on the save path are turned into a single exception in the command and returned as `ErrorResult(message=f"cst_save_tree failed: {e}", code="CST_SAVE_ERROR")`.
- **Change points** are concrete and reviewable: `rpc_client.py` (_create_connection / call retry), `tree_saver.save_tree_to_file` (optional retry wrapper or call-site retry), and/or driver/client handling of lock errors for execute_batch/update.
