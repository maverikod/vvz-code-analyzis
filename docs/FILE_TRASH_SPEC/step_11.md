# Step 11: list_deleted_files / get_deleted_files — consistency with trash layout

**Target file:** `code_analysis/commands/file_management_mcp_commands.py` (and internal `get_deleted_files` in `code_analysis/core/database/files.py` if needed)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: files live under `trash_dir/{project_id}/...`; DB field `files.path` holds the path in trash.
- **This step:** Listing deleted files must return entries whose `path` is the path in trash (under trash_dir/project_id). If there is an MCP command that lists deleted files, ensure it returns these paths and, if useful, a flag or field like "in_trash". If the only list is internal `get_deleted_files(project_id)`, ensure the returned `path` is the trash path and that callers (restore, permanent delete) use it correctly.
- **Related steps:**  
  - Path layout: [Step 1](step_01.md), [Step 2](step_02.md).  
  - Restore uses path: [Step 3](step_03.md), [Step 5](step_05.md), [Step 6](step_06.md). Permanent delete: [Step 4](step_04.md).

---

## Relevant requirements (from [README](README.md))

- All operations (restore, permanent delete) assume deleted files are under trash_dir/project_id. This step ensures the list API is consistent with that layout.

---

## Goal

Ensure listing deleted files returns entries that live under trash_dir/project_id (path in DB = path in trash).

---

## Actions

- If there is an MCP command that lists deleted files, ensure it returns paths and, if useful, a flag or field indicating "in_trash" (path under trash_dir). If the only list is internal `get_deleted_files(project_id)`, ensure the returned `path` is the trash path and that callers (e.g. restore, permanent delete) use it correctly.
- **Optional:** Add a dedicated MCP command `list_deleted_files(project_id)` that exposes `get_deleted_files(project_id)` and returns the list with `path` (trash path) and optionally `original_path`, `in_trash=True`, so clients can show deleted files and call restore/permanent-delete with the correct paths.

---

## Result

List deleted files API is consistent with trash layout. Restore and permanent-delete flows get correct paths from the list.

---

## Completion metrics

- [x] Deleted files list returns `path` = path in trash (under trash_dir/project_id); no stale project paths for trashed files.
- [x] If MCP command exists for listing deleted files: response includes paths and optionally "in_trash" or equivalent; callers (restore, permanent delete) use same paths.
- [x] Optional: `list_deleted_files(project_id)` MCP command added and registered if product needs it.
- [x] `get_deleted_files(project_id)` (if used) returns rows with trash path in `path`; no behavioural regression for existing callers.
- [x] black, flake8, mypy pass on modified files.
