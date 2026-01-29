# delete_unwatched_projects

**Command name:** `delete_unwatched_projects`  
**Class:** `DeleteUnwatchedProjectsMCPCommand`  
**Source:** `code_analysis/commands/project_management_mcp_commands.py`  
**Category:** project_management

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The delete_unwatched_projects command deletes projects that are not in the list of watched directories. It discovers all projects in watched directories and compares them with database projects to find unwatched ones, then deletes those projects.

Operation flow:
1. Validates root_dir exists and is a directory
2. Gets watched directories from config.json (code_analysis.worker.watch_dirs) or from parameter
3. Also checks dynamic_watch_file if configured
4. Discovers all projects in watched directories using project discovery
5. Gets all projects from database
6. Compares database projects with discovered projects:
   - Projects in discovered list: Kept
   - Projects not in discovered list: Marked for deletion
   - Server root directory: Always protected from deletion
7. If dry_run=True:
   - Lists projects that would be deleted
   - Lists projects that would be kept
   - Does not perform actual deletion
8. If dry_run=False:
   - Deletes unwatched projects using clear_project_data
   - Removes all project data (files, chunks, datasets, etc.)
9. Returns deletion summary

Project Discovery:
- Scans watched directories for projects (looks for projectid files)
- Uses project discovery to find all projects
- Handles nested project errors and duplicate project_id errors
- Collects discovery errors for reporting

Protection:
- Server root directory is always protected from deletion
- Projects in watched directories are kept
- Only unwatched projects are deleted

Use cases:
- Clean up projects that are no longer in watched directories
- Remove orphaned projects from database
- Maintain database cleanliness
- Free up database space

Important notes:
- This operation is PERMANENT and cannot be undone
- Always use dry_run=True first to preview what will be deleted
- Watched directories are read from config.json if not provided
- Server root directory is automatically protected
- Discovery errors are reported but don't stop the process
- Use with extreme caution

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | **Yes** | Server root directory (contains config.json and data/code_analysis.db). Must be an absolute path or relative to current working directory. |
| `watched_dirs` | array | No | Optional list of watched directory paths. If not provided, will be read from config.json (code_analysis.worker.watch_dirs). |
| `dry_run` | boolean | No | If True, only show what would be deleted without actually deleting. Default: False. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Whether operation was successful (True if no errors)
- `dry_run`: Whether this was a dry run
- `deleted_count`: Number of projects deleted (or would be deleted)
- `kept_count`: Number of projects kept
- `projects_deleted`: List of projects that were deleted. Each contains:
- project_id: Project UUID
- root_path: Project root path
- name: Project name
- reason: Reason for deletion (not_discovered_in_watch_dirs, invalid_path)
- `projects_kept`: List of projects that were kept. Each contains:
- project_id: Project UUID
- root_path: Project root path
- name: Project name
- reason: Reason for keeping (discovered_in_watch_dirs, server_root_protected)
- `discovery_errors`: List of errors during project discovery (if any)
- `errors`: List of errors during deletion (if any)
- `message`: Status message

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** NO_WATCHED_DIRS, DELETE_UNWATCHED_PROJECTS_ERROR (and others).

---

## Examples

### Correct usage

**Preview deletion (dry run)**
```json
{
  "root_dir": "/home/user/projects/code_analysis",
  "dry_run": true
}
```

Shows which projects would be deleted and which would be kept. Safe to run to preview deletion.

**Delete unwatched projects using config**
```json
{
  "root_dir": "/home/user/projects/code_analysis"
}
```

Deletes projects not in watched directories from config.json. WARNING: This is permanent and cannot be undone.

**Delete unwatched projects with explicit watched_dirs**
```json
{
  "root_dir": "/home/user/projects/code_analysis",
  "watched_dirs": [
    "/home/user/projects",
    "/var/lib/projects"
  ]
}
```

Deletes projects not in the specified watched directories. Overrides config.json watched_dirs.

### Incorrect usage

- **NO_WATCHED_DIRS**: watched_dirs not provided and not in config.json. Provide watched_dirs parameter or configure code_analysis.worker.watch_dirs in config.json.

- **DELETE_UNWATCHED_PROJECTS_ERROR**: Database error, project discovery error, or deletion failure. Check database integrity, verify watched directories exist, ensure project discovery works. Use dry_run=True first.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `NO_WATCHED_DIRS` | No watched directories found | Provide watched_dirs parameter or configure code_a |
| `DELETE_UNWATCHED_PROJECTS_ERROR` | General error during deletion | Check database integrity, verify watched directori |

## Best practices

- ALWAYS use dry_run=True first to preview what will be deleted
- Verify watched_dirs are correct before deletion
- Backup database before deleting projects
- This operation is permanent - double-check before proceeding
- Server root directory is automatically protected
- Review projects_kept and projects_deleted lists carefully
- Check discovery_errors to identify project discovery issues

---
