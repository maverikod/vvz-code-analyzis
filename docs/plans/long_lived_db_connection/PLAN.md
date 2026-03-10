# Plan: One Long-Lived Database Connection

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [TZ.md](TZ.md)  
**Parallel chains:** [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)

---

## Executor role

You are an executor model (e.g. Llama-level). Implement exactly what is specified in the TZ and in each step file. Do not invent architecture or add forbidden alternatives. Read TZ, then this PLAN, then PARALLEL_CHAINS, then the step file and all "Read first" files in full before writing code. Run mandatory validation after each step; step is complete only when the full test suite passes.

---

## Objective

Implement one long-lived database connection in the HTTP server process: open at startup, close at shutdown; all MCP commands use it; no per-command open/close.

---

## Execution policy

- Each step: 1 step = 1 target code file = 1 step description file in `docs/plans/long_lived_db_connection/steps/`. Do not combine steps or change the target file of a step.
- Before changing code: read every file listed in the step’s “Read first” in full. Read “Expected file change”, “Forbidden alternatives”, and “Blackstops” of that step.
- After code: run `black <target_file>`, `flake8 <target_file>`, `mypy <target_file>` from project root; then run `pytest`. Step is complete only when all tests pass. If any fail, fix and re-run until green.
- No alternative implementations. Follow TZ and each step's “Forbidden alternatives”. If a blackstop is met, stop and report.

---

## Step list (ordered, with dependencies)

| Step | Step file | Target code file | Purpose |
|------|-----------|------------------|---------|
| 01 | `steps/step_01_shared_database_module.md` | `code_analysis/core/shared_database.py` (new) | Shared DB holder: set/get/close and proxy with no-op disconnect. |
| 02 | `steps/step_02_startup_shutdown_connection.md` | `code_analysis/main_app_events.py` | Startup: open connection (integrity + connect + probe once), set in holder. Shutdown: close shared then stop workers. On error at startup: log and stop. |
| 03 | `steps/step_03_base_mcp_command_use_shared.md` | `code_analysis/commands/base_mcp_command.py` | `_open_database_from_config` and `_open_database` return `get_shared_database()`; no `open_database_from_config_impl`. |
| 04 | `steps/step_04_extract_open_once.md` | `code_analysis/commands/base_mcp_command_open_db.py` | Extract "open and probe once" for startup; keep integrity and schema helpers. |
| 05 | `steps/step_05_delete_project_use_shared.md` | `code_analysis/commands/project_management_mcp_commands/delete_project.py` | Replace direct DatabaseClient + connect with `_open_database_from_config()`. |
| 06 | `steps/step_06_list_watch_dirs_use_shared.md` | `code_analysis/commands/project_management_mcp_commands/list_watch_dirs.py` | Same: use shared connection. |
| 07 | `steps/step_07_permanently_delete_from_trash_use_shared.md` | `code_analysis/commands/project_management_mcp_commands/permanently_delete_from_trash.py` | Same: use shared connection. |
| 08 | `steps/step_08_clear_trash_use_shared.md` | `code_analysis/commands/project_management_mcp_commands/clear_trash.py` | Same: use shared connection. |
| 09 | `steps/step_09_restore_project_from_trash_use_shared.md` | `code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py` | Same: use shared connection. |
| 10+ | (add if needed) | Other commands with direct DatabaseClient | Replace with shared per TZ. |

- Order: execute 01 then 02 then 03 then 04. Then 05, 06, 07, 08, 09 in any order (parallel allowed). See PARALLEL_CHAINS.md.
- Mandatory validation per step: from project root run `black <target_file>`, `flake8 <target_file>`, `mypy <target_file>`, `pytest`. Step complete only when all tests pass.

---

## Completion condition

- All steps 01–09 implemented.
- Full test suite green (pytest from project root passes).
- No MCP command in the server process opens its own connection; one long-lived connection opened at startup and closed at shutdown.

---

## Decision rules (plan level)

- If a step says "modify only the target code file" then do not modify any other file in that step.
- If validation fails then fix the target file and re-run until all pass; do not mark step complete until then.
- If in doubt about architecture then re-read TZ section 6 (Forbidden alternatives) and section 9 (Decision rules); do not add fallbacks or pools.

---

## Blackstops (plan level)

- Stop if you are about to add a per-command or per-request connection open in the server process.
- Stop if you are about to add a fallback "if get_shared_database() fails then open new connection".
- Stop if the step's blackstop condition is met; report and do not continue that step.

---

## References

- TZ: [TZ.md](TZ.md) — source of truth.
- Parallel order: [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)
- Step files: `docs/plans/long_lived_db_connection/steps/step_NN_*.md`
