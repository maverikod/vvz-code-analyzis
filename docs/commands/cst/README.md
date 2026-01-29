# CST (Concrete Syntax Tree) Commands Block

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Commands for working with Concrete Syntax Tree: load, save, reload, find node, get node info, get node by range, modify tree, compose module, create file, convert and save; plus list_cst_blocks and query_cst.

## Commands → File Mapping

| MCP Command Name   | Class                     | Source File                              |
|--------------------|---------------------------|------------------------------------------|
| cst_load_file      | CSTLoadFileCommand        | `commands/cst_load_file_command.py`      |
| cst_save_tree      | CSTSaveTreeCommand        | `commands/cst_save_tree_command.py`      |
| cst_reload_tree    | CSTReloadTreeCommand      | `commands/cst_reload_tree_command.py`    |
| cst_find_node      | CSTFindNodeCommand        | `commands/cst_find_node_command.py`      |
| cst_get_node_info  | CSTGetNodeInfoCommand     | `commands/cst_get_node_info_command.py`  |
| cst_get_node_by_range| CSTGetNodeByRangeCommand| `commands/cst_get_node_by_range_command.py`|
| cst_modify_tree    | CSTModifyTreeCommand      | `commands/cst_modify_tree_command.py`    |
| compose_cst_module| ComposeCSTModuleCommand   | `commands/cst_compose_module_command.py` |
| cst_create_file    | CSTCreateFileCommand     | `commands/cst_create_file_command.py`    |
| cst_convert_and_save| CSTConvertAndSaveCommand| `commands/cst_convert_and_save_command.py`|
| list_cst_blocks    | ListCSTBlocksCommand      | `commands/list_cst_blocks_command.py`    |
| query_cst          | QueryCSTCommand           | `commands/query_cst_command.py`          |

All MCP CST commands inherit from `BaseMCPCommand`. Registration: `code_analysis/hooks.py`.

## Detailed Command Descriptions

See [COMMANDS.md](COMMANDS.md) in this directory for per-command schema, parameters, and behavior.
