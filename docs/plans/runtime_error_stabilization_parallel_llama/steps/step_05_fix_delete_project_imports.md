# Step 05: Fix imports in delete_project

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/delete_project.py`

## Exact change

Inside `execute()` replace:

- `from ..core.exceptions ...` -> `from ...core.exceptions ...`
- `from ..core.storage_paths ...` -> `from ...core.storage_paths ...`
- `from ..core.database_client.client ...` -> `from ...core.database_client.client ...`
- `from .base_mcp_command ...` -> `from ..base_mcp_command ...`
- `from .project_deletion ...` -> `from ..project_deletion ...`

## Validation

- `black code_analysis/commands/project_management_mcp_commands/delete_project.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/delete_project.py`
- `mypy code_analysis/commands/project_management_mcp_commands/delete_project.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

