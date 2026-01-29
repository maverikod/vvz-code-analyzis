# Project Trash (Recycle Bin) — Refactoring Plan

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## 1. Current State

### 1.1 Delete project flow

- **MCP command**: `delete_project` (in `project_management_mcp_commands.py`).
- **Internal command**: `DeleteProjectCommand` in `commands/project_deletion.py`.
- **Behaviour**:
  - Always clears project data from the database via `_clear_project_data_impl()` (files, chunks, datasets, duplicates, versions metadata, etc.).
  - If `delete_from_disk=True`:
    - Deletes version directory: `{version_dir}/{project_id}/` with `shutil.rmtree`.
    - Deletes project root directory with `shutil.rmtree`.
  - Order today: **disk deletion first**, then DB clear. So when `delete_from_disk=True`, project directory is removed permanently; there is **no trash**.

### 1.2 Configuration

- DB path: from `storage_paths.resolve_storage_paths()` (e.g. `code_analysis.db_path` → `data/code_analysis.db`).
- Version directory: `code_analysis.file_watcher.version_dir` (e.g. `data/versions`).
- There is **no** `trash_dir` or recycle bin path in config or `StoragePaths`.

### 1.3 Gaps

- No project recycle bin: deleted projects are lost when `delete_from_disk=True`.
- No way to list deleted (trashed) projects.
- No way to permanently delete a single project from trash.
- No way to empty the whole trash.

---

## 2. Goals

1. **Introduce a project trash (recycle bin)**  
   When a project is “deleted from disk” via MCP, move it to a trash directory instead of removing it permanently.

2. **Trash folder naming**  
   Format:  
   `{original_project_name}_{YYYY-MM-DDThh-mm-ss}Z`  
   - `original_project_name`: project `name` from DB (or basename of `root_path` if name is empty); sanitized for filesystem (e.g. replace `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`).
   - Timestamp: deletion time in UTC, ISO-like format with `T` and `Z`, with colons replaced by `-` if needed for FS (e.g. `2025-01-29T14-30-00Z`).

3. **Order of operations for delete_project**  
   - First: **full removal from DB** (all project data).
   - Then: if “delete from disk” is requested, **move** project directory (and optionally version data) into trash; do **not** `shutil.rmtree` the project root.

4. **New commands**  
   - List trashed projects.  
   - Permanently delete one project from trash (by identifier: trash folder name or path).  
   - Clear trash completely (permanent delete of all contents).

---

## 3. Design

### 3.1 Trash directory

- **Config**: add `trash_dir` under service state (e.g. `code_analysis.storage.trash_dir`).
- **Default**: e.g. `data/trash` or `data/project_trash` (relative to config dir), same pattern as `backup_dir`, `locks_dir`.
- **StoragePaths**: add field `trash_dir: Path`; resolve in `resolve_storage_paths()`; create in `ensure_storage_dirs()`.

### 3.2 Trash folder name

- **Format**: `{sanitized_name}_{YYYY-MM-DDThh-mm-ss}Z`
- **Sanitization**: replace characters illegal or problematic in filenames (`/ \ : * ? " < > |`) by `_`; collapse multiple `_`; strip leading/trailing `_` and dots; if result is empty, use `project_{project_id}` or `project_{first_8_chars_of_project_id}`.
- **Uniqueness**: if `trash_dir / final_name` already exists, append `_1`, `_2`, … until the path is unique.

### 3.3 delete_project (refactor)

- **Order of operations** (change from current):
  1. Load project from DB (need `name`, `root_path`).
  2. **Clear all project data from DB** (`_clear_project_data_impl`).
  3. If `delete_from_disk=True` and project `root_path` exists:
     - Build trash folder name: `{sanitized_name}_{ISO}Z`.
     - Ensure `trash_dir` exists.
     - `shutil.move(Path(root_path), trash_dir / trash_folder_name)`.
     - Version dir: either **move** `{version_dir}/{project_id}/` to `trash_dir/{trash_folder_name}/versions` (so one trashed entry = project root + its versions), or **delete** `{version_dir}/{project_id}/` (simpler; backups/versions are optional in trash). Plan recommends: **delete** version dir for this project (no need to keep in trash unless product requires it).
- **Backward compatibility**: keep parameter `delete_from_disk`; when `True`, “delete” means “move to trash” instead of “rmtree”. Optionally add a flag `permanent_delete_from_disk=False` for future: if True, skip trash and do current rmtree behaviour (for admin use only).

### 3.4 List trashed projects

- **Input**: optional `trash_dir` override (default from config).
- **Behaviour**: list direct children of `trash_dir` that are directories; parse folder names with regex to extract `original_name` and `deleted_at`; return list of `{ "folder_name", "original_name", "deleted_at", "path" }`.
- **Naming**: command e.g. `list_trashed_projects` (MCP) and internal `ListTrashedProjectsCommand`.

### 3.5 Permanently delete one project from trash

- **Input**: identifier of the trashed entry — either:
  - `trash_folder_name` (e.g. `MyProject_2025-01-29T14-30-00Z`), or
  - full path to that folder (if we want to support paths outside default trash_dir).
- **Behaviour**: resolve to one directory under `trash_dir` (or allowed path); `shutil.rmtree` that directory; return success/error.
- **Naming**: e.g. `permanently_delete_from_trash` (MCP), internal `PermanentlyDeleteFromTrashCommand`.

### 3.6 Clear trash completely

- **Input**: optional `trash_dir` (default from config); optional `dry_run`.
- **Behaviour**: list all direct children of `trash_dir`; for each directory, `shutil.rmtree`; optionally report list of removed folders.
- **Naming**: e.g. `clear_trash` (MCP), internal `ClearTrashCommand`.

---

## 4. Implementation Plan

### Step 1: Config and StoragePaths (trash_dir)

- **Files**: `config.json` (or doc only), `code_analysis/core/storage_paths.py`.
- **Changes**:
  - In `StoragePaths` dataclass add `trash_dir: Path`.
  - In `resolve_storage_paths()`: read `code_analysis.storage.trash_dir`; if missing, default to `data/trash` (relative to config dir); resolve to absolute and set `trash_dir`.
  - In `ensure_storage_dirs()`: `paths.trash_dir.mkdir(parents=True, exist_ok=True)`.
- **Config example**:  
  `"storage": { "trash_dir": "data/trash" }`  
  (optional; default can stay in code.)

### Step 2: Trash name helper and move-to-trash

- **New file** (optional): `code_analysis/core/trash_utils.py` (or put helpers in `project_deletion.py`).
- **Functions**:
  - `sanitize_project_name(name: str, project_id: str) -> str`: sanitize for FS; fallback to `project_{id[:8]}`.
  - `build_trash_folder_name(project_name: str, project_id: str, deleted_at_utc: datetime) -> str`: return `{sanitized}_{YYYY-MM-DDThh-mm-ss}Z`.
  - `ensure_unique_trash_path(trash_dir: Path, base_name: str) -> Path`: if `trash_dir / base_name` exists, append `_1`, `_2`, …
- **Move to trash**: given `root_path`, `trash_dir`, `trash_folder_name`: `shutil.move(Path(root_path), trash_dir / trash_folder_name)`; on Windows handle “directory exists” by renaming to unique name.

### Step 3: Refactor DeleteProjectCommand

- **File**: `code_analysis/commands/project_deletion.py`.
- **Changes**:
  - Add constructor args: `trash_dir: Optional[str] = None` (and pass from MCP when delete_from_disk).
  - **Order**: first call `await _clear_project_data_impl(self.database, self.project_id)` (so DB is cleared while project dir still exists).
  - Then, if `delete_from_disk` and `Path(root_path).exists()`:
    - Resolve `trash_dir` (from param or config).
    - `deleted_at_utc = datetime.now(timezone.utc)`.
    - `trash_folder_name = build_trash_folder_name(project_name, project_id, deleted_at_utc)`.
    - `dest = ensure_unique_trash_path(Path(trash_dir), trash_folder_name)`.
    - `shutil.move(Path(root_path), dest)`.
    - Delete version dir for this project: `shutil.rmtree(version_dir / project_id)` if exists (no move of versions into trash in minimal version).
  - Remove the current “rmtree project root” and “rmtree version dir” before DB clear; keep only version dir rmtree after move (as above).
- **Error handling**: if move fails, log error and optionally leave project root in place (DB already cleared); return result with `disk_deletion_errors` or similar.

### Step 4: MCP delete_project — pass trash_dir

- **File**: `code_analysis/commands/project_management_mcp_commands.py`.
- **Changes**:
  - When calling `DeleteProjectCommand`, resolve `trash_dir` from config (e.g. `storage.trash_dir` or new `resolve_storage_paths().trash_dir`).
  - Pass `trash_dir=str(storage.trash_dir)` into `DeleteProjectCommand` when `delete_from_disk=True`.
  - Optionally: extend metadata/description to state that “delete from disk” moves project to trash instead of permanent delete.

### Step 5: List trashed projects — internal command

- **File**: `code_analysis/commands/project_deletion.py` (or new `commands/trash_commands.py` if you prefer to keep deletion and trash in one module).
- **Class**: `ListTrashedProjectsCommand`.
  - `__init__(self, trash_dir: str)`.
  - `async def execute(self) -> Dict[str, Any]`: list `Path(trash_dir).iterdir()`; for each directory, parse name with regex `^(.+)_(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)$`; return `{"success": True, "items": [{"folder_name": ..., "original_name": ..., "deleted_at": ...}]}`.

### Step 6: List trashed projects — MCP command

- **File**: `code_analysis/commands/project_management_mcp_commands.py` (category `project_management`).
- **Class**: `ListTrashedProjectsMCPCommand`.
  - `name = "list_trashed_projects"`.
  - Params: optional `trash_dir` (default from config).
  - Resolve config, get `trash_dir`, run `ListTrashedProjectsCommand`, return result.

### Step 7: Permanently delete one from trash — internal command

- **File**: same as Step 5.
- **Class**: `PermanentlyDeleteFromTrashCommand`.
  - `__init__(self, trash_dir: str, trash_folder_name: str)`.
  - `execute`: path = `Path(trash_dir) / trash_folder_name`; validate that path is under `trash_dir` (no escape); if not exists or not dir, error; `shutil.rmtree(path)`; return success.

### Step 8: Permanently delete one from trash — MCP command

- **File**: `project_management_mcp_commands.py`.
- **Class**: `PermanentlyDeleteFromTrashMCPCommand`.
  - `name = "permanently_delete_from_trash"`.
  - Params: `trash_folder_name` (required); optional `trash_dir`.
  - Call internal command, return result.

### Step 9: Clear trash — internal command

- **File**: same as Step 5.
- **Class**: `ClearTrashCommand`.
  - `__init__(self, trash_dir: str, dry_run: bool = False)`.
  - `execute`: list directories in `trash_dir`; if dry_run return list; else for each dir `shutil.rmtree`; return count and list of removed folder names.

### Step 10: Clear trash — MCP command

- **File**: `project_management_mcp_commands.py`.
- **Class**: `ClearTrashMCPCommand`.
  - `name = "clear_trash"`.
  - Params: optional `dry_run`, optional `trash_dir`.
  - Call internal command, return result.

### Step 11: Registration and docs

- **File**: `code_analysis/hooks.py`: register `ListTrashedProjectsMCPCommand`, `PermanentlyDeleteFromTrashMCPCommand`, `ClearTrashMCPCommand`.
- **Docs**: add `docs/commands/project_management/list_trashed_projects.md`, `permanently_delete_from_trash.md`, `clear_trash.md`; update `delete_project.md` (new behaviour: move to trash); update `docs/commands/project_management/COMMANDS.md` and any index.

### Step 12: Tests ✅

- Unit tests: `tests/test_trash_utils.py` — `sanitize_project_name`, `build_trash_folder_name`, `ensure_unique_trash_path`.
- Unit tests: `tests/test_trash_commands.py` — `ListTrashedProjectsCommand`, `PermanentlyDeleteFromTrashCommand`, `ClearTrashCommand` (with temp trash_dir).
- Integration: `DeleteProjectCommand` with `delete_from_disk=True` covered by existing flow; trash commands tested with temp dir.
- StoragePaths mocks updated: `tests/integration/test_commands.py`, `tests/test_main_process_integration.py` — added `trash_dir`.

---

## 5. File Summary

| Action | File / location |
|--------|------------------|
| Add trash_dir | `core/storage_paths.py` (StoragePaths, resolve, ensure) |
| Helpers | `core/trash_utils.py` (or inside project_deletion.py) |
| Refactor delete + new internal commands | `commands/project_deletion.py` (or + `commands/trash_commands.py`) |
| MCP commands | `commands/project_management_mcp_commands.py` |
| Registration | `hooks.py` |
| Config example | `config.json` (optional key `code_analysis.storage.trash_dir`) |
| Docs | `docs/commands/project_management/*.md` |
| Tests | `tests/` (e.g. `test_project_deletion.py`, `test_trash_*.py`) |

---

## 6. Edge Cases

- **Project name with only illegal chars**: fallback to `project_{project_id[:8]}`.
- **Trash dir missing**: create in `ensure_storage_dirs`; before move, `trash_dir.mkdir(parents=True, exist_ok=True)`.
- **Move fails** (e.g. cross-device): fallback to copy + rmtree source, or return error and leave project root in place (DB already cleared).
- **Same second**: `ensure_unique_trash_path` with `_1`, `_2` avoids overwrite.
- **list_trashed_projects**: folders not matching name format can be skipped or returned with `original_name=folder_name`, `deleted_at=null`.

---

## 7. Backward Compatibility

- **Config**: if `trash_dir` is absent, default `data/trash`; no change required in existing configs.
- **delete_project**: behaviour change only when `delete_from_disk=True` (from “permanent delete” to “move to trash”). Clients that relied on permanent delete must use the new “permanently delete from trash” or “clear trash” to achieve the same effect.

---

## 8. Optional Extensions (out of scope for minimal plan)

- **Restore from trash**: new command to move a trashed folder back to a given path and optionally re-register project in DB (complex; can be a follow-up).
- **Version dir in trash**: move `{version_dir}/{project_id}/` into `trash_dir/{trash_folder_name}/versions` so trashed project keeps backups (more code and tests).
- **Retention**: auto-clean trash older than N days (cron or background job).
