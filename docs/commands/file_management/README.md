# File Management Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for file lifecycle and DB repair: cleanup deleted files, collapse versions, repair database, unmark deleted file.

## Commands → File Mapping

| MCP Command Name    | Class                      | Source File                            |
|---------------------|----------------------------|----------------------------------------|
| cleanup_deleted_files| CleanupDeletedFilesMCPCommand| `commands/file_management_mcp_commands.py`|
| unmark_deleted_file | UnmarkDeletedFileMCPCommand | (same)                                 |
| collapse_versions   | CollapseVersionsMCPCommand  | (same)                                 |
| repair_database     | RepairDatabaseMCPCommand    | (same)                                 |

Internal commands: `CleanupDeletedFilesCommand`, `CollapseVersionsCommand`, `RepairDatabaseCommand`, `UnmarkDeletedFileCommand` in `commands/file_management.py`. All MCP commands inherit from `BaseMCPCommand`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
