# Step A.1 — Driver: expose "index_file" RPC

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`code_analysis/core/database_driver_pkg/` (e.g. new handler in `rpc_handlers*.py` or existing files handler module). Implement the same way as other driver RPCs (same interaction pattern as the vectorization worker’s use of the driver).

## Input

- `file_path` (str) — absolute path to the file (same as stored in `files.path`).
- `project_id` (str) — project UUID.

There is **no** `root_dir` parameter. Project root is defined by the database: table `projects` has `root_path`; table `watch_dirs` and related structures define observed directories. The driver obtains project root from the DB when needed (e.g. `SELECT root_path FROM projects WHERE id = ?`).

## Behaviour

In the driver process:

1. Resolve `file_id` from DB by `path` and `project_id` (e.g. `get_file_by_path`-equivalent).
2. Optionally get project row for `root_path` if needed for validation or path resolution.
3. Read file content from disk using `file_path` (path is absolute).
4. Run the same logic as `update_file_data` for that file:
   - Clear old file data
   - Parse AST, save AST/CST, extract entities, call `add_code_content`

Reuse existing app logic (e.g. `CodeDatabase.update_file_data` or the same code path) so behaviour is identical to the rest of the application.

## Output

Success/failure and optional message (e.g. `"syntax_error"`, `"file_not_found"`).

## Idempotency

Safe to call multiple times; clears then re-creates data for that file.
