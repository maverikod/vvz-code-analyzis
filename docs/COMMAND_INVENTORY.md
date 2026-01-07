# Command Inventory

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Overview

This document lists all custom commands available in the code-analysis-server.
Standard adapter commands (echo, health, queue_*, etc.) are excluded.

**Total custom commands**: 58

**Metadata Status:**

- ✅ Commands with detailed metadata (man-page level): 42
- ⚠️ Commands needing detailed metadata: 16

**Note:** Commands marked with ⚠️ need implementation of `metadata()` method with:

- `detailed_description` - comprehensive operation flow
- `parameters` - detailed parameter descriptions with examples
- `usage_examples` - practical usage examples
- `error_cases` - common errors and solutions
- `return_value` - return value structure
- `best_practices` - recommended usage patterns

## Commands by Category

**Legend:**

- ✅ = Has detailed metadata (man-page level documentation)
- ⚠️ = Needs detailed metadata (missing or insufficient)

### AST Commands

- ✅ `ast_statistics`
- ✅ `export_graph`
- ✅ `find_dependencies`
- ✅ `find_usages`
- ✅ `get_ast`
- ✅ `get_class_hierarchy`
- ✅ `get_code_entity_info`
- ✅ `get_imports`
- ✅ `list_code_entities`
- ✅ `list_project_files`
- ✅ `search_ast_nodes`

### Analysis Commands

- ✅ `analyze_complexity`
- ✅ `comprehensive_analysis`
- ✅ `find_duplicates`
- ✅ `list_errors_by_category`
- ✅ `list_long_files`
- ✅ `update_indexes`

### Backup Management

- ✅ `clear_all_backups`
- ✅ `delete_backup`
- ✅ `list_backup_files`
- ✅ `list_backup_versions`
- ✅ `restore_backup_file`

### Code Quality

- ✅ `format_code`
- ✅ `lint_code`
- ✅ `type_check_code`

### Database Integrity Commands

- ✅ `backup_database`
- ✅ `get_database_corruption_status`
- ✅ `repair_sqlite_database`
- ✅ `restore_database`

### File Management

- ✅ `cleanup_deleted_files`
- ✅ `collapse_versions`
- ✅ `repair_database`
- ✅ `unmark_deleted_file`

### Logging Commands

- ✅ `list_worker_logs`
- ✅ `view_worker_logs`

### Monitoring Commands

- ✅ `get_database_status`
- ✅ `get_worker_status`

### Project Management

- ✅ `change_project_id`
- ✅ `delete_project`
- ✅ `delete_unwatched_projects`
- ✅ `list_projects`

### Refactor Commands

- ✅ `compose_cst_module`
- ✅ `extract_superclass`
- ✅ `list_cst_blocks`
- ✅ `query_cst`
- ✅ `split_class`
- ✅ `split_file_to_package`

### Repair Worker Commands

- ✅ `repair_worker_status`
- ✅ `start_repair_worker`
- ✅ `stop_repair_worker`

### Search Commands

- ✅ `find_classes`
- ✅ `fulltext_search`
- ✅ `list_class_methods`
- ✅ `semantic_search`

### Vectorization Commands

- ✅ `rebuild_faiss`
- ✅ `revectorize`

### Worker Management Commands

- ✅ `start_worker`
- ✅ `stop_worker`

## Command Files by Group

### ast

- `code_analysis/commands/ast/dependencies.py`
- `code_analysis/commands/ast/entity_info.py`
- `code_analysis/commands/ast/get_ast.py`
- `code_analysis/commands/ast/graph.py`
- `code_analysis/commands/ast/hierarchy.py`
- `code_analysis/commands/ast/imports.py`
- `code_analysis/commands/ast/list_entities.py`
- `code_analysis/commands/ast/list_files.py`
- `code_analysis/commands/ast/search_nodes.py`
- `code_analysis/commands/ast/statistics.py`
- `code_analysis/commands/ast/usages.py`

### top_level

- `code_analysis/commands/analyze_complexity_mcp.py`
- `code_analysis/commands/ast_mcp_commands.py`
- `code_analysis/commands/backup_mcp_commands.py`
- `code_analysis/commands/base_mcp_command.py`
- `code_analysis/commands/code_mapper_commands.py`
- `code_analysis/commands/code_mapper_mcp_command.py`
- `code_analysis/commands/code_mapper_mcp_commands.py`
- `code_analysis/commands/code_quality_commands.py`
- `code_analysis/commands/comprehensive_analysis_mcp.py`
- `code_analysis/commands/cst_compose_module_command.py`
- `code_analysis/commands/database_integrity_mcp_commands.py`
- `code_analysis/commands/database_restore_mcp_commands.py`
- `code_analysis/commands/file_management.py`
- `code_analysis/commands/file_management_mcp_commands.py`
- `code_analysis/commands/find_duplicates_mcp.py`
- `code_analysis/commands/list_cst_blocks_command.py`
- `code_analysis/commands/log_viewer.py`
- `code_analysis/commands/log_viewer_mcp_commands.py`
- `code_analysis/commands/project_deletion.py`
- `code_analysis/commands/project_management_mcp_commands.py`
- `code_analysis/commands/query_cst_command.py`
- `code_analysis/commands/refactor.py`
- `code_analysis/commands/refactor_mcp_commands.py`
- `code_analysis/commands/repair_worker_management.py`
- `code_analysis/commands/repair_worker_mcp_commands.py`
- `code_analysis/commands/search.py`
- `code_analysis/commands/search_mcp_commands.py`
- `code_analysis/commands/semantic_search_mcp.py`
- `code_analysis/commands/worker_management_mcp_commands.py`
- `code_analysis/commands/worker_status.py`
- `code_analysis/commands/worker_status_mcp_commands.py`

### vector_commands

- `code_analysis/commands/vector_commands/rebuild_faiss.py`
- `code_analysis/commands/vector_commands/revectorize.py`
