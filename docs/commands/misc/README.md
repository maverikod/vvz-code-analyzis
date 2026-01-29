# Miscellaneous Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Other commands: analyze project/file, help, check vectors, watch dirs (add/remove). Some may be optional (ImportError handled in hooks).

## Commands → File Mapping

| MCP/Command Name | Class                  | Source File                          |
|------------------|------------------------|--------------------------------------|
| analyze_project  | AnalyzeProjectCommand  | `commands/analyze_project_command` (optional)|
| analyze_file     | AnalyzeFileCommand     | `commands/analyze_file_command` (optional)|
| help             | HelpCommand            | `commands/help_command` (optional)   |
| check_vectors    | CheckVectorsCommand     | `commands/check_vectors_command.py`  |
| add_watch_dir    | AddWatchDirCommand     | `commands/watch_dirs_commands` (optional)|
| remove_watch_dir | RemoveWatchDirCommand  | (same)                               |

Registration: `code_analysis/hooks.py` (try/except for optional commands).

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior where available.
