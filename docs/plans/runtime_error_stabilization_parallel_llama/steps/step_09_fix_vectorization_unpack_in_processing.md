# Step 09: Fix vectorization DB reconnect unpack

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/core/vectorization_worker_pkg/processing.py`

## Exact change

Ensure call to `ensure_database_connection()` unpacks exactly 4 values:

`database, db_available, backoff, db_status_logged`

and that `db_status_logged` is propagated consistently across retry path.

Do not change cycle semantics.

## Validation

- `black code_analysis/core/vectorization_worker_pkg/processing.py`
- `flake8 code_analysis/core/vectorization_worker_pkg/processing.py`
- `mypy code_analysis/core/vectorization_worker_pkg/processing.py`
- Run targeted worker import/smoke test for processing module.

