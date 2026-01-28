# MCP Commands List

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-28

## Project Management Commands

### `create_project`
- **Version**: 1.0.0
- **Category**: project_management
- **Description**: Create or register a new project. Creates projectid file and registers project in database.
- **Required params**: `root_dir`, `project_name`, `watch_dir_id`, `description`

### `delete_project`
- **Version**: 1.0.0
- **Category**: project_management
- **Description**: Delete a project and all its data from the database. This operation cannot be undone.
- **Required params**: `project_id`

### `list_projects`
- **Version**: 1.0.0
- **Category**: project_management
- **Description**: List all projects in the database with their UUID and metadata
- **Optional params**: `watched_dir_id`

### `change_project_id`
- **Version**: 1.1.0
- **Category**: project_management
- **Description**: Change project identifier and/or description: update projectid file and database record.
- **Required params**: `root_dir`, `new_project_id`, `description` (optional)

### `delete_unwatched_projects`
- **Version**: 1.0.0
- **Category**: project_management
- **Description**: Delete projects that are not in the list of watched directories.
- **Required params**: `root_dir`

## CST (Concrete Syntax Tree) Commands

### `cst_create_file`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Create a new Python file with docstring and return tree_id. Creates file on disk and in database.
- **Required params**: `project_id`, `file_path`, `docstring`
- **Optional params**: `root_dir`

### `cst_load_file`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Load Python file into CST tree and return tree_id with node metadata
- **Required params**: `project_id`, `file_path`
- **Optional params**: `root_dir`, `node_types`, `max_depth`, `include_children`

### `cst_modify_tree`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Modify CST tree with atomic operations (replace, insert, delete)
- **Required params**: `tree_id`, `operations`
- **Optional params**: `preview`
- **Operations**: `replace`, `replace_range`, `insert`, `delete`

### `cst_save_tree`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Save CST tree to file with atomic operations and rollback on errors
- **Required params**: `tree_id`, `project_id`, `file_path`
- **Optional params**: `root_dir`, `dataset_id`, `validate`, `backup`, `commit_message`, `auto_reload`

### `cst_reload_tree`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Reload CST tree from file, updating existing tree in memory (keeps same tree_id)
- **Required params**: `tree_id`
- **Optional params**: `node_types`, `max_depth`, `include_children`

### `cst_find_node`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Find nodes in CST tree using simple or XPath-like queries
- **Required params**: `tree_id`, `query`
- **Optional params**: `search_type` (simple/xpath), `node_type`, `name`

### `cst_get_node_info`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Get detailed information about a node in CST tree (metadata, children, parent)
- **Required params**: `tree_id`, `node_id`
- **Optional params**: `include_code`, `include_children`

### `cst_get_node_by_range`
- **Version**: 1.0.0
- **Category**: cst
- **Description**: Get node ID for a specific line range in CST tree
- **Required params**: `tree_id`, `start_line`, `end_line`

### `compose_cst_module`
- **Version**: 2.0.0
- **Category**: refactor
- **Description**: Apply CST tree to file with atomic operations
- **Required params**: `project_id`, `file_path`, `tree_id`
- **Optional params**: `node_id` (if empty - overwrite file, if specified - insert after node), `commit_message`

### `list_cst_blocks`
- **Version**: 1.0.0
- **Category**: refactor
- **Description**: List replaceable CST logical blocks (functions/classes/methods) with ids and ranges
- **Required params**: `file_path`
- **Optional params**: `project_id`, `root_dir`

### `query_cst`
- **Version**: 1.0.0
- **Category**: refactor
- **Description**: Query python source using CSTQuery selectors (LibCST)
- **Required params**: `file_path`, `selector`
- **Optional params**: `project_id`, `root_dir`, `include_code`, `max_results`

## AST (Abstract Syntax Tree) Commands

### `get_ast`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Get AST for a Python file from the analysis database
- **Required params**: `root_dir`, `file_path`
- **Optional params**: `project_id`, `include_json`

### `search_ast_nodes`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Search AST nodes (by type) in project files
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `file_path`, `node_type`, `name`, `limit`

### `ast_statistics`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Collect AST statistics for project or single file
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `file_path`

### `list_project_files`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: List all files in a project with statistics (classes, functions, chunks, AST)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `limit`, `offset`

### `get_code_entity_info`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Get detailed information about a class, function, or method
- **Required params**: `root_dir`, `file_path`, `entity_type`, `name`
- **Optional params**: `project_id`

### `list_code_entities`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: List classes, functions, or methods in a file or project
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `file_path`, `entity_type`, `limit`

### `get_imports`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Get list of imports in a file or project with filtering options
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `file_path`, `module`, `name`, `limit`

### `find_dependencies`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Find where a class, function, method, or module is used in the project
- **Required params**: `root_dir`, `target_type`, `target_name`
- **Optional params**: `project_id`, `file_path`

### `get_class_hierarchy`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Get class inheritance hierarchy for a specific class or all classes
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `class_name`

### `find_usages`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Find where a method, property, class, or function is used in the project
- **Required params**: `root_dir`, `target_type`, `target_name`
- **Optional params**: `project_id`, `file_path`

### `export_graph`
- **Version**: 1.0.0
- **Category**: ast
- **Description**: Export graphs (dependencies, hierarchy, call_graph) in DOT or JSON format
- **Required params**: `root_dir`, `graph_type`
- **Optional params**: `project_id`, `format`, `file_path`

## Vectorization Commands

### `check_vectors`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: Check vector statistics and vectorization status in database
- **Required params**: `root_dir`
- **Optional params**: `project_id`

### `revectorize`
- **Version**: 1.0.0
- **Category**: vectorization
- **Description**: Revectorize chunks (regenerate embeddings and update FAISS index)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `batch_size`, `force`

### `rebuild_faiss`
- **Version**: 1.0.0
- **Category**: vectorization
- **Description**: Rebuild FAISS index from database (dataset-scoped)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `dataset_id`

### `semantic_search`
- **Version**: 1.0.0
- **Category**: search
- **Description**: Perform semantic search using embeddings and FAISS vectors
- **Required params**: `root_dir`, `query`
- **Optional params**: `project_id`, `limit`, `threshold`

## Analysis Commands

### `analyze_complexity`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: Analyze cyclomatic complexity for functions and methods in a project
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `file_path`, `limit`

### `find_duplicates`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: Find duplicate code blocks using AST normalization
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `min_similarity`, `limit`

### `comprehensive_analysis`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: Comprehensive code analysis (placeholders, stubs, duplicates, long files, missing docstrings, etc.)
- **Required params**: `root_dir`
- **Optional params**: `project_id`
- **Note**: Uses queue (long-running)

### `list_long_files`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: List files exceeding maximum line limit (code_mapper functionality)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `max_lines`

### `list_errors_by_category`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: List errors grouped by category (code_mapper functionality)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `category`

### `update_indexes`
- **Version**: 1.0.0
- **Category**: analysis
- **Description**: Update code indexes by analyzing project files and adding them to database
- **Required params**: `root_dir`
- **Optional params**: `project_id`
- **Note**: Uses queue (long-running)

## Search Commands

### `fulltext_search`
- **Version**: 1.0.0
- **Category**: search
- **Description**: Perform full-text search in code content and docstrings
- **Required params**: `root_dir`, `query`
- **Optional params**: `project_id`, `entity_type`, `limit`

### `find_classes`
- **Version**: 1.0.0
- **Category**: search
- **Description**: Find classes by name pattern
- **Required params**: `root_dir`, `name`
- **Optional params**: `project_id`, `limit`

### `list_class_methods`
- **Version**: 1.0.0
- **Category**: search
- **Description**: List methods of a specific class
- **Required params**: `root_dir`, `class_name`
- **Optional params**: `project_id`, `file_path`

## Code Quality Commands

### `format_code`
- **Version**: 1.0.0
- **Category**: code_quality
- **Description**: Format Python code using black formatter
- **Required params**: `file_path`
- **Optional params**: `root_dir`

### `lint_code`
- **Version**: 1.0.0
- **Category**: code_quality
- **Description**: Lint Python code using flake8
- **Required params**: `file_path`
- **Optional params**: `root_dir`

### `type_check_code`
- **Version**: 1.0.0
- **Category**: code_quality
- **Description**: Type check Python code using mypy
- **Required params**: `file_path`
- **Optional params**: `root_dir`

## Refactoring Commands

### `split_class`
- **Version**: 1.0.0
- **Category**: refactor
- **Description**: Split a class into multiple smaller classes
- **Required params**: `root_dir`, `file_path`, `config`
- **Optional params**: `project_id`, `dry_run`

### `extract_superclass`
- **Version**: 1.0.0
- **Category**: refactor
- **Description**: Extract superclass from existing class
- **Required params**: `root_dir`, `file_path`, `config`
- **Optional params**: `project_id`, `dry_run`

### `split_file_to_package`
- **Version**: 1.0.0
- **Category**: refactor
- **Description**: Split a large file into a package structure
- **Required params**: `root_dir`, `file_path`, `config`
- **Optional params**: `project_id`, `dry_run`

## Worker Management Commands

### `start_worker`
- **Version**: 1.0.0
- **Category**: worker_management
- **Description**: Start a background worker (file_watcher or vectorization) for a project
- **Required params**: `worker_type`, `root_dir`
- **Optional params**: `watch_dirs`, `scan_interval`, `poll_interval`

### `stop_worker`
- **Version**: 1.0.0
- **Category**: worker_management
- **Description**: Stop a background worker process
- **Required params**: `worker_type`, `root_dir`
- **Optional params**: `project_id`

### `get_worker_status`
- **Version**: 1.0.0
- **Category**: monitoring
- **Description**: Get worker process status, resource usage, and recent activity
- **Required params**: `worker_type`
- **Optional params**: `log_path`, `lock_file_path`, `root_dir`

### `get_database_status`
- **Version**: 1.0.0
- **Category**: monitoring
- **Description**: Get database status and statistics
- **Required params**: `root_dir`

### `start_repair_worker`
- **Version**: 1.0.0
- **Category**: repair_worker
- **Description**: Start repair worker process for database integrity restoration
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `version_dir`, `batch_size`, `poll_interval`

### `stop_repair_worker`
- **Version**: 1.0.0
- **Category**: repair_worker
- **Description**: Stop repair worker process
- **Required params**: `root_dir`
- **Optional params**: `project_id`

### `repair_worker_status`
- **Version**: 1.0.0
- **Category**: repair_worker
- **Description**: Get repair worker status
- **Required params**: `root_dir`
- **Optional params**: `project_id`

## Backup Commands

### `list_backup_files`
- **Version**: 1.0.0
- **Category**: backup
- **Description**: List all backed up files
- **Required params**: `root_dir`

### `list_backup_versions`
- **Version**: 1.0.0
- **Category**: backup
- **Description**: List all backup versions for a specific file
- **Required params**: `root_dir`, `file_path`

### `restore_backup_file`
- **Version**: 1.0.0
- **Category**: backup
- **Description**: Restore a file from backup
- **Required params**: `root_dir`, `file_path`, `backup_uuid`

### `delete_backup`
- **Version**: 1.0.0
- **Category**: backup
- **Description**: Delete a specific backup version
- **Required params**: `root_dir`, `file_path`, `backup_uuid`

### `clear_all_backups`
- **Version**: 1.0.0
- **Category**: backup
- **Description**: Clear all backups for a project
- **Required params**: `root_dir`

## File Management Commands

### `cleanup_deleted_files`
- **Version**: 1.0.0
- **Category**: file_management
- **Description**: Clean up deleted files from database (soft or hard delete)
- **Required params**: `root_dir`
- **Optional params**: `project_id`, `dry_run`, `older_than_days`, `hard_delete`

### `unmark_deleted_file`
- **Version**: 1.0.0
- **Category**: file_management
- **Description**: Unmark a file as deleted (restore from version directory)
- **Required params**: `root_dir`, `file_path`
- **Optional params**: `project_id`

### `collapse_versions`
- **Version**: 1.0.0
- **Category**: file_management
- **Description**: Collapse version directories (merge deleted files back)
- **Required params**: `root_dir`
- **Optional params**: `project_id`

### `repair_database`
- **Version**: 1.0.0
- **Category**: file_management
- **Description**: Repair database inconsistencies
- **Required params**: `root_dir`
- **Optional params**: `project_id`

## Log Viewer Commands

### `view_worker_logs`
- **Version**: 1.0.0
- **Category**: logging
- **Description**: View worker logs with filtering by time, event type, and search pattern
- **Required params**: `log_path`
- **Optional params**: `worker_type`, `from_time`, `to_time`, `event_types`, `log_levels`, `search_pattern`, `tail`, `limit`

### `list_worker_logs`
- **Version**: 1.0.0
- **Category**: logging
- **Description**: List available worker log files
- **Required params**: `root_dir`
- **Optional params**: `worker_type`

## Database Integrity Commands

### `get_database_corruption_status`
- **Version**: 1.0.0
- **Category**: database_integrity
- **Description**: Get corruption marker and quick_check status for project database
- **Required params**: `root_dir`

### `backup_database`
- **Version**: 1.0.0
- **Category**: database_integrity
- **Description**: Create backup of SQLite database file
- **Required params**: `root_dir`

### `repair_sqlite_database`
- **Version**: 1.0.0
- **Category**: database_integrity
- **Description**: Repair corrupted SQLite database
- **Required params**: `root_dir`

### `restore_database`
- **Version**: 1.0.0
- **Category**: database_integrity
- **Description**: Restore (rebuild) SQLite database by sequentially indexing directories from config
- **Required params**: `root_dir`
- **Note**: Uses queue (long-running)

## Summary

**Total Commands**: ~71+ MCP commands

**Categories**:
- **Project Management**: 5 commands
- **CST (Concrete Syntax Tree)**: 10 commands
- **AST (Abstract Syntax Tree)**: 11 commands
- **Vectorization**: 4 commands
- **Analysis**: 6 commands
- **Search**: 4 commands
- **Code Quality**: 3 commands
- **Refactoring**: 3 commands
- **Worker Management**: 7 commands
- **Backup**: 5 commands
- **File Management**: 4 commands
- **Log Viewer**: 2 commands
- **Database Integrity**: 4 commands
