# create_project

**Command name:** `create_project`  
**Class:** `CreateProjectMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The create_project command creates or registers a new project in the system. It validates prerequisites, creates a projectid file with UUID4 identifier, and registers the project in the database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Gets or creates watch_dir_id for watched_dir:
   - Searches for existing watch_dir by normalized path
   - If found: Uses existing watch_dir_id
   - If not found: Creates new watch_dir and watch_dir_path entries
4. Validates watched_dir exists and is a directory
5. Checks if watched_dir contains projectid file (raises error if found)
6. Validates project_dir exists and is a directory
7. Checks if project_dir is already registered in database:
   - If registered: Updates watch_dir_id if needed, returns existing project info (already_existed=True)
   - If not registered: Continues to creation
8. Checks if projectid file exists in project_dir:
   - If exists and valid: Registers in database using existing ID with watch_dir_id
   - If exists but invalid: Recreates projectid file
   - If not exists: Creates new projectid file with UUID4
9. Registers project in database with watch_dir_id
10. Returns project information including watch_dir_id

Project ID File Format:
The projectid file is created in JSON format:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "description": "Human readable description"
}

Validation Rules:
- watched_dir must exist and be a directory
- watched_dir must NOT contain projectid file
- project_dir must exist and be a directory
- project_dir must NOT be already registered in database (unless projectid exists)
- description is optional (defaults to project directory name)

Return Values (MCP response):
- data.project_id: UUID4 identifier of the project (created or existing)
- message: Status message

Use cases:
- Register a new project for code analysis
- Register an existing project that has projectid file but not in database
- Create a new project from scratch
- Re-register a project after database cleanup

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | **Yes** | Server root directory (contains config.json and data/code_analysis.db). Must be an absolute path or relative to current working directory. |
| `watch_dir_id` | string | **Yes** | Watch directory ID (UUID4) from watch_dirs table. Must exist in database. Required. |
| `project_name` | string | **Yes** | Name of project subdirectory to create in watch_dir. Required. Must be a valid directory name. |
| `description` | string | **Yes** | Human-readable description of the project. Required. |
| `project_id` | string | No | Optional project ID (UUID4). If not provided, will be generated automatically. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `data.project_id`: UUID4 identifier of the project (created or existing)
- `message`: Status message (e.g. "Project created successfully")

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** WATCH_DIR_NOT_FOUND, INVALID_PROJECT_NAME, PROJECT_ALREADY_EXISTS, PROJECT_DIR_EXISTS, PROJECTID_WRITE_ERROR, DATABASE_REGISTRATION_ERROR, CREATE_PROJECT_ERROR (and others).

---

## Examples

### Correct usage

**Create new project**

Use `watch_dir_id` (UUID from watch_dirs table) and `project_name` (subdirectory name under that watch dir). Get `watch_dir_id` from the server configuration or from a previous `add_watch_dir` / list operation.

```json
{
  "root_dir": "/home/user/projects/tools/code_analysis",
  "watch_dir_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_name": "my_project",
  "description": "My new project for testing"
}
```

Creates project subdirectory `my_project` under the watch directory identified by `watch_dir_id`, creates projectid file with UUID4, and registers the project in the database.

**Create project with optional project_id**
```json
{
  "root_dir": "/home/user/projects/tools/code_analysis",
  "watch_dir_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "project_name": "existing_project",
  "description": "Existing project re-registration",
  "project_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Uses the provided `project_id` instead of generating a new one. Useful when re-registering a project with an existing projectid file content.

### Incorrect usage

- **WATCH_DIR_NOT_FOUND**: `watch_dir_id` not found in database or watch directory has no path set. Verify `watch_dir_id` exists in `watch_dirs` table and that a path is configured (e.g. via worker config or `watch_dir_paths`).

- **INVALID_PROJECT_NAME**: `project_name` is empty or whitespace. Provide a non-empty directory name.

- **PROJECT_ALREADY_EXISTS**: A project with the same path is already registered. Use `list_projects` to get existing project_id or use a different `project_name`.

- **PROJECT_DIR_EXISTS**: Project directory already exists but is not registered. Resolve manually or use a different `project_name`.

- **PROJECTID_WRITE_ERROR**: Failed to write projectid file (permission denied or disk full). Check directory permissions and disk space.

- **DATABASE_REGISTRATION_ERROR**: Database error during registration (locked, constraint violation, or connection error). Check database integrity and connections.

- **CREATE_PROJECT_ERROR**: Unexpected error during creation. Check the returned `message` for details.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `WATCH_DIR_NOT_FOUND` | Watch directory ID not in DB or path not set | Ensure `watch_dir_id` exists in `watch_dirs` and has a path |
| `INVALID_PROJECT_NAME` | Project name empty or invalid | Provide non-empty `project_name` |
| `PROJECT_ALREADY_EXISTS` | Project path already registered | Use `list_projects` or different `project_name` |
| `PROJECT_DIR_EXISTS` | Directory exists but not registered | Resolve manually or use different `project_name` |
| `PROJECTID_WRITE_ERROR` | Failed to write projectid file | Check permissions and disk space |
| `DATABASE_REGISTRATION_ERROR` | DB error on registration | Check DB integrity and connection |
| `CREATE_PROJECT_ERROR` | Unexpected creation error | Check returned `message` for details |

## Best practices

- Ensure watched_dir exists and does not contain projectid file
- Project will be automatically linked to watched_dir via watch_dir_id
- If watch_dir doesn't exist in database, it will be created automatically
- Use descriptive project descriptions for better organization
- If project already has projectid file, it will be used (not recreated)
- If project is already registered, command updates watch_dir_id if needed and returns existing info
- Always check already_existed flag to know if project was created or already existed
- watch_dir_id is returned in response and can be used for CST commands

---
