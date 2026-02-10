# Step 15: Config and docs — file trash layout and behaviour

**Target files:** Config (e.g. `config.json` or config documentation) and docs (e.g. `docs/commands/file_management/` or a dedicated file-trash doc)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File trash uses `trash_dir` (same as project trash); trashed files are under `trash_dir/{project_id}/...`. Config and user docs must describe this clearly.
- **This step:** (1) In config or config docs: state that file-level trash uses `trash_dir`; trashed files are stored under `trash_dir/{project_id}/...`. If file_watcher has `version_dir`, document whether it is deprecated in favour of trash_dir for files or how both relate. (2) Add or update a short doc (e.g. under docs/commands/file_management/) describing: mark file for deletion (move to trash, set flag), restore one/many (with pre-check), permanent delete from trash, and "replace if already in trash".
- **Related steps:**  
  - Path layout: [Step 1](step_01.md). Behaviour: [Step 2](step_02.md)–[Step 8](step_08.md), [Step 11](step_11.md).

---

## Relevant requirements (from [README](README.md))

- All six requirements should be summarised in user/operator docs so that mark, restore, permanent delete, replace-if-exists, project deletion, and batch restore pre-check are clearly described.

---

## Goal

Document file trash layout and configuration.

---

## Actions

- In `config.json` (or config docs): document that file-level trash uses `trash_dir` (same as project trash); trashed files are stored under `trash_dir/{project_id}/...`. If today file_watcher has `version_dir`, document whether it is deprecated in favour of trash_dir for files or how both relate.
- Add or update a short doc (e.g. under docs/commands/file_management/) describing: mark file for deletion (move to trash, set flag), restore one/many (with pre-check), permanent delete from trash, and "replace if already in trash".

---

## Result

Config and docs clearly describe file trash behaviour and layout. Operators and developers know where trashed files live and how mark/restore/delete work.

---

## Completion metrics

- [x] Config or config docs state: file-level trash uses `trash_dir`; trashed files under `trash_dir/{project_id}/...`; relation to file_watcher `version_dir` (if any) documented.
- [x] User/operator doc added or updated: mark file for deletion (move to trash, set flag), restore one/many (with pre-check), permanent delete from trash, replace if already in trash.
- [x] All six requirements from [README](README.md) are reflected in the documentation.
- [x] No code changes required in this step unless config schema or defaults are extended.
