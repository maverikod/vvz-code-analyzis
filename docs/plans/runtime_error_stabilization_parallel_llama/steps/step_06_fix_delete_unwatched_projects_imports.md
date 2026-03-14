# Step 06: Fix imports in delete_unwatched_projects

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/delete_unwatched_projects.py`

## Exact change

Inside `execute()` replace:

- `from ..core.storage_paths ...` -> `from ...core.storage_paths ...`
- `from .delete_unwatched_projects_command ...` -> `from ..delete_unwatched_projects_command ...`

In metadata text, remove mention of dynamic watch file if still present.

## Validation

- `black code_analysis/commands/project_management_mcp_commands/delete_unwatched_projects.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/delete_unwatched_projects.py`
- `mypy code_analysis/commands/project_management_mcp_commands/delete_unwatched_projects.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

