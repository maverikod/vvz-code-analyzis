# File Management Commands

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/file_management_mcp_commands.py`. Internal logic in `commands/file_management.py`.

## cleanup_deleted_files

Remove records of deleted files from the database. Optionally by project, dry_run, or older_than_days.

## unmark_deleted_file

Unmark a file previously marked as deleted; restore its record to active.

## collapse_versions

Collapse or prune old file versions in the database to save space.

## repair_database

Run logical repair on project database (e.g. fix references). Distinct from repair_sqlite_database (physical repair).
