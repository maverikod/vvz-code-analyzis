# FILE_TRASH_SPEC — verification report

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document checks the codebase against [README.md](README.md) and steps 1–15. **Все ли учтено** — что сделано, что нет, расхождения.

---

## Summary table

| Step | Target | Status | Notes |
|------|--------|--------|--------|
| 1 | storage_paths.py | **Done** | `get_file_trash_dir` added; trash_dir doc updated |
| 2 | files.py — mark_file_deleted | **Done** | trash_dir param, replace-if-exists |
| 3 | files.py — unmark_file_deleted | **Done** | Pre-check + out_error for FILE_EXISTS_AT_TARGET |
| 4 | files.py — hard_delete_file | **Done** | Docstring updated |
| 5 | file_management.py — UnmarkDeletedFileCommand | **Done** | Pre-check, FILE_EXISTS_AT_TARGET |
| 6 | file_management.py — RestoreDeletedFilesCommand | **Done** | Batch restore + pre-check |
| 7 | file_management_mcp_commands.py — UnmarkDeletedFileMCPCommand | **Done** | Error mapping for FILE_EXISTS_AT_TARGET |
| 8 | file_management_mcp_commands.py — RestoreDeletedFilesMCPCommand | **Done** | + Step 14 registered in hooks |
| 9 | project_deletion.py | **Done** | In-file doc project trash layout |
| 10 | file_watcher processor | **Done** | Comment: only SET deleted=1, no move |
| 11 | list_deleted_files / get_deleted_files | **Done** | get_deleted_files returns path in trash; MCP list_deleted_files added and registered |
| 12 | database_client | **N/A** | RPC client; server uses driver with mark/unmark |
| 13 | repair | **Done** | trash_dir param, pre-check restore-from-CST (no overwrite) |
| 14 | hooks.py | **Done** | RestoreDeletedFilesMCPCommand registered |
| 15 | Config + docs | **Done** | FILE_TRASH.md + README updated |

---

## Requirements (README) vs implementation

1. **Mark file for deletion (move to trash)**  
   Partially: file is moved to `version_dir/{project_id}/...`, not `trash_dir/{project_id}/...`. Replace-if-exists not implemented.

2. **Restore file (clear flag = move back), fail if target exists**  
   Not implemented: no check that original_path is clear; restore can overwrite.

3. **Permanent delete from trash**  
   Implemented in spirit (physical delete + clear_file_data + DELETE). Path is version path; no separate “version copy” cleanup.

4. **Replace if already in trash**  
   Not implemented: no logic to remove/overwrite existing trashed file with same project_id + original_path.

5. **Project mark for deletion**  
   Current behaviour: project root → trash_dir/ProjectName_timestamp. Not documented in project_deletion.py as required.

6. **Restore: pre-check for existing files in project**  
   Not implemented: no batch restore command; single-file restore has no pre-check.

---

## Step-by-step detail

### Step 1 — storage_paths.py

- **Missing:** `get_file_trash_dir(trash_dir: Path, project_id: str) -> Path` returning `trash_dir / project_id`.
- **Missing:** In `resolve_storage_paths` or module docstring: document that `trash_dir` holds (1) project folders `trash_dir/ProjectName_timestamp`, (2) file trash per project `trash_dir/{project_id}/...`.

### Step 2 — mark_file_deleted

- **Current:** Accepts `version_dir`, builds `version_dir_path = Path(version_dir) / project_id`, moves file there.
- **Missing:** Parameter/semantic switch to `trash_dir` (or storage paths) so file trash lives under `trash_dir/{project_id}/...`.
- **Missing:** Replace-if-exists: if same project_id + original_path already in trash, remove/overwrite old file before move.

### Step 3 — unmark_file_deleted

- **Missing:** At start, check that `original_path` does not exist on disk. If it exists: return False (and optionally error message/code), do not move or update DB.

### Step 4 — hard_delete_file

- **Current:** Get path from DB → delete physical file → clear_file_data → DELETE FROM files. Order matches spec.
- **Missing:** Docstring/comment that file trash and version storage are the same place (`trash_dir/{project_id}/...`). If a separate version copy under old path is ever used, remove it too.

### Step 5 — UnmarkDeletedFileCommand

- **Missing:** Before calling `unmark_file_deleted`, resolve file record and check that `original_path` does not exist on disk.
- **Missing:** If target exists: return `restored=False`, `error` (e.g. `FILE_EXISTS_AT_TARGET`), user-facing message; do not call DB restore.

### Step 6 — RestoreDeletedFilesCommand

- **Missing:** New class `RestoreDeletedFilesCommand(database, project_id, file_paths, dry_run)` with: (1) resolve all original_paths, (2) pre-check all targets clear; if any exists → abort with error and list of conflicting paths, (3) if clear, call `unmark_file_deleted` for each (all-or-nothing), (4) dry_run only pre-check + report.

### Step 7 — UnmarkDeletedFileMCPCommand

- **Missing:** Map `FILE_EXISTS_AT_TARGET` (or equivalent) from UnmarkDeletedFileCommand to clear MCP error code and user-facing message. Depends on Step 5.

### Step 8 — RestoreDeletedFilesMCPCommand

- **Missing:** New MCP command class (e.g. `RestoreDeletedFilesMCPCommand`) with `project_id`, `file_paths`, optional `dry_run`; call RestoreDeletedFilesCommand; on pre-check failure return error with code and conflicting paths.

### Step 9 — project_deletion.py

- **Missing:** In-file comment or docstring: “When marking project for deletion, all its files are moved into a trash subfolder (current implementation: project root moved to trash_dir/ProjectName_timestamp).”

### Step 10 — file_watcher processor

- **Current:** On file disappearance only `SET deleted = 1` (no move; file already gone). Matches spec’s “only exception”.
- **Missing:** Document this behaviour in processor (and optionally in FILE_TRASH_SPEC or file_management docs).

### Step 11 — list_deleted_files / get_deleted_files

- **Current:** `get_deleted_files(project_id)` returns rows; `path` is current path (version/trash). When mark uses version_dir, path is under version_dir.
- **Missing:** After Step 1–2, ensure path is under `trash_dir/{project_id}/...` and list is consistent. Optional: MCP command `list_deleted_files(project_id)` with path, original_path, in_trash.

### Step 12 — database_client

- **Current:** No `mark_file_deleted`, `unmark_file_deleted`, `hard_delete_file` in client_api_files. MCP uses `_open_database_from_config` (likely in-process driver).
- **Conclusion:** If all file-trash callers use in-process driver, Step 12 is N/A. If any caller uses RPC, add/wire client methods for mark (with trash_dir), unmark (with “target exists” result), batch restore.

### Step 13 — repair

- **Current:** RepairDatabaseCommand uses `self.version_dir` and passes it to `mark_file_deleted`. Restore-from-CST: if `target_path.exists()` it creates backup and overwrites.
- **Missing:** Use trash_dir (and project_id) for “files in versions” = files under `trash_dir/project_id`. All `mark_file_deleted` calls with new signature (trash_dir/project_id).
- **Missing:** Restore from trash to original_path: pre-check original_path does not exist; if exists, do not overwrite (skip and report).
- **Missing:** Restore-from-CST to project root: pre-check target path does not exist; if exists, do not overwrite — skip and report (Req. 2).

### Step 14 — hooks.py

- **Missing:** Register `RestoreDeletedFilesMCPCommand` (after Step 8). RestoreDeletedFilesMCPCommand not imported or registered.

### Step 15 — Config and docs

- **Missing:** In config or config docs: file-level trash uses `trash_dir`; trashed files under `trash_dir/{project_id}/...`; relation to file_watcher `version_dir` (deprecation or how both relate).
- **Missing:** User/operator doc: mark file for deletion (move to trash, set flag), restore one/many (with pre-check), permanent delete from trash, replace if already in trash. All six requirements summarised.

---

## Cross-references in spec

- **Step 11 (step_11.md)** says target is “file_management_mcp_commands.py (and internal get_deleted_files in files.py if needed)”. README table says “list_deleted_files” in “file_management_mcp_commands.py”. So step 11 covers both: consistency of get_deleted_files with trash layout and optional MCP list_deleted_files. Accounted in verification above.
- **Step 12** refers to “database_client” and RPC. Architecture (in-process vs RPC for file operations) is not fully visible from current grep; verification marks Step 12 as N/A or not done depending on usage.
- **Order of implementation** in README is 1→2→…→15. Code currently follows the old model (version_dir, no pre-checks, no batch restore). Implementing in that order will keep callers consistent.

---

## Conclusion

**Не всё учтено в коде.** Спека полная и непротиворечивая; в реализации:

- Сделано по сути: перенос файла в каталог при mark, удаление с диска и из БД при hard_delete, наличие get_deleted_files и unmark (без pre-check).
- Не сделано: единый корень file trash через `trash_dir/{project_id}` (Step 1–2), pre-check при restore (Steps 3, 5, 6, 7, 13), replace-if-exists (Step 2), batch restore и его MCP (Steps 6, 8, 14), переключение repair на trash_dir и pre-check (Step 13), явная документация в коде и конфиге (Steps 9, 10, 15), при необходимости — RPC-методы (Step 12).

Рекомендация: реализовывать по порядку 1→15, обновляя этот отчёт после каждого шага.
