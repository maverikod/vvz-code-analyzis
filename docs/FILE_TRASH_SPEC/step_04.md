# Step 4: hard_delete_file — permanent delete from trash

**Target file:** `code_analysis/core/database/files.py` (function `hard_delete_file`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark, restore, **permanent delete**.
- **This step:** "Delete from trash" = remove file from DB (with all dependencies via `clear_file_data`) and delete the physical file from trash (and from version storage if different). Order: (1) get path from DB, (2) delete file on disk, (3) clear_file_data, (4) DELETE FROM files.
- **Related steps:**  
  - Path to file on disk comes from `files.path` (set when marking in [Step 2](step_02.md)); trash root from [Step 1](step_01.md).  
  - Callers: cleanup/delete-from-trash UI or commands; [Step 11](step_11.md) (list deleted) and [Step 12](step_12.md) (RPC) expose or use this.

---

## Relevant requirements (from [README](README.md))

- **Req. 3:** Permanent delete from trash: remove from DB with all dependencies, then delete file from trash and from version storage.

---

## Goal

Full delete: remove from DB (with all dependencies) and delete physical file from trash and from version storage.

---

## Actions

- In `hard_delete_file`: keep current order: (1) get `path` and `version_dir` from `files` for `file_id`; (2) if physical file exists at `path`, delete it (and remove empty parent dirs under trash/project_id); (3) call `clear_file_data(file_id)`; (4) `DELETE FROM files WHERE id = ?`; commit.
- Ensure the path used for deletion is the one stored in `files.path` (trash path). If you still have a separate "version" copy elsewhere (e.g. under old version_dir), remove that too if present. Document that "version" and "trash" for files are the same place: `trash_dir/{project_id}/...`.

---

## Result

Permanent delete removes the file from DB (and all dependencies) and deletes the file from trash and any version copy.

---

## Completion metrics

- [ ] Order preserved: get path from DB → delete physical file at `path` (and empty parents under trash) → `clear_file_data(file_id)` → DELETE FROM files → commit.
- [ ] Any separate "version" copy under old version_dir is also removed if present.
- [ ] Docstring or comment states that file trash and version storage are the same place (`trash_dir/{project_id}/...`).
- [ ] black, flake8, mypy pass on `files.py`.
