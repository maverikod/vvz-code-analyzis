# Step 02: Open long-lived connection at startup and close at shutdown

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ.md](../TZ.md)

---

## Executor role

Implementer: in the HTTP server startup event, after the database driver process is started, open the long-lived database connection (resolve config, integrity once, create DatabaseClient, connect, run probe selects once), then set it in the shared holder. In the shutdown event, close the shared connection then stop workers.

---

## Execution directive

- Execute only this step.
- Read every file listed in "Read first" before editing.
- Modify only the target file and, if necessary, the module that provides "open and probe once" (see Step 04; if that function does not exist yet, implement the minimal logic in this step in main_app_events or call into base_mcp_command_open_db).
- Do not change BaseMCPCommand or any command file in this step.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/main_app_events.py`
- **Step type:** Behaviour change (startup/shutdown)
- **Primary purpose:** At startup, after driver start, open one DB connection (integrity + connect + probe once) and set it via set_shared_database(); at shutdown, call close_shared_database() then stop workers.

---

## Dependency contract

- **Prerequisites:** Step 01 (shared_database module with set_shared_database, get_shared_database, close_shared_database).
- **Unlocks:** Step 03 (commands can use get_shared_database).
- **Forbidden scope expansion:** Do not change command execute() signatures or base_mcp_command open logic in this step.

---

## Required context

- TZ: one long-lived connection; open at startup, close at shutdown; integrity and probe once. **If errors are detected at startup (integrity/connect/probe) → write to log and stop.** Shutdown order: close shared connection then stop workers.

---

## Read first

- `docs/plans/long_lived_db_connection/TZ.md` (sections 3.5, 3.6, 4, 6)
- `code_analysis/main_app_events.py` (full file)
- `code_analysis/commands/base_mcp_command_open_db.py` (open_database_from_config_impl, ensure_database_integrity, probe selects)
- `code_analysis/core/shared_database.py` (set_shared_database, close_shared_database)
- `code_analysis/commands/base_mcp_command.py` (_resolve_config_path, _get_socket_path_from_db_path)

---

## Expected file change

- In the startup handler: after `startup_database_driver()` (inside _start_workers_bg), add: resolve config path, load config, resolve storage paths, ensure_database_integrity(db_path). **If integrity is not OK → log the error and stop** (abort startup; do not continue). If OK: create DatabaseClient(socket_path), connect(); **if connect fails → log and stop**. Run the two probe selects (and sync_schema if needed); **if probe fails → log and stop**. If all succeed, set_shared_database(proxy or client). Use the same config/path resolution as open_database_from_config_impl. **TZ: any error during integrity/connect/probe → write to log and stop.**
- In the shutdown handler: before calling worker_manager.stop_all_workers(), call close_shared_database(). Ensure shutdown event runs in a context where the shared_database module is available.
- No removal of existing worker startup/shutdown; only addition of DB open/set and close_shared_database before stop_all_workers.

---

## Forbidden alternatives

- Do not run integrity or probe selects on every request or in any command.
- Do not close the shared connection after stop_all_workers (TZ specifies close before stop workers).

---

## Atomic operations

1. In _start_workers_bg, after startup_database_driver() succeeds (or after a short wait for driver to be ready), call a helper that: resolves config, runs ensure_database_integrity, creates DatabaseClient, connect(), runs probe selects (and sync_schema if needed), returns the client.
2. Call set_shared_database(returned_client_or_proxy) only when integrity, connect, and probe all succeed. **If integrity fails, or connect fails, or probe fails → log the error and stop** (abort startup; e.g. raise from the startup thread or call sys.exit / trigger app shutdown so the server does not serve requests).
3. In the shutdown handler, call close_shared_database() before stop_all_workers(timeout=...).
4. Ensure the helper that opens the connection is either in main_app_events or imported from base_mcp_command_open_db (e.g. a new function open_database_for_shared_once() that does integrity + connect + probes and returns the client).

---

## Expected deliverables

- Server startup sets the shared database once after the driver is started; server shutdown closes it before stopping workers. No per-command open in this step (that is Step 03).

---

## Mandatory validation

- From project root: `black code_analysis/main_app_events.py`, `flake8 code_analysis/main_app_events.py`, `mypy code_analysis/main_app_events.py`, then `pytest`. All tests must pass.

---

## Decision rules

- If "open and probe once" logic is large, extract it to a function in base_mcp_command_open_db.py and import it here; do not duplicate the whole of open_database_from_config_impl.
- If the startup thread runs before the driver is listening, add a short delay or retry loop (bounded) before connect(); document in code comment.

---

## Blackstops

- Stop if BaseMCPCommand or any command file is modified in this step.
- Stop if integrity or probe runs outside the single startup path.
- Stop if on integrity/connect/probe failure the server continues to start instead of logging and stopping.

---

## Handoff package

Return: modified file(s); confirmation of Read first; validation evidence; blockers or risks.
