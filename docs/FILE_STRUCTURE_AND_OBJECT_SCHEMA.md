# File Structure and Object Schema

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes the project file layout and the main object/schema concepts used by the code-analysis server. Use `code_analysis/method_index.yaml` and `code_analysis/code_map.yaml` for quick lookup of classes and methods.

---

## 1. Top-Level Layout

```
code_analysis/           # Project root
├── code_analysis/       # Main package
│   ├── cli/             # CLI entry points (config, server manager, etc.)
│   ├── commands/       # MCP command implementations (see §2)
│   ├── core/            # Core logic, DB, workers, CST/AST (see §3)
│   ├── cst_query/       # CST query language and execution
│   ├── hooks.py         # Command registration for MCP
│   └── main.py          # Server entry point
├── config.json          # Server configuration (example)
├── docs/                # All documentation
│   ├── commands/        # Per-block command docs (see docs/README)
│   ├── FILE_STRUCTURE_AND_OBJECT_SCHEMA.md  # This file
│   ├── COMPONENT_INTERACTION.md
│   └── ...
├── scripts/             # Non-pytest scripts and utilities
├── tests/               # Pytest tests
├── code_analysis/       # Generated indices (do not edit by hand)
│   ├── method_index.yaml
│   ├── code_map.yaml
│   └── ...
├── requirements.txt
└── MANIFEST.in
```

---

## 2. Commands Package (`code_analysis/commands/`)

Commands are grouped by **block**; each block is documented under `docs/commands/<block>/`.

| Block | Location | Description |
|-------|----------|-------------|
| **ast** | `commands/ast/` | AST: get_ast, search_ast_nodes, statistics, list_project_files, entity_info, list_entities, get_imports, find_dependencies, get_class_hierarchy, find_usages, export_graph |
| **backup** | `backup_mcp_commands.py` | list_backup_files, list_backup_versions, restore_backup_file, delete_backup, clear_all_backups |
| **code_mapper** | `code_mapper_mcp_command.py`, `code_mapper_mcp_commands.py` | update_indexes, list_long_files, list_errors_by_category |
| **code_quality** | `code_quality_commands.py` | format_code, lint_code, type_check_code |
| **cst** | `cst_*.py`, `list_cst_blocks_command.py`, `query_cst_command.py` | CST load/save/reload, find_node, get_node_info, get_node_by_range, modify_tree, compose_cst_module, cst_create_file, cst_convert_and_save, list_cst_blocks, query_cst |
| **database_integrity** | `database_integrity_mcp_commands.py` | get_database_corruption_status, backup_database, repair_sqlite_database |
| **database_restore** | `database_restore_mcp_commands.py` | restore_database |
| **file_management** | `file_management_mcp_commands.py` | cleanup_deleted_files, unmark_deleted_file, collapse_versions, repair_database |
| **log_viewer** | `log_viewer_mcp_commands.py` | view_worker_logs, list_worker_logs |
| **project_management** | `project_management_mcp_commands.py` | change_project_id, create_project, delete_project, delete_unwatched_projects, list_projects |
| **refactor** | `refactor_mcp_commands.py` | extract_superclass, split_class, split_file_to_package |
| **repair_worker** | `repair_worker_mcp_commands.py` | start_repair_worker, stop_repair_worker, repair_worker_status |
| **search** | `search_mcp_commands.py` | fulltext_search, list_class_methods, find_classes |
| **vector** | `vector_commands/` | rebuild_faiss, revectorize |
| **worker_management** | `worker_management_mcp_commands.py` | start_worker, stop_worker |
| **worker_status** | `worker_status_mcp_commands.py` | get_worker_status, get_database_status |
| **analysis** | `analyze_complexity_mcp.py`, `find_duplicates_mcp.py`, `comprehensive_analysis_mcp.py`, `semantic_search_mcp.py` | analyze_complexity, find_duplicates, comprehensive_analysis, semantic_search |
| **misc** | various | analyze_project, analyze_file, help, check_vectors, watch_dirs |

- **Base**: Most MCP commands inherit from `BaseMCPCommand` (`commands/base_mcp_command.py`), which provides DB access, project ID resolution, and error handling.
- **Registration**: All commands are registered in `code_analysis/hooks.py` via `register_code_analysis_commands(reg)`.

---

## 3. Core Package (`code_analysis/core/`)

| Area | Path | Main concepts |
|------|------|----------------|
| **Database** | `database/` | `CodeDatabase`; modules: base, projects, files, ast, cst, entities, chunks, comprehensive_analysis, watch_dirs, worker_stats |
| **Database client** | `database_client/` | RPC client to DB driver; `objects/`: Project, File, Dataset, AST/CST nodes, Method, Import, Issue, Usage, TreeAction, XPathFilter, vector chunks |
| **Database driver** | `database_driver_pkg/` | RPC server (runner), handlers (schema, AST/CST query/modify, base CRUD), SQLite driver, request/result protocol |
| **DB integrity** | `db_integrity.py` | Physical integrity check and repair for SQLite |
| **CST** | `cst_tree/`, `cst_module/` | Tree build/save/load, finder, modifier, range finder; patcher, validation, blocks |
| **Code quality** | `code_quality/` | Formatter (Black), linter (Flake8), type checker (mypy) |
| **Refactoring** | `refactorer_pkg/` | Base refactorer, extractor (superclass), splitter (class), file_splitter (file-to-package), validators |
| **Workers** | `file_watcher_pkg/`, `vectorization_worker_pkg/`, `db_worker_pkg/` | File watcher, vectorization worker, DB driver process |
| **Workers (lifecycle)** | `worker_manager.py`, `worker_lifecycle.py`, `worker_monitor.py`, `worker_registry.py` | Start/stop workers, monitoring, registry |
| **Repair worker** | `repair_worker_management` (or similar) | Repair worker process control |
| **Backup** | `backup_manager.py` | File backup/restore, version list |
| **Vector** | `faiss_manager.py`, `vectorization_helper.py`, `svo_client_manager.py` | FAISS index, vectorization, SVO circuit state |
| **Analysis** | `complexity_analyzer.py`, `duplicate_detector.py`, `comprehensive_analyzer.py`, `usage_tracker.py` | Complexity, duplicates, comprehensive checks, usages |
| **Config** | `config.py`, `config_validator.py`, `config_generator.py`, `settings_manager.py`, `storage_paths.py` | Server/config paths and validation |
| **Other** | `exceptions.py`, `constants.py`, `path_normalization.py`, `project_manager.py`, `project_resolution.py`, `project_discovery.py`, `git_integration.py`, `progress_tracker.py` | Shared utilities and project resolution |

---

## 4. Object Schema (High Level)

- **Project**: root path, project_id (UUID), watch_dir; stored via `database/projects.py` and client `objects/project.py`.
- **File**: files belong to a project; path, content, metadata; DB module `files`.
- **AST**: nodes and trees stored/retrieved via `database/ast.py`; client objects in `database_client/objects/ast_cst.py`.
- **CST**: trees and nodes; `database/cst.py`, `core/cst_tree/`, `core/cst_module/`; client tree actions in `objects/tree_action.py`.
- **Entities**: classes, functions, methods; `database/entities.py`, client `objects/class_function.py`, `objects/method_import.py`.
- **Chunks / vectors**: code chunks and embeddings; `database/chunks.py`, client `objects/vector_chunk.py`; FAISS index in `faiss_manager.py`.
- **Issues / analysis**: comprehensive analysis results; `database/comprehensive_analysis.py`, client `objects/analysis.py`.
- **Request/Result**: MCP commands use schemas from `get_schema()` and return results; base types in client `result.py` and driver `request.py`/`result.py`.

For exact class names, methods, and file locations, use **`code_analysis/method_index.yaml`** (class → methods) and **`code_analysis/code_map.yaml`** (class → file, docstring, bases, methods).

---

## 5. Indices (Quick Search)

- **method_index.yaml**: Lists each class and its methods (one block per class).
- **code_map.yaml**: For each class: file path, line, docstring, bases, methods. Use for “command → file” and “class → description” lookup.

Both are generated by the code_mapper/update_indexes pipeline; do not edit manually.
