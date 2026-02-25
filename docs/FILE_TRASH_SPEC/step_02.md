# Step 2: mark_file_deleted — move to trash and replace if exists

**Target file:** `code_analysis/core/database/files.py` (function `mark_file_deleted`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark file for deletion (move to trash), restore, permanent delete.
- **This step:** Implements "mark file for deletion": move file from project to trash and set `deleted=1`. Uses **trash_dir** (and path from [Step 1](step_01.md)), not `version_dir`. If the same file (same project_id + original_path) is already in trash, replace it.
- **Related steps:**  
  - Depends on: [Step 1](step_01.md) (path `trash_dir/project_id`).  
  - Restore uses: [Step 3](step_03.md) (unmark_file_deleted). Permanent delete uses: [Step 4](step_04.md) (hard_delete_file).  
  - Callers: repair [Step 13](step_13.md), file watcher [Step 10](step_10.md) (optional).

---

## Relevant requirements (from [README](README.md))

- **Req. 1:** Move file to trash and set `deleted=1`; all project files in folder named by project_id.
- **Req. 4:** If file with same logical path already in trash → replace it.

---

## Goal

**Set deleted=1 ⇒ move file to trash.** Move the file from the project folder to `trash_dir/{project_id}/...`, then set DB flag. Replace existing file in trash if same project_id + original_path. The file must not remain in the project path when marked deleted.

---

## Actions

- Change `mark_file_deleted` to accept **trash_dir** (or storage paths object) instead of (or in addition to) **version_dir**. Target path for moved file: `trash_dir / project_id / relative_path` (relative to project root), or hash-based name if relative path cannot be computed. Keep storing in DB: `original_path`, and a single "current location" field (e.g. `path` = path in trash; optionally keep `version_dir` as the logical parent, e.g. `trash_dir/project_id`, for compatibility).
- **Replace-if-exists:** Before moving, check if in DB there is already another file record (or the same record from a previous run) with the same `project_id` and same `original_path` and `deleted=1`, and whose `path` points under `trash_dir/project_id`. If so, delete the physical file at that old `path` (if it exists), then proceed to move the current file to the target and update the record. If the same file (same file_id) is being marked again, overwrite the file at current `path` if it exists.
- Ensure target directory is created; move file; update `files`: `deleted=1`, `original_path`, `version_dir` (or equivalent) = `trash_dir/project_id`, `path` = new path in trash.

---

## Result

Marking a file for deletion moves it to `trash_dir/{project_id}/...` and sets the deletion mark; existing trashed file with same identity is replaced.

---

## Completion metrics

- [ ] `mark_file_deleted` accepts trash_dir (or equivalent) and writes files under `trash_dir/{project_id}/...`.
- [ ] Replace-if-exists: existing trashed file (same project_id + original_path) is removed/overwritten before move.
- [ ] DB updated: `deleted=1`, `original_path`, `path` = path in trash; `version_dir` or equivalent set to trash project subfolder.
- [ ] black, flake8, mypy pass on `files.py`; no regressions in callers (repair, file_management) that pass trash_dir.
