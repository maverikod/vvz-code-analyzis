# list_projects

**Command name:** `list_projects`  
**Class:** `ListProjectsMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_projects command retrieves all projects from the database and returns their complete metadata including UUID, root path, name, comment, watch directory identifier, and last update timestamp.

Operation flow:
1. Resolves database path from server configuration (config.json)
2. Opens database connection
3. If watched_dir_id is provided, filters projects by watched_dir_id
4. Queries projects from the projects table
5. Returns list of projects with their metadata

Use cases:
- Discover all projects in the database
- Get project UUIDs for use in other commands
- Filter projects by watched directory
- Verify project registration
- Audit project metadata

Important notes:
- Returns all projects if watched_dir_id is not provided
- If watched_dir_id is provided, only projects from that watched directory are returned
- Empty database or no matching projects returns empty list (count: 0)
- Each project entry includes: id (UUID), root_path, name, comment, watch_dir_id, updated_at
- Database path is automatically resolved from server configuration, no root_dir parameter needed

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `watched_dir_id` | string | No | Optional watched directory identifier (UUID4). If provided, only projects from this watched directory will be returned. If not provided, all projects from all watched directories are returned. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted. This command does **not** accept `root_dir`; database path is resolved from server configuration.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `projects`: List of project dictionaries, each containing:
- id: Project UUID (string)
- root_path: Project root directory path (string)
- name: Project name (string, may be None)
- comment: Optional comment/description (string, may be None)
- watch_dir_id: Watched directory identifier (string, UUID4, may be None)
- updated_at: Last update timestamp (ISO format string or None)
- `count`: Number of projects found (integer)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** CONFIG_NOT_FOUND, DATABASE_NOT_FOUND, DATABASE_ERROR, INVALID_WATCHED_DIR_ID (and others).

---

## Examples

### Correct usage

**List projects from specific watched directory**
```json
{
  "watched_dir_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Lists only projects that belong to the specified watched directory. Useful for filtering projects by their watch directory location.

### Incorrect usage

- **CONFIG_NOT_FOUND**: config.json missing or invalid. Ensure config.json exists and is valid JSON. The configuration file is required to resolve database path.

- **DATABASE_NOT_FOUND**: Database path from config.json points to non-existent file. Ensure the database file exists at the configured path. You may need to run update_indexes or restore_database first to create the database.

- **DATABASE_ERROR**: Database locked, corrupted, or permission denied. Check database integrity, ensure it's not locked by another process, verify file permissions, or run repair_sqlite_database if corrupted

- **INVALID_WATCHED_DIR_ID**: watched_dir_id='invalid-uuid' or watched_dir_id not in watch_dirs table. Verify the watched_dir_id is a valid UUID4 and exists in the watch_dirs table. Use list_projects without filter first to see available projects and their watch_dir_id values.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `CONFIG_NOT_FOUND` | Server configuration file (config.json) not found or cannot  | Ensure config.json exists and is valid JSON. The c |
| `DATABASE_NOT_FOUND` | Database file not found at the path resolved from configurat | Ensure the database file exists at the configured  |
| `DATABASE_ERROR` | Failed to open or query the database | Check database integrity, ensure it's not locked b |
| `INVALID_WATCHED_DIR_ID` | watched_dir_id provided but not found in database | Verify the watched_dir_id is a valid UUID4 and exi |

---
