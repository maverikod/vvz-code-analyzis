# Plan: Entity Cross-Reference Table (Dependencies and References)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document is an implementation plan for adding a cross-reference table and supporting logic to answer:
- **Dependencies of an entity** (от чего зависит): what a method/function/class calls or uses.
- **References to an entity** (кто зависит от): what methods/functions/classes call or use this entity.

---

## 1. Current State (Summary)

| Component | Current behavior |
|-----------|------------------|
| **usages** table | Stores `file_id`, `line`, `usage_type`, `target_type`, `target_name`, `target_class`, `context`. No caller entity id. |
| **UsageTracker** | AST visitor; knows `_current_class`, `_current_function` at each call site but does not persist caller id. |
| **add_usage** | `database/entities.py` — inserts into `usages`; called from `files.py` during `update_file_data_atomic` after entities are added. |
| **find_dependencies / find_usages** | Query `usages` (and imports/classes.bases); return (file_path, line). No entity-to-entity by id. |
| **methods / functions / classes** | Have `line` (start) only; no `end_line` in DB. |
| **clear_file_data** | Deletes classes, methods, functions, usages, etc. for a file; does not touch a cross-ref table yet. |

To support “dependencies of method M” and “what depends on method M” by entity id we need:
1. A table that links caller entity (class_id | method_id | function_id) to callee entity (class_id | method_id | function_id).
2. Resolving (file_id, line) → caller entity (requires line ranges for methods/functions/classes).
3. Resolving (target_type, target_name, target_class) → callee entity (lookup in classes/methods/functions by project).
4. Populating the table when file data is updated and cleaning it when file data is cleared.

---

## 2. Schema Changes

### 2.1 Add `end_line` to classes, methods, functions

Needed to resolve “which entity contains (file_id, line)” without reparsing AST every time.

- **classes**: `ALTER TABLE classes ADD COLUMN end_line INTEGER;`
- **methods**: `ALTER TABLE methods ADD COLUMN end_line INTEGER;`
- **functions**: `ALTER TABLE functions ADD COLUMN end_line INTEGER;`

Populate during entity extraction in `update_file_data_atomic` from AST: `node.end_lineno` (Python 3.8+). Update `add_class`, `add_method`, `add_function` in `database/entities.py` to accept and store `end_line`. In `database/files.py` where these are called, pass `getattr(node, 'end_lineno', node.lineno)` (and for methods, the method node’s end_lineno).

### 2.2 New table `entity_cross_ref`

One row per reference: caller entity (exactly one of class/method/function) → callee entity (exactly one of class/method/function).

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| id | INTEGER | NOT NULL | PRIMARY KEY AUTOINCREMENT |
| caller_class_id | INTEGER | NULL | FK → classes(id); exactly one of caller_* NOT NULL |
| caller_method_id | INTEGER | NULL | FK → methods(id) |
| caller_function_id | INTEGER | NULL | FK → functions(id) |
| callee_class_id | INTEGER | NULL | FK → classes(id); exactly one of callee_* NOT NULL |
| callee_method_id | INTEGER | NULL | FK → methods(id) |
| callee_function_id | INTEGER | NULL | FK → functions(id) |
| ref_type | TEXT | NOT NULL | 'call', 'instantiation', 'attribute', 'inherit' |
| file_id | INTEGER | NULL | FK → files(id); location of reference |
| line | INTEGER | NULL | Line number of reference |
| created_at | REAL | NULL | Default julianday('now') |

Constraints:

- CHECK: exactly one of (caller_class_id, caller_method_id, caller_function_id) is NOT NULL.
- CHECK: exactly one of (callee_class_id, callee_method_id, callee_function_id) is NOT NULL.
- Foreign keys with ON DELETE CASCADE to classes, methods, functions, files.

Indexes:

- `idx_entity_cross_ref_caller_method` ON (caller_method_id) WHERE caller_method_id IS NOT NULL
- `idx_entity_cross_ref_caller_function` ON (caller_function_id) WHERE caller_function_id IS NOT NULL
- `idx_entity_cross_ref_caller_class` ON (caller_class_id) WHERE caller_class_id IS NOT NULL
- `idx_entity_cross_ref_callee_method` ON (callee_method_id) WHERE callee_method_id IS NOT NULL
- `idx_entity_cross_ref_callee_function` ON (callee_function_id) WHERE callee_function_id IS NOT NULL
- `idx_entity_cross_ref_callee_class` ON (callee_class_id) WHERE callee_class_id IS NOT NULL
- `idx_entity_cross_ref_file` ON (file_id) for cleanup by file.

Optional: VIEWs for “by method” / “by function” / “by class” (e.g. filter WHERE caller_method_id IS NOT NULL OR callee_method_id IS NOT NULL) or JOIN to methods/classes/functions for names; SQLite supports VIEWs.

---

## 3. Code Changes (Order)

### 3.1 Database schema (core/database/base.py)

1. In `_create_tables` (or equivalent init):
   - Add `CREATE TABLE IF NOT EXISTS entity_cross_ref (...)` with CHECK constraints and FKs.
   - Add the indexes above.
2. In `_get_schema_definition()`: add full definition of `entity_cross_ref` (columns, foreign_keys, check_constraints, indexes) so driver/schema sync can create it.
3. Migration:
   - Add `end_line` to `classes`, `methods`, `functions` if not present (e.g. in a new migration step like `_migrate_add_entity_cross_ref()`).
   - Create `entity_cross_ref` table if not exists (idempotent).

### 3.2 Entities and line ranges (core/database/entities.py)

1. **add_class**: add optional parameter `end_line: Optional[int] = None`; extend INSERT to include `end_line` if column exists (or always after migration).
2. **add_method**: same for `end_line`.
3. **add_function**: same for `end_line`.
4. New functions (or new module `database/entity_cross_ref.py`):
   - **add_entity_cross_ref(self, caller_class_id, caller_method_id, caller_function_id, callee_class_id, callee_method_id, callee_function_id, ref_type, file_id=None, line=None)**  
     Validate exactly one caller_* and one callee_*; INSERT into entity_cross_ref; return id.
   - **get_dependencies_by_caller(self, caller_entity_type: str, caller_entity_id: int)**  
     type in ('class','method','function'), id the corresponding id. Query entity_cross_ref by caller_* column; return list of rows (or callee type + id + ref_type, file_id, line).
   - **get_dependents_by_callee(self, callee_entity_type: str, callee_entity_id: int)**  
     Same for callee_*; return list of caller type + id + ref_type, file_id, line.
   - **delete_entity_cross_ref_for_file(self, file_id: int)**  
     Delete all rows where the reference is in this file (file_id = ?) or where caller/callee belongs to this file (caller/callee class/method/function in this file). Implement by: get all class_ids, method_ids, function_ids for file_id; DELETE FROM entity_cross_ref WHERE file_id = ? OR caller_class_id IN (...) OR caller_method_id IN (...) OR caller_function_id IN (...) OR callee_class_id IN (...) OR callee_method_id IN (...) OR callee_function_id IN (...). Use subqueries or a helper that returns these ids.

### 3.3 Resolving caller and callee (core/database or core/)

New module or functions (e.g. `core/entity_cross_ref_builder.py` or inside `database/files.py`):

1. **resolve_caller(db, file_id, line) → Optional[Tuple[str, int]]**  
   Returns (entity_type, entity_id) e.g. ('method', 42). Logic:
   - Load methods for this file (via classes: SELECT m.id, m.line, m.end_line FROM methods m JOIN classes c ON m.class_id = c.id WHERE c.file_id = ?). Find method where line BETWEEN m.line AND m.end_line (handle NULL end_line: treat as line or use a fallback).
   - If not found, load functions for file_id; find function where line BETWEEN f.line AND f.end_line.
   - If not found, load classes for file_id; find class where line BETWEEN c.line AND c.end_line.
   - Return the first match (prefer method over function over class if overlapping; define a clear order, e.g. smallest containing span).

2. **resolve_callee(db, project_id, file_id, line, target_type, target_name, target_class) → Optional[Tuple[str, int]]**  
   Returns (entity_type, entity_id). Logic:
   - **class**: SELECT id FROM classes c JOIN files f ON c.file_id = f.id WHERE f.project_id = ? AND c.name = ?. If multiple, prefer same file_id.
   - **function**: SELECT id FROM functions fn JOIN files f ON fn.file_id = f.id WHERE f.project_id = ? AND fn.name = ?. Prefer same file_id.
   - **method**: SELECT m.id FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE f.project_id = ? AND c.name = ? AND m.name = ?. Prefer same file_id.

If no unique match, return None (do not insert cross_ref for that usage, or document “best effort” and pick first match).

### 3.4 Populating cross-ref in file update (core/database/files.py)

1. In **update_file_data_atomic** (after entities and usages are written):
   - When adding classes/methods/functions, pass `end_line` from AST (`getattr(node, 'end_lineno', node.lineno)` for classes/functions; for methods the method node’s end_lineno).
2. After the existing “Track usages” block (UsageTracker and add_usage):
   - Call a new helper **build_entity_cross_ref_for_file(self, file_id, project_id, source_code)** (or inline steps):
     - Fetch all usages for this file_id from usages table.
     - For each usage row:  
       caller = resolve_caller(self, file_id, row['line'])  
       callee = resolve_callee(self, project_id, file_id, row['line'], row['target_type'], row['target_name'], row['target_class'])  
       If both caller and callee are not None: map caller to (caller_class_id, caller_method_id, caller_function_id) and callee similarly; then add_entity_cross_ref(..., ref_type=row['usage_type']).
   - On failure log and continue; do not fail the whole file update.

3. In **clear_file_data**:
   - Before or after deleting usages, call **delete_entity_cross_ref_for_file(self, file_id)** so that when a file is re-indexed or removed, cross-ref rows for that file and its entities are removed.

### 3.5 Commands and API

1. **Option A – Extend find_dependencies / find_usages**
   - Add optional parameters e.g. `entity_type`, `entity_id`. When both provided, query `entity_cross_ref` instead of (or in addition to) `usages`:
     - “Dependencies of this entity”: get_dependencies_by_caller(entity_type, entity_id).
     - “What depends on this entity”: get_dependents_by_callee(entity_type, entity_id).
   - Return shape can include entity id and type for caller/callee so the client can use them for further calls.

2. **Option B – New MCP commands**
   - **get_entity_dependencies** (root_dir, entity_type, entity_id, project_id?)  
     Returns list of callee entities (type, id, ref_type, file_path, line) that this entity depends on.
   - **get_entity_dependents** (root_dir, entity_type, entity_id, project_id?)  
     Returns list of caller entities (type, id, ref_type, file_path, line) that depend on this entity.

Recommendation: implement Option B for clarity; optionally wire find_dependencies/find_usages to the same backend when entity_id is provided (Option A as a thin wrapper).

### 3.6 Database client (RPC) and driver

- If commands use **DatabaseClient** (out-of-process driver): add RPC handlers and client API for:
  - insert into entity_cross_ref (or a dedicated “add_entity_cross_ref” RPC that accepts the same args as add_entity_cross_ref),
  - get_dependencies_by_caller, get_dependents_by_callee,
  - delete_entity_cross_ref_for_file.
- Driver schema: ensure `entity_cross_ref` and new columns (end_line) are created/synced when the driver starts or schema is synced (via base.py schema definition and driver’s sync_schema/create_table path).

---

## 4. File and Module Checklist

| Task | File / module |
|------|----------------|
| CREATE TABLE entity_cross_ref, indexes, migration for end_line and table | core/database/base.py |
| _get_schema_definition: entity_cross_ref + end_line columns for classes/methods/functions | core/database/base.py |
| add_class/add_method/add_function: end_line param and INSERT | core/database/entities.py |
| add_entity_cross_ref, get_dependencies_by_caller, get_dependents_by_callee, delete_entity_cross_ref_for_file | core/database/entities.py or database/entity_cross_ref.py |
| resolve_caller, resolve_callee | core/database/ (e.g. entity_cross_ref.py) or core/entity_cross_ref_builder.py |
| update_file_data_atomic: pass end_line; call build_entity_cross_ref_for_file after usages | core/database/files.py |
| clear_file_data: call delete_entity_cross_ref_for_file | core/database/files.py |
| New MCP commands get_entity_dependencies, get_entity_dependents | commands/ (e.g. ast/entity_dependencies.py) |
| Register commands | code_analysis/hooks.py |
| Optional: extend find_dependencies/find_usages to accept entity_id and use cross_ref | commands/ast/dependencies.py, commands/ast/usages.py |
| RPC client API and handlers for cross_ref and new methods | database_client/, database_driver_pkg/ (if used) |
| Docs: COMMANDS_INDEX, COMMANDS.md, new .md for get_entity_dependencies, get_entity_dependents | docs/commands/ |

---

## 5. Testing and Backward Compatibility

- **Migration**: Existing DBs must get end_line columns (nullable) and entity_cross_ref table; no breaking change to existing queries. Old rows have end_line NULL; resolve_caller can treat NULL as “unknown” and skip that entity or use line-only containment (line = start_line).
- **Populate**: After migration, run update_indexes (or equivalent) on a project to backfill entity_cross_ref for existing files; no need to backfill end_line for old rows if we allow NULL and document “best effort” for old data.
- **Tests**: Unit tests for resolve_caller, resolve_callee (with mock DB or in-memory SQLite); for add_entity_cross_ref and get_* with a small fixture; integration test that update_file_data_atomic then get_entity_dependencies returns expected rows.

---

## 6. Summary

1. Add **end_line** to classes, methods, functions and populate from AST.
2. Add table **entity_cross_ref** with caller triple (class_id | method_id | function_id), callee triple, ref_type, file_id, line.
3. Implement **resolve_caller(file_id, line)** and **resolve_callee(project_id, file_id, line, target_type, target_name, target_class)** using DB and (for caller) line ranges.
4. After writing usages in **update_file_data_atomic**, **build_entity_cross_ref_for_file** for each usage: resolve caller and callee; insert into entity_cross_ref when both resolved.
5. In **clear_file_data**, **delete_entity_cross_ref_for_file**.
6. Expose **get_entity_dependencies** and **get_entity_dependents** as MCP commands (and optionally extend find_dependencies/find_usages).
7. Add schema and migration in base.py; add client/driver support if commands use RPC.

This yields a single table of entity-to-entity references with optional VIEWs, and direct answers to “dependencies of” and “references to” by entity id.

---

## 7. Implementation Status (2025-01-30)

- **Schema**: `end_line` added to classes, methods, functions; table `entity_cross_ref` and indexes created; migration and `_get_schema_definition` updated.
- **Entities**: `add_class`/`add_method`/`add_function` accept `end_line`; module `entity_cross_ref.py` with `add_entity_cross_ref`, `get_dependencies_by_caller`, `get_dependents_by_callee`, `delete_entity_cross_ref_for_file`.
- **Builder**: `entity_cross_ref_builder.py` with `resolve_caller`, `resolve_callee`, `build_entity_cross_ref_for_file`.
- **Files**: `update_file_data_atomic` passes `end_line`, calls `build_entity_cross_ref_for_file` after usages; `clear_file_data` calls `delete_entity_cross_ref_for_file`.
- **Commands**: `get_entity_dependencies`, `get_entity_dependents` (MCP) in `commands/ast/entity_dependencies.py`, registered in hooks.
- **Docs**: `COMMANDS_INDEX.md` and `COMMANDS_GUIDE.md` updated with get_entity_dependencies, get_entity_dependents; per-command docs in `docs/commands/ast/get_entity_dependencies.md`, `get_entity_dependents.md`; AST block `COMMANDS.md` lists both.
- **RPC**: Commands use `DatabaseClient.execute()` for entity_cross_ref queries; no dedicated RPC handlers required.
- **Tests**: Unit tests in `test_entity_cross_ref.py`, `test_entity_cross_ref_builder.py`; integration in `test_entity_cross_ref_integration.py`. Coverage for entity_cross_ref and entity_cross_ref_builder ~93% (90%+).

**Optional (done):** find_dependencies and find_usages accept optional entity_id; when entity_type (or target_type) and entity_id are provided, they query entity_cross_ref via _get_entity_dependents_via_execute (thin wrapper). Metadata for both commands documents entity_id.

---

## 8. Plan completed (2025-01-30)

All items from sections 1–7 are implemented and tested. Optional follow-ups (not in scope):

- **Backfill**: Run update_indexes (or equivalent) on existing projects to populate entity_cross_ref for already-indexed files; end_line remains nullable for old rows.
- **VIEWs**: Optional SQL VIEWs for filtering by method/function/class can be added later if needed.
