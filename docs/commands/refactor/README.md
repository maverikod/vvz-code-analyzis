# Refactor Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for refactoring: extract superclass, split class, split file to package.

## Commands → File Mapping

| MCP Command Name    | Class                      | Source File                        |
|---------------------|----------------------------|------------------------------------|
| extract_superclass  | ExtractSuperclassMCPCommand | `commands/refactor_mcp_commands.py`|
| split_class         | SplitClassMCPCommand       | (same)                             |
| split_file_to_package| SplitFileToPackageMCPCommand| (same)                            |

Internal: `RefactorCommand` in `commands/refactor.py`. Core: `core/refactorer_pkg/` (base, extractor, file_splitter, splitter, validators). Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
