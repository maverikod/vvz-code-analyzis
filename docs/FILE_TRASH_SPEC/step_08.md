# Step 8: RestoreDeletedFilesMCPCommand — batch restore via MCP

**Target file:** `code_analysis/commands/file_management_mcp_commands.py` (new class `RestoreDeletedFilesMCPCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark, restore one or **several**, permanent delete.
- **This step:** New MCP command that exposes **batch** restore. Parameters: `project_id`, `file_paths` (list of paths — current path in trash or original_path), optional `dry_run`. Calls [Step 6](step_06.md) (RestoreDeletedFilesCommand); on pre-check failure returns error with code and list of conflicting paths.
- **Related steps:**  
  - Calls: [Step 6](step_06.md) (RestoreDeletedFilesCommand).  
  - Single-file restore: [Step 7](step_07.md) (UnmarkDeletedFileMCPCommand).  
  - Registration: [Step 14](step_14.md) (hooks.py) registers this command.

---

## Relevant requirements (from [README](README.md))

- **Req. 6:** Before restoring one or several files, check that no target path exists; if any exists, cancel whole operation. Step 6 implements that; this step exposes it via API.

---

## Goal

Expose batch restore with pre-check (no restore if any target exists in project).

---

## Actions

- New command class, e.g. `RestoreDeletedFilesMCPCommand`, with parameters: `project_id`, `file_paths` (list of strings: current path or original_path), optional `dry_run`.
- Call `RestoreDeletedFilesCommand`; on success return list of restored paths; on pre-check failure return error with code and list of conflicting paths and a warning that the user must delete or rename them.

---

## Result

API supports batch restore with "cancel if any file exists in project" semantics. Step 14 registers this command so it is discoverable via MCP.

---

## Completion metrics

- [ ] New class `RestoreDeletedFilesMCPCommand` with params: `project_id`, `file_paths` (list), optional `dry_run`.
- [ ] Calls `RestoreDeletedFilesCommand`; on success returns list of restored paths; on pre-check failure returns error with code and conflicting paths list.
- [ ] Schema and help text describe batch restore and pre-check behaviour.
- [ ] black, flake8, mypy pass on `file_management_mcp_commands.py`.
