# Step 3: unmark_file_deleted — restore one file, fail if target exists

**Target file:** `code_analysis/core/database/files.py` (function `unmark_file_deleted`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark file for deletion, **restore**, permanent delete.
- **This step:** Restore **one** file from trash to project folder. If the target path (`original_path`) already exists on disk, do not overwrite — return failure and a clear signal so the caller can show: "File already exists; delete or rename it before restoring."
- **Related steps:**  
  - Inverse of: [Step 2](step_02.md) (mark_file_deleted).  
  - Command layer that calls this: [Step 5](step_05.md) (UnmarkDeletedFileCommand), [Step 6](step_06.md) (RestoreDeletedFilesCommand).  
  - MCP: [Step 7](step_07.md), [Step 8](step_08.md). Repair: [Step 13](step_13.md).

---

## Relevant requirements (from [README](README.md))

- **Req. 2:** Restore file; before restore, if target path exists in project folder → error and warning to delete/rename.

---

## Goal

**Clear deleted=0 ⇒ move file back.** Move the file from trash to the project folder (original_path), then clear the flag. Fail if target path already exists in project (do not overwrite).

---

## Actions

- At the start of `unmark_file_deleted`, after resolving the file record and `original_path`:
  - Check that **original_path** does **not** exist on disk. If it exists, do **not** move or update DB; return False (and optionally set a clear error message/code for the caller).
- Add a small helper used by both sync driver and callers: e.g. `check_original_path_clear(original_path: Path) -> bool` or return an error message so MCP can return a user-facing error and warning: "File already exists at …; delete or rename it before restoring."
- Rest of logic unchanged: create parent dirs, move from current path to original_path, set `deleted=0`, clear `original_path` and `version_dir`.

---

## Result

Single-file restore fails with a clear error if the target file already exists in the project folder. Callers (Steps 5, 6, 7) can map this to API errors.

---

## Completion metrics

- [ ] If `original_path` exists on disk, `unmark_file_deleted` returns False (and does not move or update DB).
- [ ] Caller can distinguish "target exists" (e.g. error message/code or helper) for MCP/API.
- [ ] Restore path: parent dirs created, file moved to original_path, DB: `deleted=0`, `original_path`/`version_dir` cleared.
- [ ] black, flake8, mypy pass on `files.py`.
