# Step 01: Add import-path regression test

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`tests/regression/test_project_management_import_paths.py`

## Task

Create a regression test module that imports these command modules and fails if any import raises `ModuleNotFoundError`:

- `project_management_mcp_commands.list_trashed_projects`
- `project_management_mcp_commands.permanently_delete_from_trash`
- `project_management_mcp_commands.restore_project_from_trash`
- `project_management_mcp_commands.delete_project`
- `project_management_mcp_commands.delete_unwatched_projects`
- `project_management_mcp_commands.change_project_id`
- `project_management_mcp_commands.list_projects`

Use direct module imports (no monkeypatching). Assert import success explicitly.

## Validation

- `black tests/regression/test_project_management_import_paths.py`
- `flake8 tests/regression/test_project_management_import_paths.py`
- `mypy tests/regression/test_project_management_import_paths.py`
- `pytest tests/regression/test_project_management_import_paths.py -q`

