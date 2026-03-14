# Step 03: Fix imports in restore_project_from_trash

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`

## Exact change

Inside `execute()` replace:

- `from ..core.storage_paths ...` -> `from ...core.storage_paths ...`
- `from ..core.trash_utils ...` -> `from ...core.trash_utils ...`
- `from .clear_project_data_impl ...` -> `from ..clear_project_data_impl ...`
- `from ..core.database_client.client ...` -> `from ...core.database_client.client ...`

## Validation

- `black code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`
- `flake8 code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`
- `mypy code_analysis/commands/project_management_mcp_commands/restore_project_from_trash.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

