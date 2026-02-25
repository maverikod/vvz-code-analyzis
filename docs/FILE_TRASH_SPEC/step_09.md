# Step 9: DeleteProjectCommand — project deletion and file trash layout

**Target file:** `code_analysis/commands/project_deletion.py` (class `DeleteProjectCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash lives under `trash_dir/{project_id}/...`; **project** trash moves the whole project folder to `trash_dir/ProjectName_timestamp`.
- **This step:** When marking a **project** for deletion, all its files are moved from the project folder into a trash subfolder. Current behaviour: project root is moved to `trash_dir/ProjectName_timestamp`, so all files move with it. This step ensures that behaviour is explicit and consistent with the chosen layout; optionally document or adjust if product wants project trash to use `trash_dir/{project_id}/` instead (move each file there, then mark).
- **Related steps:**  
  - Same `trash_dir` as [Step 1](step_01.md). File-level mark: [Step 2](step_02.md).  
  - Restore project from trash is a separate flow (restore_project_from_trash); project deletion only "sends" the project to trash.

---

## Relevant requirements (from [README](README.md))

- **Req. 5:** When marking project for deletion, all its files are moved from the project folder into a trash subfolder. Current implementation does this by moving the whole project root; this step documents or aligns that.

---

## Goal

When marking a **project** for deletion, ensure all its files are moved from the project folder into a trash subfolder.

---

## Actions

- Current behaviour: project root is moved to `trash_dir/ProjectName_timestamp`. That already moves all files from the project folder into that trash subfolder. Ensure that:
  - Before moving the project root, all file records are marked `deleted=1` (already done via `mark_project_deleted_impl` which updates `files`).
  - After moving, DB still has `path` pointing to the old project path; optionally you can add a later step or migration that updates `path` to the new location under trash for consistency. For "all files in a folder named by project_id": the project folder in trash is named by `ProjectName_timestamp`, not by `project_id`. If the requirement is "files must be under a folder named project_id", then when moving a **project** to trash you would: (1) create `trash_dir/{project_id}/` and move each project file there (by relative path), then (2) mark all files deleted and update their `path` to `trash_dir/{project_id}/...`. That would be a different design (project trash = many files under trash_dir/project_id, not one folder ProjectName_timestamp). The spec assumes: file-level trash = trash_dir/project_id/...; project-level trash = whole folder to trash_dir/ProjectName_timestamp. If product wants project trash to also use trash_dir/project_id/, this step would be "move each file from project root to trash_dir/project_id/relative_path, then mark project and files deleted". Clarify with product; here we only document that this step must align project deletion with the chosen layout.
- Document in this file: "When marking project for deletion, all its files are moved into a trash subfolder (current implementation: project root moved to trash_dir/ProjectName_timestamp)."

---

## Result

Project deletion behaviour is explicit and consistent with the chosen trash layout. No ambiguity with file-level trash (trash_dir/project_id).

---

## Completion metrics

- [ ] Before moving project root, file records are marked deleted (e.g. via `mark_project_deleted_impl`); project root then moved to `trash_dir/ProjectName_timestamp`.
- [ ] In-file comment or docstring documents: "When marking project for deletion, all its files are moved into a trash subfolder (current implementation: project root moved to trash_dir/ProjectName_timestamp)."
- [ ] If product chose alternative (trash_dir/project_id per file): implementation and doc updated accordingly.
- [ ] black, flake8, mypy pass on `project_deletion.py`.
