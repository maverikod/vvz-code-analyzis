# Step 10: Harden DB connect return contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/core/vectorization_worker_pkg/processing_db_connect.py`

## Exact change

Stabilize return contract of `ensure_database_connection()` so callers cannot misread tuple shape:

- Keep 4-value return only.
- Add explicit typed alias (or `NamedTuple`) for return type.
- Update docstring to state exact ordering and semantics.

No behavior change beyond contract clarity.

## Validation

- `black code_analysis/core/vectorization_worker_pkg/processing_db_connect.py`
- `flake8 code_analysis/core/vectorization_worker_pkg/processing_db_connect.py`
- `mypy code_analysis/core/vectorization_worker_pkg/processing_db_connect.py`
- Re-run any targeted test that imports/uses `ensure_database_connection`.

