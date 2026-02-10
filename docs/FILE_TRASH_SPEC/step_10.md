# Step 10: File watcher — deleted file handling

**Target file:** `code_analysis/core/file_watcher_pkg/processor.py` (deleted-files handling)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark (move to trash), restore, permanent delete.
- **This step:** The file watcher detects when a file **disappears** from disk. Currently it only sets `deleted=1` in the DB and does **not** move the file (it is already gone). If the product wants "every deleted file ends up in trash", the watcher would need to move the file to trash **before** it is deleted from disk (e.g. on "about to delete" or only when the user explicitly "moves to trash"). This step: document current behaviour; optionally call the same "move to trash + mark" logic as [Step 2](step_02.md) when configured (e.g. when version_dir is actually file trash path = trash_dir/project_id).
- **Related steps:**  
  - Mark in DB + move: [Step 2](step_02.md) (mark_file_deleted).  
  - Trash path: [Step 1](step_01.md).  
  - If no code change: only document that file watcher sets deleted=1 and does not move files.

---

## Relevant requirements (from [README](README.md))

- **Principle (README):** Set flag ⇒ move to trash; clear flag ⇒ move back. The file watcher is the **only exception**: when a file has already disappeared from disk, we can only set `deleted=1` (no physical move). Explicit "mark for deletion" must always move the file to trash.
- **Req. 1** (mark file for deletion) is usually done explicitly by the user. File watcher handles the case "file was removed from disk"; whether that should also move to trash is a product decision (often not possible if the file is already gone).

---

## Goal

When the file watcher detects a file deletion on disk, optionally move it to trash (trash_dir/project_id/...) and set DB, instead of only setting deleted=1.

---

## Actions

- Currently the processor only sets `deleted=1` and does not move the file (file is already gone from disk). If the product wants "every deleted file ends up in trash", the watcher would need to be changed to move the file to trash **before** it is deleted from disk (e.g. on "about to delete" or by not treating disappearance as delete but as "move to trash" only when explicitly requested). This is a product decision. In this step, document the current behaviour and, if required, add a call to the same "move to trash + mark" logic used by mark_file_deleted (using trash_dir/project_id/...) when the watcher is configured to do so (e.g. when version_dir is actually the file trash path). If no change: only document that file watcher only sets deleted=1 and does not move files.

---

## Result

File watcher behaviour is documented and, if needed, aligned with file trash under trash_dir/project_id.

---

## Completion metrics

- [x] Current behaviour documented: on file disappearance watcher sets `deleted=1` only (no move; file already gone).
- [x] If product requires "deleted file in trash": logic to move to trash_dir/project_id and mark is added and documented; otherwise only documentation updated.
- [x] No regressions: existing `deleted=1` path still works; workers still skip deleted files.
- [x] black, flake8, mypy pass on `processor.py`.
