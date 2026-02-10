# File-level trash: technical specification (step-by-step plan)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document is a detailed step-by-step implementation plan for file-level trash (mark for deletion, restore, permanent delete). Each step corresponds to changes in **one file** and has its own document in this directory. The plan is based on inspection of the existing codebase (files table, version_dir, project trash, mark_file_deleted, unmark_file_deleted, hard_delete_file, clear_file_data, MCP commands, file_watcher).

---

## How to read the step files

Each step file (e.g. [step_01.md](step_01.md)) is **self-contained** and includes:

- **Context** — Link to this README (the full spec), a short "where this step fits" explanation, and **Related steps** (previous/next and dependent steps) with links.
- **Relevant requirements** — Which of the six requirements below this step implements, with a link back to this README.
- **Target file** — The single code file to change (path in the repo).
- **Goal** — What this step achieves.
- **Actions** — Concrete implementation tasks.
- **Result** — Outcome and how later steps use it.
- **Completion metrics** — Verifiable criteria to consider the step done (checkboxes: code changes, tests, linters, docs, no regressions).

You can open any step file alone and understand what to do, how it relates to other steps via the links, and when to mark the step complete using the metrics.

---

## Requirements summary

**Principle:** Setting the deletion flag must **move the file to trash**; clearing the flag must **move the file back** to its original location in the project. The flag and the file location must stay in sync.

1. **Mark file for deletion (move to trash)**  
   When setting `deleted=1`: **move the file** from the project folder to trash, then set the flag. All trashed files of a project must live under a folder named by **project_id** (e.g. `trash_dir/{project_id}/...`). No "deleted=1" with the file still in the project path.

2. **Restore file (clear flag = move back)**  
   When clearing the deletion flag: **move the file** from trash back to the project folder (original_path), then set `deleted=0`. Before restore: if the target path already exists in the project folder, return an error and a warning that the user must delete or rename the existing file.

3. **Permanent delete from trash**  
   Full delete: remove file from DB with all dependencies (clear_file_data + DELETE files), then delete the physical file from trash and from version storage.

4. **Replace if already in trash**  
   When marking a file for deletion, if a file with the same logical path (same project_id + original_path) is already in trash, replace it (overwrite or remove old file, then move the new one).

5. **Project mark for deletion**  
   When marking a **project** for deletion, all its files are moved from the project folder into a trash subfolder (e.g. project root moved to `trash_dir/ProjectName_timestamp`; files then live under that tree, which is the "subfolder" of trash). No change to the current project-trash behaviour is required beyond ensuring consistency with file trash.

6. **Restore: pre-check for existing files in project**  
   Before restoring **one or several** files, check that **none** of the target paths already exist in the project folder. If **at least one** target path exists, **cancel the whole** restore operation and return an error (with a message about deleting or renaming the conflicting file(s)).

---

## Current state (from code inspection)

- **files table**: `deleted`, `original_path`, `version_dir`, `path` (current path; when deleted, path points to version/trash location).
- **mark_file_deleted** (`code_analysis/core/database/files.py`): moves file to `version_dir/{project_id}/...` (relative or hash-based path), sets `deleted=1`, `original_path`, `version_dir`, updates `path` to target. Uses **version_dir** from config (e.g. `data/versions`), not **trash_dir**.
- **unmark_file_deleted** (same file): finds file by path or original_path, moves from current path back to `original_path`, sets `deleted=0`, clears `original_path` and `version_dir`. **Does not** check whether `original_path` already exists in the project.
- **hard_delete_file** (same file): deletes physical file at `path` (version_dir), calls `clear_file_data(file_id)`, then `DELETE FROM files WHERE id = ?`. Does not explicitly remove from "version" listing if there is a separate structure.
- **clear_file_data** (same file): removes all dependent rows (classes, methods, functions, imports, issues, usages, code_content, code_content_fts, ast_trees, cst_trees, code_chunks, vector_index). Does not touch FAISS file by file (FAISS is project-scoped).
- **Project trash**: `trash_dir` from `StoragePaths`; project roots are moved to `trash_dir/ProjectName_timestamp`. File-level trash currently uses **version_dir** (`data/versions`), structure `version_dir/{project_id}/...`.
- **UnmarkDeletedFileCommand** (`code_analysis/commands/file_management.py`): calls `database.unmark_file_deleted(file_path, project_id)`. No pre-check for existing file at target path; no batch restore with "all or nothing" check.
- **UnmarkDeletedFileMCPCommand** (`code_analysis/commands/file_management_mcp_commands.py`): wrapper for UnmarkDeletedFileCommand; no restore of multiple files; no pre-check.
- **File watcher** (`code_analysis/core/file_watcher_pkg/processor.py`): on detected file delete only sets `deleted=1` in DB (no move to version_dir). So "deleted" files can be either: (a) moved to version_dir by explicit mark_file_deleted, or (b) only DB-flagged by file watcher.
- **StoragePaths** (`code_analysis/core/storage_paths.py`): has `trash_dir` (e.g. `data/trash`). No `file_trash_dir`; file trash is currently version_dir.

---

## Step files in this directory

| Step | File | Target code file | Main change |
|------|------|------------------|-------------|
| 1 | [step_01.md](step_01.md) | storage_paths.py | Helper for file trash path: trash_dir/project_id. |
| 2 | [step_02.md](step_02.md) | files.py | mark_file_deleted: use trash_dir, replace if already in trash. |
| 3 | [step_03.md](step_03.md) | files.py | unmark_file_deleted: fail if original_path exists. |
| 4 | [step_04.md](step_04.md) | files.py | hard_delete_file: delete from trash and version storage. |
| 5 | [step_05.md](step_05.md) | file_management.py | UnmarkDeletedFileCommand: pre-check, return error if target exists. |
| 6 | [step_06.md](step_06.md) | file_management.py | RestoreDeletedFilesCommand: batch restore, cancel if any target exists. |
| 7 | [step_07.md](step_07.md) | file_management_mcp_commands.py | UnmarkDeletedFileMCPCommand: map new errors. |
| 8 | [step_08.md](step_08.md) | file_management_mcp_commands.py | New: RestoreDeletedFilesMCPCommand. |
| 9 | [step_09.md](step_09.md) | project_deletion.py | Align/document project deletion vs file trash. |
| 10 | [step_10.md](step_10.md) | file_watcher processor | Document/align deleted-file handling. |
| 11 | [step_11.md](step_11.md) | file_management_mcp_commands.py | list_deleted_files / get_deleted_files consistency. |
| 12 | [step_12.md](step_12.md) | database_client | RPC methods for new/updated file trash ops. |
| 13 | [step_13.md](step_13.md) | file_management.py + file_management_mcp_commands.py | Repair uses trash_dir and restore pre-check (including restore-from-CST). |
| 14 | [step_14.md](step_14.md) | hooks.py | Register batch restore command. |
| 15 | [step_15.md](step_15.md) | Config + docs | Document file trash layout and behaviour. |

---

## Implementation status

All 15 steps are implemented: storage_paths (get_file_trash_dir), files.py (mark/unmark/hard_delete with trash_dir and pre-check), file_management commands (UnmarkDeletedFileCommand pre-check, RestoreDeletedFilesCommand batch + pre-check), MCP commands (error mapping, RestoreDeletedFilesMCPCommand, list_deleted_files with in_trash), project_deletion and file_watcher documented, database_client RPC and rpc_handlers_file_trash, RepairDatabaseCommand (trash_dir + restore pre-check), hooks registration, and docs (FILE_TRASH.md, config behaviour in storage_paths).

---

## Order of implementation

Recommended order to avoid breaking callers:

1. **storage_paths.py** — file trash path helper.  
2. **files.py** — mark_file_deleted (trash_dir, replace-if-exists).  
3. **files.py** — unmark_file_deleted (pre-check: target must not exist).  
4. **files.py** — hard_delete_file (delete from trash and versions).  
5. **file_management.py** — UnmarkDeletedFileCommand (pre-check + error).  
6. **file_management.py** — RestoreDeletedFilesCommand (batch + pre-check).  
7. **file_management_mcp_commands.py** — UnmarkDeletedFileMCPCommand (error mapping).  
8. **file_management_mcp_commands.py** — RestoreDeletedFilesMCPCommand.  
9. **project_deletion.py** — document/align project deletion with file trash.  
10. **file_watcher processor** — document or align with trash.  
11. **list_deleted_files** — ensure paths and layout.  
12. **database_client** — RPC methods.  
13. **repair** — use trash_dir and pre-check.  
14. **hooks.py** — register new command.  
15. **Config and docs** — layout and behaviour.
