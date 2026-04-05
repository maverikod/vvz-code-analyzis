# File Management Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for file lifecycle and DB repair: cleanup deleted files, collapse versions, repair database, unmark deleted file, batch restore deleted files, and line-oriented read/write via `read_project_text_file` / `write_project_text_lines`. **Read:** Python paths auto-route to `get_file_lines`. **Write:** non-code text only; Python and other blocked source suffixes are refused (see each command doc).

See [FILE_TRASH.md](FILE_TRASH.md) for file-level trash layout and behaviour (mark, restore, pre-check, permanent delete).

## Commands → File Mapping

| MCP Command Name     | Class                         | Source File                            |
|----------------------|-------------------------------|----------------------------------------|
| cleanup_deleted_files| CleanupDeletedFilesMCPCommand | `commands/file_management_mcp_commands.py`|
| list_deleted_files   | ListDeletedFilesMCPCommand   | (same)                                 |
| unmark_deleted_file  | UnmarkDeletedFileMCPCommand  | (same)                                 |
| restore_deleted_files| RestoreDeletedFilesMCPCommand| (same)                                 |
| collapse_versions    | CollapseVersionsMCPCommand   | (same)                                 |
| repair_database      | RepairDatabaseMCPCommand     | (same)                                 |
| read_project_text_file | ReadProjectTextFileCommand | `commands/read_project_text_file_command.py` |
| write_project_text_lines | WriteProjectTextLinesCommand | `commands/write_project_text_lines_command.py` |

Internal commands: `CleanupDeletedFilesCommand`, `CollapseVersionsCommand`, `RepairDatabaseCommand`, `UnmarkDeletedFileCommand` in `commands/file_management.py`. All MCP commands inherit from `BaseMCPCommand`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
