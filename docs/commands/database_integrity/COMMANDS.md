# Database Integrity Commands

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/database_integrity_mcp_commands.py`. Schema from `get_schema()`; metadata from `metadata()`.

## get_database_corruption_status

Get persistent database corruption status for a project. Returns whether the project SQLite DB has been marked as corrupted and optional details.

## backup_database

Create a filesystem backup of the project SQLite database file. Copies the DB file to a backup location with timestamp; returns backup path or id.

## repair_sqlite_database

Repair corrupted SQLite database by recreating it from scratch. Destructive: after recreation, re-run `update_indexes` for the project. Backs up current file, creates new empty DB, applies schema.
