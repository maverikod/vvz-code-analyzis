# Backup Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All commands in `commands/backup_mcp_commands.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## list_backup_files — ListBackupFilesMCPCommand

**Description:** List all backed up files.

**Behavior:** Returns list of files that have backups (project-scoped if project_id/root_dir given).

---

## list_backup_versions — ListBackupVersionsMCPCommand

**Description:** List all versions of a backed up file.

**Behavior:** Accepts file path (or file_id); returns list of backup versions (timestamp, version id) for that file.

---

## restore_backup_file — RestoreBackupFileMCPCommand

**Description:** Restore file from backup.

**Behavior:** Accepts file path and version id (or “latest”); restores file content from backup to target path; may update DB.

---

## delete_backup — DeleteBackupMCPCommand

**Description:** Delete backup from history.

**Behavior:** Accepts backup id or file + version; removes that backup from storage and index.

---

## clear_all_backups — ClearAllBackupsMCPCommand

**Description:** Clear all backups and history.

**Behavior:** Removes all backups for the given project (or global); use with caution.
