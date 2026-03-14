# Step 11: Add FK-race guard in update_file_data

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/core/database/files/update.py`

## Exact change

Add an early project existence guard before file updates:

1. Query `projects` by `project_id`.
2. If missing, return deterministic non-crashing error payload (success=False, explicit reason).
3. Do not execute write SQL for missing project.

Also handle FK-related DB exceptions in this function with explicit error message (no silent swallow).

## Validation

- `black code_analysis/core/database/files/update.py`
- `flake8 code_analysis/core/database/files/update.py`
- `mypy code_analysis/core/database/files/update.py`
- Run targeted tests related to index/update_file_data.

