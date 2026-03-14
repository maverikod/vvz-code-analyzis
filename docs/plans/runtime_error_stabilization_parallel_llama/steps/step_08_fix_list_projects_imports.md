# Step 08: Fix imports in list_projects

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/list_projects.py`

## Exact change

Replace the local import:

- `from ..core.exceptions import ValidationError`

with:

- `from ...core.exceptions import ValidationError`

No other logic changes.

## Validation

- `black code_analysis/commands/project_management_mcp_commands/list_projects.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/list_projects.py`
- `mypy code_analysis/commands/project_management_mcp_commands/list_projects.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

