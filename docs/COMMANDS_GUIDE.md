# Commands Guide — Detailed Reference

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

This guide is the main entry point for **all MCP commands** of the code-analysis-server project. Each command is documented in a **separate file** under `docs/commands/<block>/<command_name>.md` with a uniform structure:

- **Purpose (предназначение)** — what the command does, flow, use cases
- **Arguments (аргументы)** — parameters, types, required/optional (aligned with `get_schema()` in code)
- **Returned data (возвращаемые данные)** — success/error shape and format
- **Examples** — correct and incorrect usage, error codes

Quick lookup: [COMMANDS_INDEX.md](COMMANDS_INDEX.md) maps command name → class → source file → doc block.

---

## Documentation standard per command

Every command doc file contains:

| Section | Content |
|--------|--------|
| **Purpose** | Operation flow, validation rules, use cases, important notes |
| **Arguments** | Table: Parameter, Type, Required, Description; `additionalProperties: false` |
| **Returned data** | Success: `SuccessResult` with `data`; Error: `ErrorResult` with `code`, `message` |
| **Examples** | Correct: JSON request examples; Incorrect: error codes and how to fix |
| **Error codes summary** | Table: Code, Description, Action |
| **Best practices** | Short list of recommendations |

Schema source of truth: `code_analysis/commands/**/*.py` → `get_schema()` and `execute()`.

### Versioning before write (backup + optional git)

Before any command modifies existing code, the file is placed in **versions** (backup to `old_code` via BackupManager). This is mandatory for all write commands.

**Optional git:** when the project is a git repository, pass `commit_message` to create a git commit *after* the change. Commands that support it: `cst_save_tree`, `compose_cst_module`. Git does not replace backup: backup is always created before write; git commit is an extra version snapshot after write.

---

## Blocks and command list

### AST — `docs/commands/ast/`

| Command | Doc | Purpose |
|---------|-----|--------|
| get_ast | [get_ast.md](commands/ast/get_ast.md) | Retrieve stored AST for a Python file |
| search_ast_nodes | [search_ast_nodes.md](commands/ast/search_ast_nodes.md) | Search AST by node type/pattern |
| ast_statistics | [ast_statistics.md](commands/ast/ast_statistics.md) | AST statistics for project/file |
| list_project_files | [list_project_files.md](commands/ast/list_project_files.md) | List project files from DB |
| get_code_entity_info | [get_code_entity_info.md](commands/ast/get_code_entity_info.md) | Info for a single code entity |
| list_code_entities | [list_code_entities.md](commands/ast/list_code_entities.md) | List entities (classes, functions, etc.) |
| get_imports | [get_imports.md](commands/ast/get_imports.md) | Imports for file/project |
| find_dependencies | [find_dependencies.md](commands/ast/find_dependencies.md) | Dependency graph for file |
| get_entity_dependencies | [get_entity_dependencies.md](commands/ast/get_entity_dependencies.md) | Dependencies of entity by id (what it calls) |
| get_entity_dependents | [get_entity_dependents.md](commands/ast/get_entity_dependents.md) | Dependents of entity by id (what calls it) |
| get_class_hierarchy | [get_class_hierarchy.md](commands/ast/get_class_hierarchy.md) | Class inheritance hierarchy |
| find_usages | [find_usages.md](commands/ast/find_usages.md) | Find usages of symbol |
| export_graph | [export_graph.md](commands/ast/export_graph.md) | Export dependency/usage graph |

### Backup — `docs/commands/backup/`

| Command | Doc | Purpose |
|---------|-----|--------|
| list_backup_files | [list_backup_files.md](commands/backup/list_backup_files.md) | List unique backed-up files |
| list_backup_versions | [list_backup_versions.md](commands/backup/list_backup_versions.md) | List backup versions for a file |
| restore_backup_file | [restore_backup_file.md](commands/backup/restore_backup_file.md) | Restore file from backup |
| delete_backup | [delete_backup.md](commands/backup/delete_backup.md) | Delete a backup version |
| clear_all_backups | [clear_all_backups.md](commands/backup/clear_all_backups.md) | Clear all backups in project |

### Code Mapper — `docs/commands/code_mapper/`

| Command | Doc | Purpose |
|---------|-----|--------|
| update_indexes | [update_indexes.md](commands/code_mapper/update_indexes.md) | Analyze project and update DB indexes (queue) |
| list_long_files | [list_long_files.md](commands/code_mapper/list_long_files.md) | List files over line threshold |
| list_errors_by_category | [list_errors_by_category.md](commands/code_mapper/list_errors_by_category.md) | List errors grouped by category |

### Code Quality — `docs/commands/code_quality/`

| Command | Doc | Purpose |
|---------|-----|--------|
| format_code | [format_code.md](commands/code_quality/format_code.md) | Format file with Black |
| lint_code | [lint_code.md](commands/code_quality/lint_code.md) | Lint file with Flake8 |
| type_check_code | [type_check_code.md](commands/code_quality/type_check_code.md) | Type-check with Mypy |

### CST — `docs/commands/cst/`

| Command | Doc | Purpose |
|---------|-----|--------|
| cst_load_file | [cst_load_file.md](commands/cst/cst_load_file.md) | Load Python file into CST tree (returns tree_id) |
| cst_save_tree | [cst_save_tree.md](commands/cst/cst_save_tree.md) | Save CST tree to file |
| cst_reload_tree | [cst_reload_tree.md](commands/cst/cst_reload_tree.md) | Reload CST tree from file |
| cst_find_node | [cst_find_node.md](commands/cst/cst_find_node.md) | Find node in tree by criteria |
| cst_get_node_info | [cst_get_node_info.md](commands/cst/cst_get_node_info.md) | Get node metadata |
| cst_get_node_by_range | [cst_get_node_by_range.md](commands/cst/cst_get_node_by_range.md) | Get node by line/column range |
| cst_modify_tree | [cst_modify_tree.md](commands/cst/cst_modify_tree.md) | Apply edits to CST tree |
| compose_cst_module | [compose_cst_module.md](commands/cst/compose_cst_module.md) | Compose module from blocks |
| cst_create_file | [cst_create_file.md](commands/cst/cst_create_file.md) | Create new file from CST |
| cst_convert_and_save | [cst_convert_and_save.md](commands/cst/cst_convert_and_save.md) | Convert and save CST to file |
| list_cst_blocks | [list_cst_blocks.md](commands/cst/list_cst_blocks.md) | List CST blocks for module |
| query_cst | [query_cst.md](commands/cst/query_cst.md) | Query CST with expression language |

### Database Integrity — `docs/commands/database_integrity/`

| Command | Doc | Purpose |
|---------|-----|--------|
| get_database_corruption_status | [get_database_corruption_status.md](commands/database_integrity/get_database_corruption_status.md) | Check DB corruption/safe mode |
| backup_database | [backup_database.md](commands/database_integrity/backup_database.md) | Create DB backup |
| repair_sqlite_database | [repair_sqlite_database.md](commands/database_integrity/repair_sqlite_database.md) | Repair SQLite DB |

### Database Restore — `docs/commands/database_restore/`

| Command | Doc | Purpose |
|---------|-----|--------|
| restore_database | [restore_database.md](commands/database_restore/restore_database.md) | Restore DB from config/backup |

### File Management — `docs/commands/file_management/`

| Command | Doc | Purpose |
|---------|-----|--------|
| cleanup_deleted_files | [cleanup_deleted_files.md](commands/file_management/cleanup_deleted_files.md) | Clean up DB records for deleted files |
| unmark_deleted_file | [unmark_deleted_file.md](commands/file_management/unmark_deleted_file.md) | Unmark file as deleted |
| collapse_versions | [collapse_versions.md](commands/file_management/collapse_versions.md) | Collapse file versions in DB |
| repair_database | [repair_database.md](commands/file_management/repair_database.md) | Repair file-related DB state |

### Log Viewer — `docs/commands/log_viewer/`

| Command | Doc | Purpose |
|---------|-----|--------|
| view_worker_logs | [view_worker_logs.md](commands/log_viewer/view_worker_logs.md) | View worker log content |
| list_worker_logs | [list_worker_logs.md](commands/log_viewer/list_worker_logs.md) | List available worker logs |

### Project Management — `docs/commands/project_management/`

| Command | Doc | Purpose |
|---------|-----|--------|
| change_project_id | [change_project_id.md](commands/project_management/change_project_id.md) | Change project ID in projectid file and DB |
| create_project | [create_project.md](commands/project_management/create_project.md) | Create/register project (watch_dir_id, project_name) |
| delete_project | [delete_project.md](commands/project_management/delete_project.md) | Delete project and optionally projectid file |
| delete_unwatched_projects | [delete_unwatched_projects.md](commands/project_management/delete_unwatched_projects.md) | Delete projects not in watch dirs |
| list_projects | [list_projects.md](commands/project_management/list_projects.md) | List projects (optionally by watch_dir_id) |

### Refactor — `docs/commands/refactor/`

| Command | Doc | Purpose |
|---------|-----|--------|
| extract_superclass | [extract_superclass.md](commands/refactor/extract_superclass.md) | Extract superclass from class |
| split_class | [split_class.md](commands/refactor/split_class.md) | Split class into multiple classes |
| split_file_to_package | [split_file_to_package.md](commands/refactor/split_file_to_package.md) | Split file into package |

### Repair Worker — `docs/commands/repair_worker/`

| Command | Doc | Purpose |
|---------|-----|--------|
| start_repair_worker | [start_repair_worker.md](commands/repair_worker/start_repair_worker.md) | Start repair worker |
| stop_repair_worker | [stop_repair_worker.md](commands/repair_worker/stop_repair_worker.md) | Stop repair worker |
| repair_worker_status | [repair_worker_status.md](commands/repair_worker/repair_worker_status.md) | Get repair worker status |

### Search — `docs/commands/search/`

| Command | Doc | Purpose |
|---------|-----|--------|
| fulltext_search | [fulltext_search.md](commands/search/fulltext_search.md) | Full-text search in code |
| list_class_methods | [list_class_methods.md](commands/search/list_class_methods.md) | List methods of a class |
| find_classes | [find_classes.md](commands/search/find_classes.md) | Find classes by name/pattern |

### Vector — `docs/commands/vector/`

| Command | Doc | Purpose |
|---------|-----|--------|
| rebuild_faiss | [rebuild_faiss.md](commands/vector/rebuild_faiss.md) | Rebuild FAISS index |
| revectorize | [revectorize.md](commands/vector/revectorize.md) | Re-vectorize project chunks |

### Worker Management — `docs/commands/worker_management/`

| Command | Doc | Purpose |
|---------|-----|--------|
| start_worker | [start_worker.md](commands/worker_management/start_worker.md) | Start file_watcher or vectorization worker |
| stop_worker | [stop_worker.md](commands/worker_management/stop_worker.md) | Stop worker by type |

### Worker Status — `docs/commands/worker_status/`

| Command | Doc | Purpose |
|---------|-----|--------|
| get_worker_status | [get_worker_status.md](commands/worker_status/get_worker_status.md) | Worker process status and logs |
| get_database_status | [get_database_status.md](commands/worker_status/get_database_status.md) | Database and indexing status |

### Analysis — `docs/commands/analysis/`

| Command | Doc | Purpose |
|---------|-----|--------|
| analyze_complexity | [analyze_complexity.md](commands/analysis/analyze_complexity.md) | Cyclomatic complexity analysis |
| find_duplicates | [find_duplicates.md](commands/analysis/find_duplicates.md) | Find duplicate/similar code |
| comprehensive_analysis | [comprehensive_analysis.md](commands/analysis/comprehensive_analysis.md) | Combined analysis (complexity, duplicates, etc.) |
| semantic_search | [semantic_search.md](commands/analysis/semantic_search.md) | Semantic search over embeddings |

### Miscellaneous — `docs/commands/misc/`

| Command | Doc | Purpose |
|---------|-----|--------|
| check_vectors | [check_vectors.md](commands/misc/check_vectors.md) | Vector/chunk statistics and status |

Optional commands (registered only if module exists): `analyze_project`, `analyze_file`, `help`, `add_watch_dir`, `remove_watch_dir`. See [COMMANDS_INDEX.md](COMMANDS_INDEX.md).

---

## Return format (all commands)

- **Success:** `{ "success": true, "data": { ... } }` — structure of `data` is command-specific (see per-command docs).
- **Error:** `{ "success": false, "code": "<ERROR_CODE>", "message": "..." }` — optional `details` object may be present.

Schema and validation: each command’s `get_schema()` in `code_analysis/commands/` defines `required` and `properties`; `additionalProperties: false` is used.

---

## Verifying docs against code

- **Arguments:** Compare with `get_schema()` in the command class (see [COMMANDS_INDEX.md](COMMANDS_INDEX.md) for file paths).
- **Return shape:** Infer from `execute()` return type (`SuccessResult`/`ErrorResult`) and constructor arguments.
- **Error codes:** Search for `ErrorResult(..., code="...")` and `return result.get("error", "...")` in the command and related helpers.

---

## Block indexes

Each block has:

- `docs/commands/<block>/COMMANDS.md` — list of commands in the block with links to per-command docs.
- `docs/commands/<block>/README.md` — short block overview (where present).

Use [COMMANDS_INDEX.md](COMMANDS_INDEX.md) for command → class → source file mapping.
