# Step 04: Extract "open and probe once" for startup

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ.md](../TZ.md)

---

## Executor role

Implementer: in base_mcp_command_open_db.py, extract the logic that performs integrity check, creates DatabaseClient, connect(), and runs the two probe selects (and sync_schema if needed) into a single function that can be called once at startup. Keep open_database_from_config_impl as-is or refactor it to call this new function so that Step 02 can call the same logic without duplicating code.

---

## Execution directive

- Execute only this step.
- Read every file listed in "Read first" before editing.
- Modify only the target code file.
- Do not change startup/shutdown or BaseMCPCommand in this step.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/commands/base_mcp_command_open_db.py`
- **Step type:** Refactor / extract function
- **Primary purpose:** Provide a function "open database and run probe once" (integrity + connect + probe selects + optional sync_schema) so that main_app_events (Step 02) can call it without duplicating logic.

---

## Dependency contract

- **Prerequisites:** Step 01 (shared_database exists). Step 02 may call this new function; if Step 02 was implemented with inlined logic, this step extracts it here so that both startup and any future caller use one implementation.
- **Unlocks:** Cleaner startup code in Step 02 (if not already done).
- **Forbidden scope expansion:** Do not change main_app_events or BaseMCPCommand in this step.

---

## Required context

- TZ: integrity and probe run once at startup. The same logic currently lives in open_database_from_config_impl; it must be reusable by the startup path.

---

## Read first

- `docs/plans/long_lived_db_connection/TZ.md` (sections 3.5, 3.6)
- `code_analysis/commands/base_mcp_command_open_db.py` (full file)

---

## Expected file change

- Add a new function, e.g. `open_database_once_for_shared(resolve_config_path_fn, get_socket_path_fn) -> DatabaseClient`, that: resolves config path, loads config, resolves storage, ensures integrity; if not OK raises DatabaseError; creates DatabaseClient(socket_path), connect(); runs the two probe selects and sync_schema when needed (same as current open_database_from_config_impl); returns the DatabaseClient. Optionally refactor open_database_from_config_impl to call this function so there is no duplicated logic. If open_database_from_config_impl is still used by workers or tests that run outside the server process, keep it and have it call open_database_once_for_shared so one implementation exists.
- Do not remove ensure_database_integrity or _schema_def_to_driver_format; they are used by the new function.

---

## Forbidden alternatives

- Do not run integrity or probe in any code path that is invoked per-command. Only in a single "open once" path.

---

## Atomic operations

1. Extract the sequence (integrity → create client → connect → probe 1 → probe 2 / sync_schema) into open_database_once_for_shared(resolve_config_path_fn, get_socket_path_fn) returning DatabaseClient.
2. If appropriate, make open_database_from_config_impl call open_database_once_for_shared with BaseMCPCommand._resolve_config_path and _get_socket_path_from_db_path so that workers/tests that still call open_database_from_config_impl get the same behaviour.
3. Document the function: "Called once at server startup to establish the long-lived connection; do not call per-command."

---

## Expected deliverables

- One function that performs "open and probe once"; used by startup (and optionally by open_database_from_config_impl). No duplication of integrity/probe logic.

---

## Mandatory validation

- From project root: `black code_analysis/commands/base_mcp_command_open_db.py`, `flake8 code_analysis/commands/base_mcp_command_open_db.py`, `mypy code_analysis/commands/base_mcp_command_open_db.py`, then `pytest`. All tests must pass.

---

## Decision rules

- If the file exceeds 350–400 lines after the change, split into two files (e.g. keep open_database_from_config_impl in base_mcp_command_open_db.py and move open_database_once_for_shared to a small helper module) in the same step.

---

## Blackstops

- Stop if main_app_events or BaseMCPCommand or any command file is modified in this step.

---

## Handoff package

Return: modified file; confirmation of Read first; validation evidence; blockers or risks.
