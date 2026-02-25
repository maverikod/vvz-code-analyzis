# Step 7: UnmarkDeletedFileMCPCommand — map "target exists" error

**Target file:** `code_analysis/commands/file_management_mcp_commands.py` (class `UnmarkDeletedFileMCPCommand`)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). File-level trash: mark, restore, permanent delete; all exposed via MCP where applicable.
- **This step:** MCP command for restoring **one** file. It must use the updated [Step 5](step_05.md) (UnmarkDeletedFileCommand), which returns a structured error when the target path already exists. Here we map that to a clear MCP error response and user-facing message (e.g. code `FILE_EXISTS_AT_TARGET`, message "File already exists at …; delete or rename it before restoring").
- **Related steps:**  
  - Calls: [Step 5](step_05.md) (UnmarkDeletedFileCommand).  
  - Batch variant: [Step 8](step_08.md) (RestoreDeletedFilesMCPCommand).  
  - List of commands: [README](README.md).

---

## Relevant requirements (from [README](README.md))

- **Req. 2:** Restore file; if target exists → error and warning. This step ensures the MCP API returns that error clearly.

---

## Goal

Keep single-file restore aligned with new pre-check and error codes.

---

## Actions

- Ensure the command uses the updated `UnmarkDeletedFileCommand` (which now performs the "target exists" check and returns a structured error). Map `FILE_EXISTS_AT_TARGET` (or equivalent) to a clear MCP error response and user-facing message.

---

## Result

MCP single-file restore returns a clear error when the target file already exists. Clients can show the message and suggest deleting or renaming the existing file.

---

## Completion metrics

- [ ] Command uses updated `UnmarkDeletedFileCommand` (Step 5) and does not bypass pre-check.
- [ ] When command returns `error=FILE_EXISTS_AT_TARGET` (or equivalent), MCP response has clear error code and user-facing message.
- [ ] Success path unchanged; only error mapping added.
- [ ] black, flake8, mypy pass on `file_management_mcp_commands.py`.
