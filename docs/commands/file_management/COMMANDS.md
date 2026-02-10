# File Management Commands — Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Each command is described in a separate file: purpose, arguments, return format, and examples.

| Command | Description | Doc |
|---------|-------------|-----|
| cleanup_deleted_files | Remove deleted file records from DB | [cleanup_deleted_files.md](cleanup_deleted_files.md) |
| list_deleted_files | List deleted files (path in trash, original_path) | [FILE_TRASH.md](FILE_TRASH.md) |
| unmark_deleted_file | Restore one file from trash | [unmark_deleted_file.md](unmark_deleted_file.md) |
| restore_deleted_files | Restore many files (batch; pre-check: no target exists) | [FILE_TRASH.md](FILE_TRASH.md) |
| collapse_versions | Collapse/prune old file versions | [collapse_versions.md](collapse_versions.md) |
| repair_database | Logical repair of project DB | [repair_database.md](repair_database.md) |

See [README.md](README.md) for block overview.
