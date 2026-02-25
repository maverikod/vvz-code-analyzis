# Step 1: File trash path helper

**Target file:** `code_analysis/core/storage_paths.py`

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark file for deletion (move to trash), restore, permanent delete. One step = one code file.
- **This step:** First in the chain. Defines where trashed **files** (per project) live on disk. Project trash (whole folder) already uses `trash_dir`; file trash must use the same root with a subfolder per project: `trash_dir/{project_id}/...`.
- **Related steps:**  
  - Next: [Step 2](step_02.md) (mark_file_deleted) and [Step 4](step_04.md) (hard_delete_file) will use the path from this step.  
  - [Step 9](step_09.md) (project deletion) and [Step 15](step_15.md) (config/docs) reference the same `trash_dir`.

---

## Relevant requirements (from [README](README.md))

- **Req. 1:** All trashed files of a project must live under a folder named by **project_id** → this step provides that path.

---

## Goal

Define a single place for "file trash" path so that trashed files live under `trash_dir/{project_id}/...` (all files of a project in a folder named by project_id).

---

## Actions

- In `resolve_storage_paths`, ensure file-level trash reuses **trash_dir** (no separate file_trash_dir). Document that:
  - `trash_dir` holds both: (1) project folders `trash_dir/ProjectName_timestamp`, (2) file trash per project `trash_dir/{project_id}/...`.
- Add a helper (e.g. `get_file_trash_dir(trash_dir: Path, project_id: str) -> Path`) returning `trash_dir / project_id` for use when moving/listing trashed files.

---

## Result

Callers can resolve `trash_dir` and then `trash_dir / project_id` for file trash of a project. Steps 2, 4, 11, 13 use this to place or find files in trash.

---

## Completion metrics

- [ ] Helper `get_file_trash_dir(trash_dir, project_id)` exists and returns `trash_dir / project_id`.
- [ ] `resolve_storage_paths` (or module docstring) documents that `trash_dir` holds both project folders and file trash per project (`trash_dir/{project_id}/...`).
- [ ] No new linter/type errors in `storage_paths.py`.
- [ ] black, flake8, mypy pass on the modified file.
