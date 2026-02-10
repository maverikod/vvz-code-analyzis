# Step 13: RepairDatabaseCommand — trash path and restore pre-check

**Target files:** `code_analysis/commands/file_management.py` (class `RepairDatabaseCommand`) and `code_analysis/commands/file_management_mcp_commands.py` (class `RepairDatabaseMCPCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). Repair restores DB consistency with the filesystem: "files in versions" = files under file trash; restore to project only if target path does not exist.
- **This step:** Repair currently uses `version_dir` and may call `mark_file_deleted`. Switch to the same file-trash root: `trash_dir/project_id` ([Step 1](step_01.md)). Pass trash_dir (and project_id) into repair so that "files in versions" means "files under trash_dir/project_id". When restoring a file to original_path (or when restoring from CST into project root), use the same pre-check as [Step 3](step_03.md) / [Step 5](step_05.md): do not restore if target path already exists.
- **Related steps:**  
  - Path: [Step 1](step_01.md). Mark: [Step 2](step_02.md). Unmark/pre-check: [Step 3](step_03.md), [Step 5](step_05.md).

---

## Relevant requirements (from [README](README.md))

- **Req. 2:** Restore only when target path does not exist. Repair must not overwrite an existing file when "restoring" from trash or from CST.

---

## Goal

Repair logic uses the same trash path (trash_dir/project_id) and the same mark_file_deleted / unmark_file_deleted semantics. No overwrite of existing files on restore.

---

## Actions

- Where repair uses `version_dir`, switch to the same root used for file trash (e.g. trash_dir for file trash = trash_dir/project_id). Pass trash_dir (and project_id) into repair so that "files in versions" means "files under trash_dir/project_id". Update any call to `mark_file_deleted` to use the new signature (trash_dir/project_id).
- **Restore-to-project (DB flag only):** When repair detects a file in the project directory but marked deleted, it only updates the DB (deleted=0). No pre-check needed there — the file is already on disk.
- **Restore from trash (unmark_file_deleted):** When repair restores a file from trash to original_path, use the same pre-check as [Step 3](step_03.md): if original_path already exists, do not overwrite; skip and report (or return error).
- **Restore-from-CST to project root:** In `_restore_file_from_cst`, when the target is the project directory (not deleted case: `target_path = self.root_dir / file_path`), add a pre-check: if `target_path.exists()`, do **not** overwrite; skip this file and add to errors or report (same rule as Req. 2). Optional: when target is trash (deleted case), same rule — do not overwrite existing file at that path.

---

## Result

Repair is consistent with file trash layout and restore rules. No separate "version_dir" vs "trash_dir" for files.

---

## Completion metrics

- [x] Repair uses trash_dir (and project_id) for "files in versions" = files under `trash_dir/project_id`; no standalone version_dir for file trash.
- [x] All calls to `mark_file_deleted` use new signature (trash_dir/project_id or equivalent).
- [x] Restore from trash to original_path: pre-check that original_path does not exist; if it exists, do not overwrite (same as Step 3/5).
- [x] Restore-from-CST to project root: pre-check that target path does not exist; if it exists, do not overwrite — skip and report (Req. 2).
- [x] black, flake8, mypy pass on `file_management.py` and `file_management_mcp_commands.py`.
