# Code Mapper Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**update_indexes:** `commands/code_mapper_mcp_command.py`. **list_long_files**, **list_errors_by_category:** `commands/code_mapper_mcp_commands.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## update_indexes — UpdateIndexesMCPCommand

**Description:** Update code indexes by analyzing project files and adding them to the database. Builds/updates file list, AST, entities, and optionally chunks/vectors.

**Behavior:** Accepts root_dir (and optional project_id); scans project files, parses AST, extracts entities and docstrings; updates DB and can run in background queue (use_queue). Used by file watcher after changes.

---

## list_long_files — ListLongFilesMCPCommand

**Description:** MCP command to list files exceeding line limit. Equivalent to old code_mapper functionality for finding oversized files.

**Behavior:** Returns list of files whose line count exceeds configured max (e.g. 400 lines).

---

## list_errors_by_category — ListErrorsByCategoryMCPCommand

**Description:** MCP command to list errors grouped by category. Equivalent to old code_mapper functionality for listing code issues.

**Behavior:** Returns issues (e.g. missing docstrings, long files, lint) grouped by category.
