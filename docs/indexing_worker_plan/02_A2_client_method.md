# Step A.2 — DatabaseClient: add method that calls the new RPC

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`code_analysis/core/database_client/` (e.g. `client_api_files.py` or a new small module for "indexing" API). Same pattern as for the vectorization worker: one method that builds the RPC and returns the result.

## Method

- Name: e.g. `index_file(file_path: str, project_id: str) -> dict`
- Parameters: `file_path` (absolute, as in `files.path`), `project_id` (project UUID). **No** `root_dir` — project root comes from the DB (`projects.root_path`).
- Builds the RPC request, sends to driver, returns result (success, error message, etc.).

## Contract

- `file_path` must be the absolute path stored in the `files` table for this project.
- Driver resolves project root from the database when needed.
