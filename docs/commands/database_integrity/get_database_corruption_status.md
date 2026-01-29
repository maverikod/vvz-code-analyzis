# get_database_corruption_status

**Command name:** `get_database_corruption_status`  
**Class:** `GetDatabaseCorruptionStatusMCPCommand`  
**Source:** `code_analysis/commands/database_integrity_mcp_commands.py`  
**Category:** database_integrity

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The get_database_corruption_status command checks the corruption status of a project's SQLite database. It reports both the persistent corruption marker status and the current physical integrity check result.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves database path: root_dir/data/code_analysis.db
3. Reads persistent corruption marker (if present)
4. Runs SQLite integrity check (PRAGMA quick_check)
5. Returns combined status information

Corruption Marker:
- Persistent marker file stored next to database
- Created when corruption is detected
- Prevents DB-dependent commands from running
- Contains backup paths and error message
- Must be cleared explicitly after repair

Integrity Check:
- Uses SQLite PRAGMA quick_check(1) for fast check
- Falls back to PRAGMA integrity_check if needed
- Detects physical corruption (malformed database)
- Ignores transient errors (database locked, busy)
- Returns OK if database file doesn't exist (not corrupted)

Safe Mode Policy:
- If marker present, DB-dependent commands are blocked
- Only backup/restore/repair commands allowed
- Prevents further corruption from operations
- Ensures data safety during recovery

Use cases:
- Check database health before operations
- Diagnose corruption issues
- Verify marker status after repair
- Monitor database integrity
- Troubleshoot database errors

Important notes:
- Marker presence blocks DB-dependent commands
- Integrity check is read-only (doesn't modify DB)
- Transient lock errors are not treated as corruption
- Marker must be cleared after successful repair
- Both marker and integrity status are reported

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_dir` | string | **Yes** | Project root directory (contains data/code_analysis.db). |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `root_dir`: Project root directory path
- `db_path`: Path to database file
- `marker_path`: Path to corruption marker file
- `marker_present`: True if corruption marker exists
- `marker`: Marker data if present (None otherwise). Contains:
- message: Error message
- backup_paths: List of backup file paths
- timestamp: When marker was created
- `integrity_ok`: True if database integrity check passed
- `integrity_message`: Message from integrity check

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** DB_CORRUPTION_STATUS_ERROR (and others).

---

## Examples

### Correct usage

**Check database corruption status**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Checks both corruption marker and integrity status for the project database.

**Verify database health before operations**
```json
{
  "root_dir": "."
}
```

Checks database status in current directory before running DB operations.

### Incorrect usage

- **DB_CORRUPTION_STATUS_ERROR**: Invalid root_dir, permission errors, or unexpected exceptions. Verify root_dir exists and is accessible, check file permissions, review logs for details

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `DB_CORRUPTION_STATUS_ERROR` | Error during status check | Verify root_dir exists and is accessible, check fi |

## Best practices

- Check status before running DB-dependent operations
- If marker_present=True, run repair_sqlite_database to fix
- If integrity_ok=False, database needs repair
- Use backup_database before repair operations
- Clear marker after successful repair (done automatically by repair command)
- Monitor integrity_ok status regularly

---
