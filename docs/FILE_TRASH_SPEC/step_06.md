# Step 6: RestoreDeletedFilesCommand — batch restore with pre-check

**Target file:** `code_analysis/commands/file_management.py` (new class `RestoreDeletedFilesCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark, restore **one or several**, permanent delete.
- **This step:** New command to restore **several** files in one go. Rule: if **any** target path already exists in the project folder, **cancel the whole** operation and return an error (list of conflicting paths + message to delete/rename). No partial restore.
- **Related steps:**  
  - Uses: [Step 3](step_03.md) (unmark_file_deleted) for each file after pre-check.  
  - Pre-check is the same idea as [Step 5](step_05.md) but applied to all `original_path`s before any restore.  
  - MCP: [Step 8](step_08.md) (RestoreDeletedFilesMCPCommand) calls this; [Step 14](step_14.md) registers that command.

---

## Relevant requirements (from [README](README.md))

- **Req. 6:** Before restoring one or several files, check that none of the target paths exist in the project folder; if at least one exists, cancel the whole operation and return an error.

---

## Goal

Restore multiple files in one operation; if **any** target path already exists in the project folder, cancel the **whole** operation and return an error.

---

## Actions

- New class `RestoreDeletedFilesCommand(database, project_id, file_paths: List[str], dry_run: bool)`.
- **Step 1:** For each `file_path` in `file_paths`, resolve the file record (id, original_path). Collect all `original_path` values.
- **Step 2:** For each `original_path`, check if that path exists on disk. If **any** exists, **abort:** return success=False, error code (e.g. "TARGET_FILE_EXISTS"), list of conflicting paths, and a message that the user must delete or rename those files before restoring.
- **Step 3:** If all targets are clear, for each file call `database.unmark_file_deleted(file_path, project_id)` (or equivalent). If any restore fails, optionally roll back or report partial failure (recommended: all-or-nothing, fail the whole batch on first failure).
- Support `dry_run`: only run Step 1 and Step 2 and return what would be restored and whether the operation would be allowed.

---

## Result

Batch restore is all-or-nothing and is cancelled if at least one target file already exists in the project. Step 8 exposes this via MCP.

---

## Completion metrics

- [ ] Class `RestoreDeletedFilesCommand(database, project_id, file_paths, dry_run)` implemented.
- [ ] Pre-check: for all file_paths resolve original_path; if any original_path exists on disk → abort with error code, list of conflicting paths, message.
- [ ] If pre-check passes: call `unmark_file_deleted` for each file; all-or-nothing (abort on first failure if required).
- [ ] `dry_run` only runs pre-check and returns what would be restored and whether allowed.
- [ ] black, flake8, mypy pass on `file_management.py`.
