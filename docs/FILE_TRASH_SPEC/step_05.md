# Step 5: UnmarkDeletedFileCommand — pre-check and error when target exists

**Target file:** `code_analysis/commands/file_management.py` (class `UnmarkDeletedFileCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark, **restore** (one or many), permanent delete.
- **This step:** Command that restores **one** file. Before calling DB `unmark_file_deleted` ([Step 3](step_03.md)), check if `original_path` exists on disk; if yes, return a structured error (e.g. `FILE_EXISTS_AT_TARGET`) and a user-facing message instead of calling the DB.
- **Related steps:**  
  - Uses: [Step 3](step_03.md) (unmark_file_deleted).  
  - MCP wrapper: [Step 7](step_07.md) (UnmarkDeletedFileMCPCommand) maps this error to API response.  
  - Batch restore: [Step 6](step_06.md) (RestoreDeletedFilesCommand) reuses the same pre-check logic for multiple files.

---

## Relevant requirements (from [README](README.md))

- **Req. 2:** Restore file; if target path exists in project → error and warning to delete/rename. This step implements that at the command layer.

---

## Goal

Expose pre-check and clear error when target file exists in project.

---

## Actions

- Before calling `database.unmark_file_deleted`, resolve the file record (id, path, original_path). If `original_path` exists on disk, do **not** call `unmark_file_deleted`; return a structured result with `restored=False`, `error` (e.g. "FILE_EXISTS_AT_TARGET") and a message like "File already exists at {original_path}. Delete or rename it before restoring."
- If pre-check passes, call `database.unmark_file_deleted` as now.

---

## Result

Single-file restore from UI/API returns a structured error when the target path already exists. Step 7 uses this to format MCP error responses.

---

## Completion metrics

- [ ] Before calling `unmark_file_deleted`, command resolves file record and checks `original_path` on disk.
- [ ] If target exists: return `restored=False`, `error` (e.g. `FILE_EXISTS_AT_TARGET`), user-facing message; do not call DB restore.
- [ ] If target clear: call `unmark_file_deleted` and return success/failure from it.
- [ ] black, flake8, mypy pass on `file_management.py`.
