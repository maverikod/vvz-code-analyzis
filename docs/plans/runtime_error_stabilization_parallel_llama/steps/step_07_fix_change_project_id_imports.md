# Step 07: Fix imports in change_project_id

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/change_project_id.py`

## Exact change

Replace all `from ..core...` imports in this module with `from ...core...`.

Keep imports from sibling/parent command modules unchanged unless import errors show they must move one level up.

## Validation

- `black code_analysis/commands/project_management_mcp_commands/change_project_id.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/change_project_id.py`
- `mypy code_analysis/commands/project_management_mcp_commands/change_project_id.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

