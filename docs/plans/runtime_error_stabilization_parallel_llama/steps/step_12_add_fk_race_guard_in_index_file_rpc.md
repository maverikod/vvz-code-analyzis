# Step 12: Add FK-race guard in index_file RPC handler

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py`

## Exact change

Harden `handle_index_file()` against project-deleted races:

1. Keep explicit `SELECT root_path FROM projects WHERE id = ?` check.
2. If project missing, return deterministic `ErrorResult` without attempting indexing.
3. Wrap downstream calls so FK exceptions return clear error classification (not generic traceback-only).
4. Do not attempt cleanup SQL for missing project.

## Validation

- `black code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py`
- `flake8 code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py`
- `mypy code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py`
- Run targeted tests for RPC `index_file`.

