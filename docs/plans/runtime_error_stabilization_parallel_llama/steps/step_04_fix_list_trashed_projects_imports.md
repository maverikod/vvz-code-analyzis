# Step 04: Fix imports in list_trashed_projects

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/list_trashed_projects.py`

## Exact change

Inside `execute()` replace:

- `from ..core.storage_paths ...` -> `from ...core.storage_paths ...`
- `from .trash_commands ...` -> `from ..trash_commands ...`

## Validation

- `black code_analysis/commands/project_management_mcp_commands/list_trashed_projects.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/list_trashed_projects.py`
- `mypy code_analysis/commands/project_management_mcp_commands/list_trashed_projects.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

