# Project Capabilities Analysis and Evaluation

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes the capabilities of the code-analysis project, its architecture, and an evaluation of benefits and disadvantages for adoption.

---

## 1. Project Overview

**code-analysis** is an MCP (Model Context Protocol) server that provides code analysis, refactoring, indexing, and quality tooling for Python projects. It is designed to be called via an MCP Proxy (e.g. from Cursor or other AI-assisted IDEs) and supports mTLS, optional out-of-process database driver, and multiple workers (file watcher, vectorization, repair).

---

## 2. Capabilities by Domain

### 2.1 AST (Abstract Syntax Tree)

| Capability | Command | Purpose |
|------------|---------|---------|
| Get AST | `get_ast` | Retrieve AST for a file |
| Search nodes | `search_ast_nodes` | Find nodes by selector |
| Statistics | `ast_statistics` | AST-level statistics |
| List files | `list_project_files` | List project files |
| Entity info | `get_code_entity_info` | Info for a code entity |
| List entities | `list_code_entities` | List entities (classes, functions) |
| Imports | `get_imports` | Import graph |
| Dependencies | `find_dependencies` | Dependency analysis |
| Class hierarchy | `get_class_hierarchy` | Inheritance tree |
| Usages | `find_usages` | Where symbol is used |
| Export graph | `export_graph` | Export dependency graph |

**Use cases:** Navigation, dependency analysis, refactoring planning, documentation generation.

---

### 2.2 CST (Concrete Syntax Tree)

| Capability | Command | Purpose |
|------------|---------|---------|
| Load file | `cst_load_file` | Load Python file as CST tree (in-memory) |
| Save tree | `cst_save_tree` | Save modified tree to file (atomic, optional backup) |
| Reload tree | `cst_reload_tree` | Reload from disk |
| Find node | `cst_find_node` | Find nodes (simple/xpath) |
| Node info | `cst_get_node_info` | Inspect node |
| Node by range | `cst_get_node_by_range` | Get node by line range |
| Modify tree | `cst_modify_tree` | Replace/insert/delete nodes |
| Compose module | `compose_cst_module` | Patch-based edits (selector + new_code) |
| Create file | `cst_create_file` | Create new .py file from CST |
| Convert and save | `cst_convert_and_save` | Convert and persist |
| List blocks | `list_cst_blocks` | List blocks with stable IDs |
| Query CST | `query_cst` | Query by selector |

**Use cases:** Programmatic editing of Python code (e.g. by AI), safe multi-edit workflows, creation of new files via server only (test_data workflow).

---

### 2.3 Analysis

| Capability | Command | Purpose |
|------------|---------|---------|
| Complexity | `analyze_complexity` | Cyclomatic/complexity metrics |
| Duplicates | `find_duplicates` | Structural/semantic duplicate detection |
| Comprehensive | `comprehensive_analysis` | Full quality audit (placeholders, stubs, long files, duplicates, flake8, mypy, docstrings) |
| Semantic search | `semantic_search` | Embedding-based search over code chunks (FAISS) |

**Use cases:** Quality audits, technical debt detection, semantic “find similar code”.

---

### 2.4 Code Quality

| Capability | Command | Purpose |
|------------|---------|---------|
| Format | `format_code` | Black formatting |
| Lint | `lint_code` | Flake8 |
| Type check | `type_check_code` | Mypy |

**Use cases:** Enforcing style and types after edits.

---

### 2.5 Search

| Capability | Command | Purpose |
|------------|---------|---------|
| Fulltext | `fulltext_search` | Text search in code |
| List class methods | `list_class_methods` | Methods of a class |
| Find classes | `find_classes` | Find class definitions |

---

### 2.6 Refactoring

| Capability | Command | Purpose |
|------------|---------|---------|
| Extract superclass | `extract_superclass` | Extract common base class |
| Split class | `split_class` | Split class into multiple |
| Split file to package | `split_file_to_package` | Split module into package |

---

### 2.7 Project and Index Management

| Capability | Command | Purpose |
|------------|---------|---------|
| Create project | `create_project` | Register project (root_dir, watch_dir_id, name) |
| Delete project | `delete_project` | Remove project |
| List projects | `list_projects` | List registered projects |
| Change project ID | `change_project_id` | Change project UUID |
| Delete unwatched | `delete_unwatched_projects` | Remove projects no longer in watch dirs |
| Update indexes | `update_indexes` | Refresh code mapper / AST / chunks / FAISS |
| List long files | `list_long_files` | Files exceeding line threshold |
| List errors by category | `list_errors_by_category` | Errors grouped by category |

---

### 2.8 Backup and File Management

| Capability | Command | Purpose |
|------------|---------|---------|
| List backup files | `list_backup_files` | List backups |
| List backup versions | `list_backup_versions` | Versions for a file |
| Restore backup | `restore_backup_file` | Restore from backup |
| Delete backup | `delete_backup` | Remove backup |
| Clear all backups | `clear_all_backups` | Clear backup set |
| Cleanup deleted files | `cleanup_deleted_files` | DB cleanup for deleted files |
| Unmark deleted file | `unmark_deleted_file` | Unmark as deleted |
| Collapse versions | `collapse_versions` | Version collapse |
| Repair database | `repair_database` | Repair DB state |

---

### 2.9 Database and Workers

| Capability | Command | Purpose |
|------------|---------|---------|
| Corruption status | `get_database_corruption_status` | Check DB integrity |
| Backup database | `backup_database` | Backup DB |
| Repair SQLite | `repair_sqlite_database` | Repair SQLite DB |
| Restore database | `restore_database` | Restore from config |
| Start/stop worker | `start_worker`, `stop_worker` | File watcher, vectorization |
| Worker status | `get_worker_status` | Worker health |
| Database status | `get_database_status` | DB status |
| Repair worker | `start_repair_worker`, `stop_repair_worker`, `repair_worker_status` | Repair worker lifecycle |
| Log viewer | `view_worker_logs`, `list_worker_logs` | Inspect worker logs |

---

### 2.10 Vector Index

| Capability | Command | Purpose |
|------------|---------|---------|
| Rebuild FAISS | `rebuild_faiss` | Rebuild FAISS index from DB chunks |
| Revectorize | `revectorize` | Recompute embeddings and update index |

### 2.11 Database index of methods and objects

**The index of methods and objects lives in the database**, not only in YAML files. SQLite holds the canonical index; code_mapper YAML files are optional exports.

**Table `files`:** There is a **files** table. All references to a file use **file_id** (identifier), not path. Table `files` has: `id` (PRIMARY KEY), `project_id`, `path`, `relative_path`, `lines`, `last_modified`, and other metadata; UNIQUE(project_id, path). Tables `classes`, `functions`, `imports`, `issues`, `usages`, `code_content`, `ast_trees`, `cst_trees`, `code_chunks`, `duplicate_occurrences` reference files via **file_id** (FOREIGN KEY to `files(id)`).

**Identifier types:** Entity ids are **INTEGER** (SQLite AUTOINCREMENT): `files.id`, `classes.id`, `methods.id`, `functions.id`, and all `*_id` foreign keys pointing to them (file_id, class_id, method_id, function_id) are int. Project-level ids are **TEXT (UUID)**: `projects.id`, `watch_dirs.id`, and columns like `project_id`, `watch_dir_id` store UUID strings. `code_chunks.chunk_uuid` is also TEXT (UUID).

| DB structure | Purpose |
|--------------|---------|
| **files** | id, project_id, path, relative_path, lines, last_modified, ... — canonical file registry; all other tables reference by file_id |
| **classes** | id (PK), file_id, name, line, docstring, bases — referenced by methods.class_id, issues.class_id |
| **methods** | id (PK), class_id, name, line, args, docstring, complexity, ... — referenced by issues.method_id, code_chunks.method_id |
| **functions** | id (PK), file_id, name, line, args, docstring, complexity — referenced by issues.function_id |
| **code_content** | file_id, entity_type, entity_id, entity_name, content, docstring (links to class/function/method) |
| **code_content_fts** | FTS5 full-text index on code_content (entity_type, entity_name, content, docstring) |
| **usages** | file_id, line, target_type, target_name, target_class (where each entity is used) |

Indexes: `idx_methods_name`, `idx_methods_class`, `idx_code_content_file`, `idx_code_content_entity`.

| Capability | Command | Purpose |
|------------|---------|---------|
| List entities | `list_code_entities` | List classes, functions, methods in file or project (from DB) |
| Entity info | `get_code_entity_info` | Detailed info for one class/function/method (from DB) |
| List class methods | `list_class_methods` | Methods of a class (uses `methods` + `classes` + `files`) |
| Find classes | `find_classes` | Find class definitions (from DB) |
| Fulltext search | `fulltext_search` | Search in code_content_fts (entity_type, entity_name, content, docstring) |
| Find usages | `find_usages` | Where a method/class/function is used (usages table) |

**code_mapper** (`update_indexes`) populates these DB tables and can also write **method_index.yaml** and **code_map.yaml** under the project for local/script use. The **primary** index for MCP commands is the database; the YAML files are derived.

### 2.12 Cross-reference table (dependencies / dependents)

**Current state:** There is **no** dedicated cross-reference table that links entities by “who depends on whom”.

- **Table `usages`** stores: `file_id`, `line`, `usage_type`, `target_type`, `target_name`, `target_class`. So: “at (file, line) entity X is used”. There is **no** `caller_entity_id` (which method/function contains this line).
- **“Who depends on method M?”** (от метода зависят): answered by `find_usages` / `find_dependencies` — they return **(file_path, line)** where M is used. We do **not** get “list of method_id / function_id that call M”.
- **“What does method M depend on?”** (зависимости метода от): not a single query. We would need: (1) method M’s `file_id` and **line range** (methods table has `line` only, no `end_line`); (2) `SELECT * FROM usages WHERE file_id = ? AND line BETWEEN start AND end`. So it is derivable only by resolving line ranges (e.g. from AST or next entity’s line) and filtering `usages`. The visitor `UsageTracker` knows `_current_class` and `_current_function` when it records a usage, but this **caller** context is not persisted.

**Conclusion:** A **cross-reference table** is needed if we want:

1. **Dependencies of a method** (от чего зависит метод): one query by caller — e.g. “all entities (methods, functions, classes) that this method calls”.
2. **Dependents of a method** (кто зависит от метода): one query by callee — e.g. “all methods/functions that call this method”, by entity id, not only by (file, line).

**Suggested design:**

| Column | Purpose |
|--------|---------|
| `caller_entity_type` | 'class' \| 'function' \| 'method' |
| `caller_entity_id` | id in `classes` / `functions` / `methods` |
| `callee_entity_type` | 'class' \| 'function' \| 'method' |
| `callee_entity_id` | id (or keep target_name/target_class for methods until callee is resolved) |
| `ref_type` | 'call' \| 'import' \| 'inherit' |
| `file_id`, `line` | optional: location of the reference |

Then:

- “What does method M depend on?” → `SELECT * FROM entity_cross_ref WHERE caller_entity_type = 'method' AND caller_entity_id = M.id`
- “What depends on method M?” → `SELECT * FROM entity_cross_ref WHERE callee_entity_type = 'method' AND callee_entity_id = M.id`

**Population:** During `update_indexes` (when AST and entities are available): for each usage, resolve (file_id, line) to the containing function/method/class (using line ranges; methods/functions may need `end_line` or derivation from AST), then insert into the cross-reference table. Optionally keep `usages` for raw (file, line) data and use the new table for entity-to-entity queries.

**Alternative: one table with triple (class_id, method_id, function_id).** A more compact option is a single table where **caller** is represented by three nullable FKs: `caller_class_id`, `caller_method_id`, `caller_function_id`, with a CHECK that exactly one is NOT NULL. Same for **callee**: `callee_class_id`, `callee_method_id`, `callee_function_id` — exactly one NOT NULL. Plus `ref_type`, optional `file_id`, `line`. Then:

- One row = one reference; no separate “entity_type” column; FKs go directly to `classes(id)`, `methods(id)`, `functions(id)`.
- Queries: “what does method M depend on?” → `WHERE caller_method_id = M.id`; “what depends on method M?” → `WHERE callee_method_id = M.id`.
- **Views** can wrap common patterns: e.g. `entity_cross_ref_by_method` (WHERE caller_method_id IS NOT NULL OR callee_method_id IS NOT NULL), or views that join to methods/classes/functions to expose names. **SQLite supports VIEWs** (CREATE VIEW; read-only), so this is a good fit.

This triple-id design avoids type/enum columns and keeps one table; views provide the “by method / by class / by function” slices.

---

## 3. Architecture Highlights

- **MCP server:** All capabilities exposed as MCP tools; callable from Cursor/MCP Proxy.
- **Database:** SQLite as primary store; optional **out-of-process driver** (RPC) for isolation.
- **Workers:** File watcher (change detection, re-indexing), vectorization (embeddings, FAISS), repair worker (maintenance).
- **Security:** mTLS for server and proxy registration; config-driven certificates.
- **Incremental analysis:** Comprehensive analysis can skip unchanged files (mtime-based).
- **Backups:** File-level backups (e.g. before CST save); DB backup/restore.
- **Multi-project:** Watch directories and project registration; per-project FAISS indexes.

---

## 4. Benefits of Application

| Benefit | Description |
|---------|-------------|
| **Single entry point** | One MCP server exposes AST, CST, analysis, quality, search, refactor, backup, and workers. Reduces integration surface for IDEs and automation. |
| **CST-based editing** | Safe, structured edits (load → find → modify → save) with optional backups; supports “edit only via server” policies (e.g. test_data). |
| **Semantic search** | FAISS + embeddings enable “find by meaning,” not only by text; useful for large codebases and AI-assisted workflows. |
| **Comprehensive quality** | One command (comprehensive_analysis) covers placeholders, stubs, long files, duplicates, flake8, mypy, docstrings; good for audits and CI-like checks. |
| **Incremental analysis** | mtime-based skip of unchanged files reduces cost on repeated runs. |
| **Project and index discipline** | Explicit project registration and update_indexes keep indexes (files, AST, chunks, FAISS) consistent. |
| **Operational control** | Database integrity checks, backup/restore, repair worker, log viewer support long-running and recoverable operation. |
| **Extensibility** | Command registry (hooks.py), BaseMCPCommand, and clear separation between commands and core make adding new tools straightforward. |
| **Security and deployment** | mTLS and config-driven registration fit controlled and network-isolated deployments. |

---

## 5. Disadvantages and Risks

| Disadvantage / Risk | Description |
|---------------------|-------------|
| **Operational complexity** | Server, optional DB driver, file watcher, vectorization worker, repair worker, and (external) embedding service increase setup and monitoring burden. |
| **Dependencies** | Requires embedding service for semantic search; FAISS index must be built (update_indexes); flake8/mypy for full comprehensive_analysis. |
| **Python-only** | AST/CST and most analysis are Python-focused; not a multi-language platform. |
| **Latency** | Some commands (comprehensive_analysis, update_indexes, revectorize) are long-running; require queue/status handling. |
| **Resource usage** | SQLite + FAISS + workers consume disk and memory; large repos and many projects increase requirements. |
| **Coupling to project layout** | Expects projectid, config, data/code_analysis.db, watch dirs; strict layout and conventions. |
| **Learning curve** | Many commands and parameters; need to know when to use CST tree vs compose_cst_module, when to run update_indexes, etc. |

---

## 6. Evaluation Summary

- **Best suited for:**  
  Teams using MCP-based IDEs (e.g. Cursor) who want a single server for Python code analysis, structured (CST) editing, semantic search, and quality checks, with control over projects, indexes, and backups.

- **Less suited for:**  
  Quick one-off scripts, non-Python codebases, or environments where minimal operational footprint is required.

- **Adoption recommendation:**  
  Use when the benefits (unified MCP API, CST editing, semantic search, comprehensive analysis, and operational controls) justify the setup and maintenance cost. Pilot on a single project or test_data workflow first; then scale to more projects and optional out-of-process DB and workers.

---

## 7. Token Savings and Refactoring Reliability (Large Projects)

### 7.1 Token savings

| Mechanism | How it reduces tokens | Commands / behaviour |
|-----------|------------------------|----------------------|
| **Semantic search** | Returns only **relevant chunks** (k results), not full files. Each result: `file_path`, `line`, `text` (chunk). No need to load entire codebase into context. | `semantic_search` (k, min_score) |
| **Fulltext search** | Returns **entity-level hits** (entity_type, entity_name, content, docstring, file_path) with limit; no full-file dumps. | `fulltext_search` (limit) |
| **AST without JSON** | `get_ast` can omit full AST JSON: `include_json=False` returns metadata only, cutting large payloads. | `get_ast` (include_json) |
| **CST load with filters** | Tree can be **filtered** so less data is sent: `node_types`, `max_depth`, `include_children=False` reduce size. | `cst_load_file`, `cst_reload_tree` |
| **CST query without code** | `query_cst` has `include_code=False` by default — returns node_id, kind, type, name, qualname, line/col only; code only when needed. | `query_cst` (include_code) |
| **CST node info on demand** | `cst_get_node_info`: `include_code=False`, `include_children=False` by default — code and children only when requested. | `cst_get_node_info` |
| **Pagination** | Usages and list APIs support `limit` and `offset` — client fetches only a window of results. | `find_usages`, fulltext/list commands |
| **Truncation** | `query_cst` has `max_results` and returns `truncated: true` when capped — avoids unbounded payloads. | `query_cst` (max_results) |
| **DB index of methods/objects** | **Primary** index: tables `classes`, `methods`, `functions`, `code_content`, `code_content_fts`. Commands `list_code_entities`, `get_code_entity_info`, `list_class_methods`, `find_classes`, `fulltext_search` use it — lookup without loading full source. | `list_code_entities`, `get_code_entity_info`, `list_class_methods`, `find_classes`, `fulltext_search` |
| **Code mapper YAML** | Optional exports `method_index.yaml`, `code_map.yaml` (from `update_indexes`) for local/script lookup; canonical index is in the DB. | `update_indexes` + local files |

**Summary:** For large projects, the server can return **targeted results** (chunks, entities, node metadata, paginated usages) instead of whole files. The client (e.g. AI) requests code only where needed (`include_code=True` or `cst_get_node_info` for a single node), which reduces tokens compared to “load entire repo” workflows.

### 7.2 Refactoring reliability

| Mechanism | How it improves reliability | Commands / behaviour |
|-----------|-----------------------------|---------------------|
| **Usage and dependency data** | Before refactoring, client can call `find_usages`, `find_dependencies`, `get_class_hierarchy` to know **impact** and avoid broken references. | `find_usages`, `find_dependencies`, `get_class_hierarchy` |
| **Structured edits (CST)** | Edits are **tree-based** (replace/insert/delete by node_id), not raw text patches — preserves syntax and avoids accidental corruption. | `cst_modify_tree`, `compose_cst_module` |
| **Atomic save with backup** | `cst_save_tree` uses **atomic write** and optional **backup**; on failure, previous version is restorable. | `cst_save_tree` (backup, validate) |
| **Validation after save** | Optional **validate** runs checks before/after save; can plug format/lint/type_check into the workflow. | `cst_save_tree`, `format_code`, `lint_code`, `type_check_code` |
| **Refactor commands** | Dedicated **extract_superclass**, **split_class**, **split_file_to_package** use CST/analyzers so structural refactors are consistent. | `extract_superclass`, `split_class`, `split_file_to_package` |
| **Single source of truth** | Project and file metadata (paths, project_id) come from **DB and projectid**; edits are scoped to known projects and paths, reducing path/context mistakes. | Project management, `root_dir`/`project_id` resolution |

**Summary:** For large projects, refactoring is more reliable because: (1) impact is visible via usages/dependencies/hierarchy; (2) edits are structured (CST) and optionally validated; (3) saves are atomic with backup; (4) dedicated refactor commands keep structure consistent; (5) project/path resolution is centralized.

### 7.3 Direct answer: will there be token and reliability gains?

- **Tokens:** **Yes.** By using semantic/fulltext search, filtered CST (node_types, max_depth, include_children), optional code in responses (include_code/include_json), pagination, and code_mapper indices, the client can work with **small, relevant subsets** of the codebase instead of full files or whole repos. That reduces input and output tokens for large projects.

- **Refactoring reliability:** **Yes.** Structured CST edits, atomic save with backup, usage/dependency/hierarchy data before changes, and dedicated refactor commands all reduce the risk of broken references and syntax errors, especially when many files are touched.

The gains are largest when the client (e.g. AI) **follows the intended workflow**: use search and indices to decide what to load, request code only for the nodes being changed, and run find_usages/validation around refactors.

---

## 8. References

- [COMMANDS_INDEX.md](COMMANDS_INDEX.md) — Full command → class → file mapping.
- [COMPONENT_INTERACTION.md](COMPONENT_INTERACTION.md) — Request flow, DB, workers.
- [REGISTRATION_AND_MTLS.md](REGISTRATION_AND_MTLS.md) — Proxy and mTLS setup.
- Per-command docs under `docs/commands/<block>/`.
