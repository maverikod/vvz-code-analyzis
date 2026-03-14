# Technical Specification: Runtime Error Stabilization (Parallel LLAMA Execution)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [plan/PLAN.md](plan/PLAN.md)  
**Parallel chains:** [plan/PARALLEL_CHAINS.md](plan/PARALLEL_CHAINS.md)

---

## 1. Objective

Eliminate recurring runtime failures found in server/proxy/driver logs with strict, test-backed fixes:

1. Fix broken relative imports in `project_management_mcp_commands` modules.
2. Stabilize vectorization DB reconnect contract usage.
3. Reduce FK race failures when indexing collides with project deletion.
4. Keep proxy behavior clean after hook cleanup (operational validation included).

---

## 2. Mandatory completion condition

A step is complete only when:

1. Step code changes are done exactly as specified.
2. `black`, `flake8`, and `mypy` pass for touched Python files.
3. Step-specific checks pass.
4. Final gate: **full test suite green**.

---

## 3. Scope

### In scope

- `code_analysis/commands/project_management_mcp_commands/` import fixes in listed files.
- `code_analysis/core/vectorization_worker_pkg/processing.py` unpack contract fix.
- `code_analysis/core/vectorization_worker_pkg/processing_db_connect.py` contract hardening.
- `code_analysis/core/database/files/update.py` and
  `code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py` FK-race hardening.
- New regression tests under `tests/` for import path stability and FK race guards.

### Out of scope

- No mcp_proxy_adapter source changes.
- No architecture rewrite of project deletion flow.
- No fallback codepaths beyond explicit steps.

---

## 4. Root-cause map (from logs)

1. `ModuleNotFoundError: code_analysis.commands.core`:
   commands moved into subpackage, but imports still use `..core` instead of `...core`.
2. `ModuleNotFoundError` for `.clear_project_data_impl` / `.trash_commands`:
   wrong package level; modules exist in parent `code_analysis.commands`.
3. `too many values to unpack (expected 3)` in vectorization:
   `ensure_database_connection()` returns 4 values, caller previously expected 3.
4. `FOREIGN KEY constraint failed` in driver:
   concurrent indexing/write paths can race with project delete/cleanup.
5. `Failed to import 4 modules` in proxy child:
   stale process after hooks cleanup; operational restart/verification required.

---

## 5. Non-negotiable rules for executor model (LLAMA)

- Implement only exact file-level steps.
- Do not invent alternative architecture.
- Do not leave TODOs/placeholders.
- Imports remain at file top unless lazy import is explicitly required by current file design.
- On ambiguity: stop and report, do not improvise.

---

## 6. Step inventory

| Step | Target file | Goal |
|---|---|---|
| 01 | `tests/regression/test_project_management_import_paths.py` | Add regression test for package import validity in project_management MCP modules. |
| 02 | `code_analysis/commands/project_management_mcp_commands/permanently_delete_from_trash.py` | Fix wrong relative imports (`..core` and `.clear_project_data_impl` / `.trash_commands`). |
| 03 | `code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py` | Fix wrong relative imports (`..core` and `.clear_project_data_impl`). |
| 04 | `code_analysis/commands/project_management_mcp_commands/list_trashed_projects.py` | Fix wrong relative import (`..core`). |
| 05 | `code_analysis/commands/project_management_mcp_commands/delete_project.py` | Fix wrong relative imports (`..core`). |
| 06 | `code_analysis/commands/project_management_mcp_commands/delete_unwatched_projects.py` | Fix wrong relative import (`..core`). |
| 07 | `code_analysis/commands/project_management_mcp_commands/change_project_id.py` | Fix wrong relative imports (`..core`). |
| 08 | `code_analysis/commands/project_management_mcp_commands/list_projects.py` | Fix wrong relative import (`..core`). |
| 09 | `code_analysis/core/vectorization_worker_pkg/processing.py` | Ensure 4-value unpack/usage is consistent and explicit. |
| 10 | `code_analysis/core/vectorization_worker_pkg/processing_db_connect.py` | Harden/clarify return contract to prevent caller drift. |
| 11 | `code_analysis/core/database/files/update.py` | Add guard logic against project-delete/index race (FK-safe behavior). |
| 12 | `code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py` | Add RPC-side project existence guard and deterministic error mapping. |
| 13 | `tests/regression/test_index_file_fk_race_guard.py` | Regression test for FK-race hardening paths. |

Execution order and parallelization are defined in `plan/PARALLEL_CHAINS.md`.

---

## 7. Final acceptance

All of the following are required:

1. No `from ..core...` left inside `project_management_mcp_commands` package files.
2. No imports like `from .clear_project_data_impl` / `from .trash_commands` in modules where those live in parent package.
3. Vectorization worker no longer throws unpack mismatch for DB reconnect helper.
4. Indexing path handles missing/deleted project deterministically without FK crash.
5. Full test suite green.

