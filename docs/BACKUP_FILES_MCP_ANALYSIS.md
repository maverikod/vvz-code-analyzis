# Analysis of File Backup Operations via MCP

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Overview

This document provides a comprehensive analysis of all MCP commands available for managing file backups in the code-analysis-server. The backup system stores copies of files before modifications, allowing restoration and version tracking.

## Backup System Architecture

### Storage Location

- **Backup Directory**: `{root_dir}/old_code/`
- **Index File**: `{root_dir}/old_code/index.txt`
- **Backup Files**: Stored in `old_code/` with format: `path_with_underscores-UUID`

### Index Format

The index file (`old_code/index.txt`) uses pipe-delimited format:
```
UUID|File Path|Timestamp|Command|Related Files|Comment
```

**Fields**:
- **UUID**: Unique identifier for backup (UUID4)
- **File Path**: Original file path (relative to root_dir)
- **Timestamp**: Backup creation time (YYYY-MM-DDTHH-MM-SS)
- **Command**: Command that created backup (e.g., `compose_cst_module`, `split_file_to_package`)
- **Related Files**: Comma-separated list of related files (e.g., from split operations)
- **Comment**: Optional comment/message

### Backup File Naming

Format: `path_with_underscores-UUID4`

**Example**:
- Original: `code_analysis/core/backup_manager.py`
- Backup: `code_analysis_core_backup_manager.py-123e4567-e89b-12d3-a456-426614174000`

## Available MCP Commands

### 1. `list_backup_files`

**Purpose**: List all unique files that have been backed up

**MCP Command**: `list_backup_files`

**Parameters**:
- `root_dir` (required): Project root directory

**Returns**:
```json
{
  "success": true,
  "data": {
    "files": [
      {
        "file_path": "code_analysis/core/backup_manager.py",
        "command": "compose_cst_module",
        "related_files": []
      }
    ],
    "count": 1
  }
}
```

**Use Cases**:
- Discover all files that have been backed up
- Check which files were modified by specific commands
- Find files that were part of refactoring operations
- Audit backup history

**Key Features**:
- Returns unique file paths (one entry per file, not per backup)
- Each file entry includes metadata from its latest backup
- `command` field shows which command created the latest backup
- `related_files` field shows files created/modified together

**Example Usage**:
```python
# List all backed up files
result = call_server(
    server_id="code-analysis-server",
    command="list_backup_files",
    params={"root_dir": "/home/user/projects/my_project"}
)
```

### 2. `list_backup_versions`

**Purpose**: List all backup versions for a specific file

**MCP Command**: `list_backup_versions`

**Parameters**:
- `root_dir` (required): Project root directory
- `file_path` (required): Original file path (relative to root_dir)

**Returns**:
```json
{
  "success": true,
  "data": {
    "file_path": "code_analysis/core/backup_manager.py",
    "versions": [
      {
        "uuid": "123e4567-e89b-12d3-a456-426614174000",
        "timestamp": "2024-01-15T14-30-25",
        "size_bytes": 15234,
        "size_lines": 389,
        "command": "compose_cst_module",
        "comment": "Updated restore_file method",
        "related_files": []
      }
    ],
    "count": 1
  }
}
```

**Use Cases**:
- View backup history for a specific file
- Compare file sizes across versions
- Find specific backup UUID for restoration
- Understand what operations created each backup
- Track file evolution over time

**Key Features**:
- Versions sorted by timestamp (newest first)
- Includes file size in bytes and lines
- Shows command that created each backup
- Includes optional comment and related files
- Only returns backups with existing files

**Example Usage**:
```python
# List all versions of a file
result = call_server(
    server_id="code-analysis-server",
    command="list_backup_versions",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "code_analysis/core/backup_manager.py"
    }
)
```

### 3. `restore_backup_file`

**Purpose**: Restore a file from backup

**MCP Command**: `restore_backup_file`

**Parameters**:
- `root_dir` (required): Project root directory
- `file_path` (required): Original file path (relative to root_dir)
- `backup_uuid` (optional): UUID of specific backup to restore (uses latest if omitted)

**Returns**:
```json
{
  "success": true,
  "data": {
    "message": "File restored from backup 123e4567-e89b-12d3-a456-426614174000",
    "file_path": "code_analysis/core/backup_manager.py"
  }
}
```

**Use Cases**:
- Undo changes and restore previous version
- Recover from accidental modifications
- Restore specific version from history
- Revert refactoring operations
- Test different file versions

**Key Features**:
- If `backup_uuid` specified, restores that exact version
- If `backup_uuid` omitted, restores latest version (newest timestamp)
- Original file is overwritten (no backup of current file is created)
- Parent directories are created automatically if missing
- File permissions and metadata are preserved from backup

**Important Notes**:
- Original file is overwritten without creating a new backup
- If you want to preserve current file, create backup first
- File path must be relative to root_dir
- Backup file must exist in old_code/ directory

**Example Usage**:
```python
# Restore latest version
result = call_server(
    server_id="code-analysis-server",
    command="restore_backup_file",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "code_analysis/core/backup_manager.py"
    }
)

# Restore specific version
result = call_server(
    server_id="code-analysis-server",
    command="restore_backup_file",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "code_analysis/core/backup_manager.py",
        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
    }
)
```

### 4. `delete_backup`

**Purpose**: Delete a specific backup from history

**MCP Command**: `delete_backup`

**Parameters**:
- `root_dir` (required): Project root directory
- `backup_uuid` (required): UUID of backup to delete

**Returns**:
```json
{
  "success": true,
  "data": {
    "message": "Backup 123e4567-e89b-12d3-a456-426614174000 deleted",
    "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
  }
}
```

**Use Cases**:
- Remove old backup versions to save disk space
- Clean up specific backup after successful restoration
- Remove corrupted or invalid backups
- Manage backup storage by deleting unnecessary versions

**Key Features**:
- Backup file is permanently deleted from filesystem
- Backup entry is removed from index
- Operation cannot be undone
- If backup file is missing but index entry exists, index is still cleaned
- Other backups for the same file are not affected

**Important Notes**:
- Deletion is permanent and cannot be undone
- Only the specified backup is deleted, other versions remain
- If backup file is already missing, only index entry is removed
- Use `list_backup_versions` to find backup UUIDs

**Example Usage**:
```python
# Delete a specific backup
result = call_server(
    server_id="code-analysis-server",
    command="delete_backup",
    params={
        "root_dir": "/home/user/projects/my_project",
        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
    }
)
```

### 5. `clear_all_backups`

**Purpose**: Clear all backups and backup history

**MCP Command**: `clear_all_backups`

**Parameters**:
- `root_dir` (required): Project root directory

**Returns**:
```json
{
  "success": true,
  "data": {
    "message": "All backups cleared"
  }
}
```

**Use Cases**:
- Clean up project by removing all backup history
- Free up disk space by deleting all backups
- Reset backup system for a fresh start
- Remove backups before archiving or sharing project
- Clean up after successful project completion

**Key Features**:
- ALL backup files are permanently deleted
- Backup index is cleared (all entries removed)
- `old_code/` directory structure is preserved (directory not deleted)
- `index.txt` file is reset to empty state
- Operation cannot be undone
- No backups remain after this operation

**⚠️ WARNING**: This operation is DESTRUCTIVE and PERMANENT

**Important Notes**:
- This operation is DESTRUCTIVE and PERMANENT
- ALL backups are deleted - no way to restore files after this
- Use with extreme caution - ensure backups are not needed
- Consider backing up `old_code/` directory before clearing if needed
- After clearing, no files can be restored from backup history
- `old_code/` directory is not deleted, only its contents

**Example Usage**:
```python
# Clear all backups (⚠️ DESTRUCTIVE)
result = call_server(
    server_id="code-analysis-server",
    command="clear_all_backups",
    params={
        "root_dir": "/home/user/projects/my_project"
    }
)
```

## Workflow Examples

### Example 1: Discover and Restore File

```python
# Step 1: List all backed up files
files_result = call_server(
    server_id="code-analysis-server",
    command="list_backup_files",
    params={"root_dir": "/home/user/projects/my_project"}
)

# Step 2: List versions for a specific file
versions_result = call_server(
    server_id="code-analysis-server",
    command="list_backup_versions",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "code_analysis/core/backup_manager.py"
    }
)

# Step 3: Restore specific version
restore_result = call_server(
    server_id="code-analysis-server",
    command="restore_backup_file",
    params={
        "root_dir": "/home/user/projects/my_project",
        "file_path": "code_analysis/core/backup_manager.py",
        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000"
    }
)
```

### Example 2: Clean Up Old Backups

```python
# Step 1: List all files with backups
files_result = call_server(
    server_id="code-analysis-server",
    command="list_backup_files",
    params={"root_dir": "/home/user/projects/my_project"}
)

# Step 2: For each file, list versions
for file_info in files_result["data"]["files"]:
    versions_result = call_server(
        server_id="code-analysis-server",
        command="list_backup_versions",
        params={
            "root_dir": "/home/user/projects/my_project",
            "file_path": file_info["file_path"]
        }
    )
    
    # Step 3: Delete old versions (keep only latest)
    versions = versions_result["data"]["versions"]
    for version in versions[1:]:  # Skip first (latest)
        delete_result = call_server(
            server_id="code-analysis-server",
            command="delete_backup",
            params={
                "root_dir": "/home/user/projects/my_project",
                "backup_uuid": version["uuid"]
            }
        )
```

### Example 3: Restore After Failed Refactoring

```python
# Step 1: List files affected by refactoring
files_result = call_server(
    server_id="code-analysis-server",
    command="list_backup_files",
    params={"root_dir": "/home/user/projects/my_project"}
)

# Step 2: Find files with related_files (from split operations)
for file_info in files_result["data"]["files"]:
    if file_info.get("related_files"):
        # This file was part of a refactoring operation
        # Restore it to undo the operation
        restore_result = call_server(
            server_id="code-analysis-server",
            command="restore_backup_file",
            params={
                "root_dir": "/home/user/projects/my_project",
                "file_path": file_info["file_path"]
            }
        )
```

## Integration with Other Commands

### Automatic Backup Creation

Backups are automatically created by:

1. **`compose_cst_module`**: Creates backup before modifying file
2. **`split_file_to_package`**: Creates backup before splitting file
3. **Other refactoring commands**: Create backups before destructive operations

### Backup Metadata

Each backup includes:
- **Command**: Which command created the backup
- **Related Files**: Files created/modified together (e.g., from split operations)
- **Comment**: Optional message from backup creation

This metadata helps understand:
- What operation created each backup
- Which files were modified together
- Context for restoration decisions

## Error Handling

### Common Errors

1. **No backups found**
   - **Error**: `"No backups found for {file_path}"`
   - **Solution**: Verify file_path is correct, use `list_backup_files` to see available files

2. **Backup UUID not found**
   - **Error**: `"Backup {backup_uuid} not found"`
   - **Solution**: Verify backup_uuid is correct, use `list_backup_versions` to see available UUIDs

3. **Backup file missing**
   - **Error**: `"Backup file not found: {backup_path}"`
   - **Solution**: Backup file was deleted or moved, check `old_code/` directory

4. **Permission error**
   - **Error**: `"Permission denied"`
   - **Solution**: Check file and directory permissions

## Best Practices

### 1. Regular Backup Management

- Review backups periodically using `list_backup_files`
- Delete old backups to save disk space
- Keep at least one backup version for important files

### 2. Before Restoration

- Use `list_backup_versions` to see available versions
- Compare file sizes to understand changes
- Check `command` field to understand what operation created backup
- Consider creating backup of current file before restoring

### 3. Cleanup Strategy

- Delete old backup versions after successful restoration
- Use `delete_backup` for selective cleanup
- Use `clear_all_backups` only when absolutely certain backups are not needed
- Consider disk space implications before deleting backups

### 4. Version Control

- Use specific `backup_uuid` for precise version control
- Track backup UUIDs for important restorations
- Document which backups correspond to which changes

## Limitations

1. **No Automatic Cleanup**: Backups are not automatically deleted (manual cleanup required)
2. **No Backup Compression**: Backup files are stored as-is (no compression)
3. **No Remote Storage**: Backups are stored locally in `old_code/` directory
4. **No Backup Encryption**: Backup files are stored in plain text
5. **No Backup Expiration**: Backups do not expire automatically
6. **Single Project Scope**: Backups are per-project (not cross-project)

## Future Enhancements

### Potential Improvements

1. **Automatic Cleanup**: Auto-delete backups older than N days
2. **Backup Compression**: Compress backup files to save space
3. **Remote Storage**: Support for remote backup storage (S3, etc.)
4. **Backup Encryption**: Encrypt sensitive backup files
5. **Backup Expiration**: Configurable backup expiration policies
6. **Backup Search**: Search backups by content, command, or date
7. **Backup Comparison**: Compare backup versions side-by-side
8. **Backup Statistics**: Show backup storage usage and statistics

## Conclusion

The file backup system provides comprehensive version control and restoration capabilities through MCP commands. Key features include:

- **Version Tracking**: Multiple backup versions per file
- **Metadata**: Rich metadata (command, related files, comments)
- **Flexible Restoration**: Restore latest or specific version
- **Selective Cleanup**: Delete individual backups or clear all
- **Integration**: Automatic backup creation by refactoring commands

The system is well-designed for managing file backups in development workflows, providing safety nets for code modifications and refactoring operations.

