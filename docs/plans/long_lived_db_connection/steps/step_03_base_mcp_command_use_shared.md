# Step 03: BaseMCPCommand use shared database

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ.md](../TZ.md)

---

## Executor role

Implementer: change BaseMCPCommand so that _open_database_from_config() and _open_database() return the shared database from get_shared_database() instead of calling open_database_from_config_impl(). Commands must not open a new connection; they must get the shared one.

---

## Execution directive

- Execute only this step.
- Read every file listed in "Read first" before editing.
- Modify only the target code file.
- Do not add fallback "if shared not set then open_database_from_config_impl"; get_shared_database() must be the single source; if not set, it will raise.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/commands/base_mcp_command.py`
- **Step type:** Behaviour change
- **Primary purpose:** _open_database_from_config() and _open_database() return get_shared_database() so all commands use the long-lived connection.

---

## Dependency contract

- **Prerequisites:** Step 01 and Step 02 (shared_database module and startup sets it).
- **Unlocks:** Steps 05–09 and 10+ (commands that already use _open_database_from_config or _open_database will now get the shared client; commands that build DatabaseClient directly still need to be switched in later steps).
- **Forbidden scope expansion:** Do not change open_database_from_config_impl or main_app_events in this step.

---

## Required context

- TZ: all MCP commands in the server process must use the shared connection; no per-command open. No fallback to opening a new connection.

---

## Read first

- `docs/plans/long_lived_db_connection/TZ.md` (sections 4, 5, 6)
- `code_analysis/commands/base_mcp_command.py` (full file, especially _open_database_from_config and _open_database)
- `code_analysis/core/shared_database.py` (get_shared_database)

---

## Expected file change

- In BaseMCPCommand, change _open_database_from_config(auto_analyze: bool = False) so that it returns get_shared_database() (and ignores auto_analyze for the server path). Remove the call to open_database_from_config_impl from this path. Add import of get_shared_database from code_analysis.core.shared_database.
- Change _open_database() so that it returns the same (e.g. get_shared_database() or _open_database_from_config(auto_analyze=auto_analyze)) so that all callers receive the shared client.
- _ensure_database_integrity and _resolve_config_path and other helpers remain unchanged. Only the two methods that return a DatabaseClient are changed to use get_shared_database().
- Do not remove or change _get_project_id_by_root_path, _resolve_project_root, _get_shared_storage, etc.

---

## Forbidden alternatives

- Do not add "if get_shared_database() fails then call open_database_from_config_impl". Single source: get_shared_database().
- Do not change any command file in this step.

---

## Atomic operations

1. Add import for get_shared_database from code_analysis.core.shared_database.
2. Replace the body of _open_database_from_config so it returns get_shared_database() (and no longer calls open_database_from_config_impl).
3. Ensure _open_database() still delegates to _open_database_from_config (or directly to get_shared_database()) so both paths return the shared client.

---

## Expected deliverables

- All callers of _open_database_from_config() or _open_database() on BaseMCPCommand receive the shared database client (proxy). No new connection is opened in the server process for these callers.

---

## Mandatory validation

- From project root: `black code_analysis/commands/base_mcp_command.py`, `flake8 code_analysis/commands/base_mcp_command.py`, `mypy code_analysis/commands/base_mcp_command.py`, then `pytest`. All tests must pass.

---

## Decision rules

- If any test or code path runs outside the HTTP server process (e.g. CLI or worker) and expects _open_database_from_config to open a new connection, that path must be identified and either excluded (workers are out of scope) or handled via a separate mechanism; do not re-introduce a fallback in this step.

---

## Blackstops

- Stop if open_database_from_config_impl or main_app_events are modified in this step.
- Stop if a fallback "open new connection" is added.

---

## Handoff package

Return: modified file; confirmation of Read first; validation evidence; blockers or risks.
