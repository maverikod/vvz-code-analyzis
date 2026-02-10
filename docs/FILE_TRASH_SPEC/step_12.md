# Step 12: Database client (RPC) — file trash operations

**Target file(s):** `code_analysis/core/database_client/` (RPC client that invokes mark_file_deleted, unmark_file_deleted, hard_delete_file, and optionally batch restore)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Context

- **Spec:** [FILE_TRASH_SPEC — step-by-step plan](README.md). The server may use a separate database driver; MCP and other callers use DatabaseClient (RPC) to run DB operations.
- **This step:** Ensure the RPC client exposes the updated file-trash behaviour: (1) mark uses trash_dir (or path from storage); (2) unmark can return "target exists" (or structured error); (3) batch restore pre-check and restore are available if implemented on the server. Add or adjust client methods so they pass through to the implementations from Steps 2, 3, 4, and 6.
- **Related steps:**  
  - Server/DB layer: [Step 2](step_02.md), [Step 3](step_03.md), [Step 4](step_04.md).  
  - Commands that use the client: [Step 5](step_05.md), [Step 6](step_06.md), [Step 7](step_07.md), [Step 8](step_08.md).

---

## Relevant requirements (from [README](README.md))

- All file-trash requirements (mark, restore with pre-check, permanent delete, replace-if-exists, batch restore) must be callable via the client when the architecture uses RPC.

---

## Goal

Expose new or updated operations over RPC if the server uses a separate database driver.

---

## Actions

- If mark_file_deleted, unmark_file_deleted, hard_delete_file are invoked via a client (e.g. DatabaseClient), ensure the client has methods that pass through to the updated implementations (trash_dir, pre-check result, batch restore if added at DB layer). Add or adjust methods so that: (1) mark uses trash_dir; (2) unmark can return "target exists"; (3) batch restore pre-check and restore are available if implemented on the server.

---

## Result

RPC client stays in sync with file trash behaviour. MCP and other callers can use the same API for mark, restore (with errors), and permanent delete.

---

## Completion metrics

- [x] Client method for mark passes trash_dir (or resolved path) to server; no version_dir-only signature for file trash.
- [x] Unmark/restore response can convey "target exists" (e.g. error code or structured result) when server returns it.
- [x] Batch restore pre-check and restore available via client if implemented on server (method exists and is wired).
- [x] black, flake8, mypy pass on database_client modules; no broken call sites.
