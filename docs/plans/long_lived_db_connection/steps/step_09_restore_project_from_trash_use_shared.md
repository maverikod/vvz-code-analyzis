# Step 09: restore_project_from_trash use shared database

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ.md](../TZ.md)

---

## Executor role

Implementer: replace the direct construction of DatabaseClient(socket_path) and database.connect() in restore_project_from_trash with the shared database access (e.g. self._open_database_from_config() or get_shared_database()). Remove local config_path/config_data/storage/socket_path resolution and direct DatabaseClient instantiation. Keep the rest of the command logic unchanged; keep database.disconnect() in finally (it will be a no-op when using the shared proxy).

---

## Execution directive

- Execute only this step.
- Read every file listed in "Read first" before editing.
- Modify only the target code file.
- Do not change shared_database, base_mcp_command, or main_app_events in this step.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`
- **Step type:** Refactor command to use shared DB
- **Primary purpose:** restore_project_from_trash must use the long-lived connection instead of opening its own.

---

## Dependency contract

- **Prerequisites:** Step 03 (BaseMCPCommand._open_database_from_config returns get_shared_database()).
- **Unlocks:** None (other command steps are independent).
- **Forbidden scope expansion:** Do not change other command files or the shared_database API.

---

## Required context

- TZ: all MCP commands in the server process use the shared connection. Commands that currently build DatabaseClient(socket_path) and connect() must be switched to _open_database_from_config() or get_shared_database().

---

## Read first

- `docs/plans/long_lived_db_connection/TZ.md` (sections 2, 4)
- `code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py` (full execute path)

---

## Expected file change

- In the execute() path, remove the block that: loads config, resolves storage, gets socket_path, creates DatabaseClient(socket_path), and calls database.connect(). Replace with: database = self._open_database_from_config(auto_analyze=False). Keep the try/finally that calls database.disconnect() (no-op with shared proxy).

---

## Forbidden alternatives

- Do not leave a second path that still creates DatabaseClient(socket_path) for the same command execution.

---

## Atomic operations

1. Replace DatabaseClient(socket_path) + connect() with self._open_database_from_config(auto_analyze=False).
2. Remove the local resolution of socket_path and the import of DatabaseClient for that use if no longer needed.
3. Leave database.disconnect() in finally unchanged.

---

## Expected deliverables

- restore_project_from_trash uses the shared database for its entire execute path; no per-call connection open.

---

## Mandatory validation

- From project root: `black code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`, `flake8 code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`, `mypy code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`, then `pytest`. All tests must pass.

---

## Decision rules

- Same pattern as Step 05 (delete_project); only the target file differs.

---

## Blackstops

- Stop if shared_database.py, base_mcp_command.py, or main_app_events.py are modified in this step.

---

## Handoff package

Return: modified file; confirmation of Read first; validation evidence; blockers or risks.
