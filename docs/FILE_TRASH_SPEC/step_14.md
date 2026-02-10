# Step 14: Register batch restore command (hooks)

**Target file:** `code_analysis/hooks.py` (and any command registry that registers MCP commands)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). New MCP commands must be registered so they are discoverable and callable.
- **This step:** Register `RestoreDeletedFilesMCPCommand` (or the chosen name) from [Step 8](step_08.md) in the command registry so the batch restore command is available via MCP (e.g. `restore_deleted_files` with `project_id`, `file_paths`, optional `dry_run`).
- **Related steps:**  
  - Command to register: [Step 8](step_08.md) (RestoreDeletedFilesMCPCommand).  
  - Other file-management commands (e.g. unmark_deleted_file) are already registered in the same area; add the new one alongside.

---

## Relevant requirements (from [README](README.md))

- **Req. 6** (batch restore with pre-check) is exposed via this registration. Without it, the command from Step 8 is not visible to clients.

---

## Goal

Register new MCP command(s) (e.g. restore_deleted_files).

---

## Actions

- Register `RestoreDeletedFilesMCPCommand` (or the chosen name) in the command registry so the batch restore command is available via MCP.

---

## Result

New batch restore command is discoverable and callable. Clients can list commands and call `restore_deleted_files` with a list of file paths.

---

## Completion metrics

- [x] `RestoreDeletedFilesMCPCommand` (or chosen name) registered in the command registry used by MCP.
- [x] Command appears in list of available commands (e.g. help/list_servers or equivalent); callable with project_id and file_paths.
- [x] No duplicate registration; existing file_management commands still work.
- [x] black, flake8, mypy pass on `hooks.py` (if modified).
