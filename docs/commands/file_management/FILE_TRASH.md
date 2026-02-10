# File-level trash: layout and behaviour

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes how file-level trash works: where trashed files are stored, how to mark/restore/permanently delete, and pre-checks (FILE_TRASH_SPEC).

## Layout

- **Trash root:** `trash_dir` from config (e.g. `data/trash`). Same root is used for:
  - **Project trash:** whole project folder → `trash_dir/ProjectName_timestamp`
  - **File trash:** per-project deleted files → `trash_dir/{project_id}/...`
- **Path helper:** `get_file_trash_dir(trash_dir, project_id)` returns `trash_dir / project_id`.
- **DB fields:** For a deleted file, `files.path` is the path in trash; `files.original_path` is the path in the project; `files.version_dir` stores the logical parent (trash_dir/project_id or legacy version_dir/project_id).

## Mark file for deletion

- **Effect:** File is **moved** from the project folder to `trash_dir/{project_id}/...` (or `version_dir/{project_id}/...` if `trash_dir` is not used). Then DB is updated: `deleted=1`, `original_path`, `path` = path in trash.
- **Replace if already in trash:** If a file with the same `project_id` and `original_path` is already in trash, the old file is removed and the current file is moved to the target (overwrite).

## Restore (clear deletion flag)

- **Single file:** `unmark_deleted_file` (MCP) / `UnmarkDeletedFileCommand`. Moves file from trash back to `original_path` and sets `deleted=0`.
- **Batch restore:** `restore_deleted_files` (MCP) / `RestoreDeletedFilesCommand`. Restores multiple files; **pre-check:** if **any** target path already exists in the project folder, the **whole** operation is cancelled and an error is returned with the list of conflicting paths. No partial restore.
- **Pre-check (Req. 2, 6):** Before restoring, the system checks that the target path (`original_path`) does **not** exist on disk. If it exists, restore is refused with error code `FILE_EXISTS_AT_TARGET` (single) or `TARGET_FILE_EXISTS` (batch) and a message that the user must delete or rename the existing file.

## Permanent delete from trash

- **Effect:** Removes the file record and all dependent data (chunks, FAISS, classes, methods, AST, etc.) and deletes the physical file at `files.path` (trash location). Order: get path from DB → delete physical file → clear_file_data → DELETE FROM files.

## Configuration

- **trash_dir:** Config (e.g. `code_analysis.storage.trash_dir` or default `data/trash`). File-level trash uses this same directory with a subfolder per project: `trash_dir/{project_id}/...`.
- **version_dir:** Legacy option (e.g. `file_watcher.version_dir`). When `trash_dir` is not passed to mark/repair, `version_dir` is used so that deleted files go under `version_dir/{project_id}/...`. For consistency with FILE_TRASH_SPEC, prefer passing `trash_dir` so file trash and project trash share the same root.

## Related commands

| Command | Description |
|--------|-------------|
| list_deleted_files | List deleted files for a project (path in trash, original_path, in_trash) |
| unmark_deleted_file | Restore one file; fails with FILE_EXISTS_AT_TARGET if target exists |
| restore_deleted_files | Restore many files; fails with TARGET_FILE_EXISTS if any target exists |
| cleanup_deleted_files | List or hard-delete old deleted files |
| repair_database | Can use trash_dir; restore-from-CST does not overwrite existing files |
