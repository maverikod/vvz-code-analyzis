# Search Capabilities and CST Node Types — Code Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes the project’s search capabilities (with emphasis on AST and CST) and the CST node type system used for queries and tree operations.

---

## 1. Search capabilities — overview

| Type | Command | Input | Backend | Use case |
|------|---------|--------|---------|----------|
| **Full-text (FTS5)** | `fulltext_search` | query, project_id | SQLite FTS5 `code_content_fts` | Find text in code and docstrings |
| **Semantic (vectors)** | `semantic_search` | query, project_id, limit | Embedding service + FAISS | Find conceptually similar code |
| **AST by type** | `search_ast_nodes` | project_id, node_type, file_path?, limit? | DB: classes, functions, methods | Find classes/functions/methods by type |
| **Classes by name** | `find_classes` | project_id, pattern? | DB search_classes (SQL LIKE) | List/filter classes by name |
| **Methods of class** | `list_class_methods` | project_id, class_name | DB: get_class_methods | List methods of a class |
| **Entity lookup** | `get_code_entity_info` | project_id, name, type | DB entities | One entity by name/type |
| **List entities** | `list_code_entities` | project_id, type? | DB entities | List entities (optional type filter) |
| **Usages** | `find_usages` | project_id, target_name | usages table | Where an entity is used |
| **Dependencies** | `find_dependencies` | project_id, entity_name | usages + imports | What an entity depends on |
| **CST in tree** | `cst_find_node` | tree_id, query (or simple filters) | In-memory CST tree + CSTQuery | Find nodes in loaded CST tree |
| **CST in file** | `query_cst` | project_id/root_dir, file_path, selector | LibCST parse + CSTQuery | Find nodes in file by selector |

Sources: `docs/SEARCH_TYPES.md`, `code_analysis/commands/`, `code_analysis/core/`.

---

## 2. AST search in detail

### 2.1 Command: `search_ast_nodes`

- **Source:** `code_analysis/commands/ast/search_nodes.py` → `SearchASTNodesMCPCommand`
- **Backend:** Database tables `classes`, `functions`, `methods`, `files` (by `project_id`). Data is filled by code mapper / `update_indexes`.
- **Parameters:**
  - `project_id` (required)
  - `node_type` (optional): `ClassDef`, `FunctionDef`, or aliases `class`, `function`, `method`
  - `file_path` (optional): limit search to one file (relative to project root)
  - `limit` (default 100): max number of results
- **Returns:** List of nodes with `node_type`, `name`, `file_path`, `line`, `docstring`; for methods also `class_name`.
- **Behaviour:** Maps `node_type` to DB tables: `ClassDef`/`class` → `classes`; `FunctionDef`/`function` → top-level `functions`; `method` → `methods`. No full AST parse at query time; results come from pre-indexed entities.

### 2.2 Related AST commands

- **get_code_entity_info** — one entity by name/type/path (`commands/ast/entity_info.py`).
- **list_code_entities** — list entities with optional type filter (`commands/ast/list_entities.py`).
- **find_usages** — where `target_name` is used (`commands/ast/usages.py`).
- **find_dependencies** — what `entity_name` depends on (`commands/ast/dependencies.py`).

AST data comes from the same DB entities (classes, functions, methods) populated by indexing.

---

## 3. CST search in detail

CST search works at the level of LibCST trees: full syntax tree with formatting and comments. There are two entry points: in-memory tree (after load) and direct file query.

### 3.1 CST search in memory: `cst_find_node`

- **Source:** `code_analysis/commands/cst_find_node_command.py` → `CSTFindNodeCommand`
- **Requires:** A CST tree already loaded with `cst_load_file` (returns `tree_id`).
- **Parameters:**
  - `tree_id` (required)
  - `search_type`: `"simple"` or `"xpath"` (default `"xpath"`).
  - For **simple**: optional `node_type`, `name`, `qualname`, `start_line`, `end_line` (combined with AND).
  - For **xpath**: `query` (required) — CSTQuery selector string.
- **Implementation:** `code_analysis/core/cst_tree/tree_finder.py` → `find_nodes()`. XPath mode uses `query_source(source, selector)` from `cst_query.executor` on the tree’s module code; results are matched to `TreeNodeMetadata` by `node_id` or by position/type.
- **Returns:** Node metadata (e.g. `node_id`, type, kind, name, qualname, line/col). Use `node_id` with `cst_modify_tree`, `cst_get_node_info`, etc.

### 3.2 CST search in file: `query_cst`

- **Source:** `code_analysis/commands/query_cst_command.py` → `QueryCSTCommand`
- **Parameters:** `project_id` or `root_dir`, `file_path`, `selector` (CSTQuery), optional `include_code`, `max_results`.
- **Implementation:** Resolves file path, reads source, parses with LibCST, runs `query_source(source, selector, include_code=...)` from `code_analysis/cst_query/executor.py`. No need to load tree into memory first.
- **Returns:** List of matches: `node_id`, `kind`, `type` (LibCST type), `name`, `qualname`, `start_line`, `start_col`, `end_line`, `end_col`, and optionally `code`. `node_id` is stable enough for `compose_cst_module` (selector kind `node_id` or `cst_query`).

### 3.3 CSTQuery selector syntax (CST / XPath-like)

Used by both `cst_find_node` (xpath) and `query_cst`.

- **Steps:** Each step is a **TYPE** (or `*`) with optional predicates and pseudos.
- **Combinators:**
  - Space: descendant (B anywhere under A).
  - `>`: direct child (B immediate child of A).
- **Predicates:** `[attr OP value]`
  - Operators: `=`, `!=`, `~=` (substring), `^=` (prefix), `$=` (suffix).
  - Attributes: `type`, `kind`, `name`, `qualname`, `start_line`, `end_line`.
- **Pseudos:** `:first`, `:last`, `:nth(N)`.

Examples:

- `class[name="MyClass"]` — class with exact name.
- `class[name^="Base"]` — class name prefix.
- `function[name="f"] smallstmt[type="Return"]:first` — first return in function `f`.
- `class > function` — functions that are direct children of a class (e.g. methods).

Grammar and parser: `code_analysis/cst_query/parser.py` (Lark). Query AST: `code_analysis/cst_query/ast.py` (Query, SelectorStep, Predicate, Pseudo, Combinator).

---

## 4. CST node types and kinds

The project uses two parallel classifications for CST nodes:

1. **Type (`type` / `node_type`)** — LibCST class name of the node (e.g. `Module`, `ClassDef`, `FunctionDef`, `If`, `Return`). Any node in the LibCST tree has such a type (it is `node.__class__.__name__`).
2. **Kind (`kind`)** — Project-defined semantic role used for filtering and aliases in selectors. Computed in `tree_builder._get_node_kind()` and `cst_query/executor._node_kind()`.

### 4.1 Kind taxonomy (project-defined)

| Kind | Condition (LibCST) | Meaning |
|------|--------------------|--------|
| `class` | `isinstance(node, cst.ClassDef)` | Class definition |
| `function` | `isinstance(node, cst.FunctionDef)` and not inside a class | Top-level function |
| `method` | `isinstance(node, cst.FunctionDef)` and inside a class | Method |
| `import` | `isinstance(node, (cst.Import, cst.ImportFrom))` | Import / import from |
| `smallstmt` | `isinstance(node, cst.BaseSmallStatement)` | Small statement (e.g. return, assign, expr) |
| `stmt` | `isinstance(node, cst.BaseStatement)` | Statement (compound or small) |
| `node` | Otherwise | Any other CST node |

References: `code_analysis/core/cst_tree/tree_builder.py` (`_get_node_kind`), `code_analysis/cst_query/executor.py` (`_node_kind`).

### 4.2 TYPE aliases in CSTQuery (selector steps)

In selectors, the step TYPE can be:

- **Aliases (matched by `kind`):** `module`, `class`, `function`, `method`, `stmt`, `smallstmt`, `import`, `node`.
- **LibCST class names:** Any concrete node type, e.g. `Module`, `ClassDef`, `FunctionDef`, `If`, `For`, `While`, `With`, `Try`, `Return`, `Assign`, `Expr`, `Call`, `Import`, `ImportFrom`, etc.

Matching logic: `code_analysis/cst_query/executor.py` → `_matches_node_type()`. If the step TYPE is one of the aliases (case-insensitive), the node’s `kind` must equal that alias; otherwise the step TYPE is compared to the node’s LibCST type (`node_type`).

Note: `module` matches the root module node (kind is not set to `"module"` in the current `_get_node_kind` for the module itself; the executor’s index includes the module and its `node_type` is `Module`. The alias `module` is accepted in the selector; if the index assigns a specific kind to the Module node, that would be used. In the executor, the root is visited and gets a kind from `_node_kind` — for `cst.Module` the default is `"node"`. So in practice, selecting by type `Module` is more reliable than the alias `module` for the root.)

### 4.3 LibCST node types (representative list)

The **type** of a node is always the LibCST class name. The tree indexes every node (see `_build_index` in tree_builder and executor). Representative types encountered in Python code:

- **Module-level:** `Module`
- **Definitions:** `ClassDef`, `FunctionDef`
- **Statements (compound):** `If`, `For`, `While`, `With`, `Try`, `Match`
- **Statements (small):** `Return`, `Raise`, `Assert`, `Assign`, `AnnAssign`, `AugAssign`, `Expr`, `Pass`, `Break`, `Continue`, `Global`, `Nonlocal`, `Import`, `ImportFrom`
- **Expressions / other:** `Call`, `Name`, `Attribute`, `Subscript`, `Lambda`, `List`, `Dict`, `Set`, `Tuple`, `UnaryOperation`, `BinaryOperation`, `Comparison`, `IfExp`, `ListComp`, `DictComp`, `SetComp`, `GeneratorExp`, etc.

The exact set of types is defined by LibCST; the project does not restrict which types can appear. Metadata and selectors use `type` (LibCST name) and `kind` (project taxonomy) as above.

### 4.4 Node metadata (TreeNodeMetadata / Match)

For each node the project exposes (e.g. in `cst_find_node` results or `query_cst` matches):

- **node_id** — Stable identifier (format: `kind:qualname:type:start_line:start_col-end_line:end_col`) used for modify/get operations.
- **type** — LibCST node type.
- **kind** — One of: class, function, method, import, smallstmt, stmt, node.
- **name** — For ClassDef/FunctionDef/Name: the name string.
- **qualname** — Qualified name (e.g. `ClassName.method_name` for methods).
- **start_line, start_col, end_line, end_col** — Position (1-based line, 0-based column).
- **children_count / children_ids / parent_id** — Only in tree metadata (e.g. from `cst_load_file`), not in `query_cst` Match.
- **code** — Optional snippet when requested (`include_code` or equivalent).

---

## 5. Tool effectiveness and token economy

This section evaluates search and editing tools in terms of **effectiveness** (how well they target the needed data) and **token economy** (how much input/output they consume). Use it to choose workflows that save tokens and reduce round-trips.

### 5.1 Search: token impact and recommendations

| Command | Default limit / size | Response size (typical) | Token cost | Recommendations |
|--------|----------------------|--------------------------|------------|------------------|
| **fulltext_search** | limit=20 | 20 × (content + docstring + path); content can be long | **High** if content/docstrings are large | Use small `limit` (5–20) for discovery; narrow by `entity_type` |
| **semantic_search** | limit=10 | 10 × chunk text | **Medium–high** | Use `limit` 5–10 unless you need more |
| **search_ast_nodes** | limit=100 | name, file_path, line, docstring per node; docstrings can be long | **Medium** | Set `file_path` to one file when possible; use `limit` 20–50 |
| **find_classes** / **list_class_methods** | no limit | List of metadata (name, path, line, docstring) | **Low–medium** | Use `pattern` in find_classes to avoid huge lists |
| **get_code_entity_info** / **list_code_entities** | one / list | One entity or filtered list | **Low** | Prefer over scanning many results when you know name/type |
| **query_cst** | max_results=200, include_code=**False** | Only node_id, kind, type, name, qualname, positions | **Low** (without code) | Keep `include_code=False`; set `max_results` 10–50 for discovery |
| **query_cst** with include_code=True | max_results=200 | Same + **code snippet per match** | **High** | Use only when you need 1–2 snippets; avoid for many matches |
| **cst_load_file** | all nodes | **All** node metadata (no source code); 1 entry per CST node in file | **High** for large files | Use `node_types` and `max_depth` to trim; or avoid load and use `query_cst` to find in file |
| **cst_find_node** | matches only | Only matching nodes’ metadata (no code) | **Low** | Prefer specific selectors so few matches returned |

**Token savings from search:**

- **Targeted search instead of reading many files:** One `fulltext_search` or `search_ast_nodes` returns only matching locations; then read or query only the needed file/range. Saves tokens vs. opening 5–10 files.
- **query_cst without code:** Get `node_id` and positions only; then fetch one node’s code via `cst_get_node_info` or use `node_id` in modify. Saves vs. returning code for all matches.
- **search_ast_nodes + file_path:** Restrict to one file so the result set is smaller.
- **Entity lookup when name is known:** `get_code_entity_info(project_id, name, type)` returns one entity; cheaper than scanning `list_code_entities` or large search results.

### 5.2 Editing: token impact and round-trips

**Tree-based workflow** (load → find → optional info → modify → save):

| Step | Command | Response / payload | Token cost |
|------|----------|---------------------|------------|
| 1 | cst_load_file | tree_id + **all** node metadata (no code) | **High** for large files (hundreds of small dicts) |
| 2 | cst_find_node | List of matching nodes (metadata only) | Low |
| 3 | cst_get_node_info (optional) | One node; optional code, children | **Medium** if include_code=True or many children |
| 4 | cst_modify_tree (preview=True) | **Full unified diff** (original vs modified file) | **High** for long files |
| 5 | cst_modify_tree (preview=False) or cst_save_tree | Small (success, tree_id / file_path) | Low |

- **Round-trips:** 4–6 (load, find, optional get_info, modify preview, modify apply, save).
- **Main cost:** `cst_load_file` (all nodes) and `cst_modify_tree` preview (full diff). Use `node_types` and `max_depth` in `cst_load_file` to reduce metadata; skip preview when the edit is trivial.

**File-based discovery + tree modify:**

- **list_cst_blocks:** Returns only block id, kind, qualname, start_line, end_line. **Compact**, good for choosing where to edit.
- **query_cst** (include_code=False, max_results=10–20): Get node_ids for target nodes. **Low** payload. Then use `cst_load_file` + `cst_modify_tree` with those node_ids, or (if supported) a single patch command.

**compose_cst_module** (attach branch):

- **Parameters:** project_id, file_path, tree_id, optional node_id, optional commit_message. No `apply`/`return_diff` in the current implementation; it applies the branch (overwrite or insert after node).
- **Response:** Small (success, file_path, backup_uuid, update_result, git_commit). **Low** token cost.
- **Cost:** You must already have a `tree_id` (e.g. from creating a branch or loading a file and building a “branch” tree). Building that branch may involve load + modify, so total token cost depends on that workflow.

**cst_modify_tree:**

- **Input:** tree_id, list of operations (action, node_id, code/code_lines). Use **code_lines** (array of strings) for multi-line code to avoid large escaped strings.
- **Preview:** When preview=True, response includes full **diff** of the file → high tokens for long files. Use preview only when the change is non-trivial.
- **Apply:** When preview=False, response is small (success, operations_applied, tree_id).

### 5.3 Recommendations for token economy

**Search:**

1. Prefer **narrow queries:** `file_path` for AST search, specific CSTQuery selectors, small `limit` (5–20).
2. Use **query_cst** with **include_code=False** and low **max_results**; request code only for the 1–2 nodes you will edit (e.g. via `cst_get_node_info`).
3. Use **get_code_entity_info** when the entity name is known instead of listing or searching many results.
4. Avoid **cst_load_file** for large files when you only need to find one node: use **query_cst** on the file instead, then load only if you need tree-based multi-edit.

**Editing:**

1. For **one or two edits in one file:** Prefer **query_cst** (no code) → get node_ids → **cst_load_file** (with `node_types`/`max_depth` if file is large) → **cst_find_node** or use node_ids → **cst_modify_tree** (skip preview for small edits) → **cst_save_tree**. Optionally skip load and use **cst_get_node_by_range** if you know line range.
2. Use **code_lines** (array) in **cst_modify_tree** for multi-line code to keep request compact and avoid escaping.
3. Use **cst_modify_tree** preview only when you need to verify a large or risky change; for small fixes, apply without preview to avoid a full-file diff in the response.
4. When exploring structure, **list_cst_blocks** is cheap; use it before loading the full tree when you only need block-level targets.

**Summary:** The largest token consumers are (1) **cst_load_file** returning all node metadata for big files, (2) **query_cst** or **fulltext_search** with large result sets or with **include_code**/content, and (3) **cst_modify_tree** preview returning a full-file diff. Tightening limits, avoiding code in bulk results, and using targeted entity/search + single-node code fetch keeps token usage down while keeping search and editing effective.

---

## 6. Summary

- **Search:** Full-text (FTS5), semantic (vectors), AST (DB entities by type), and CST (in-memory tree or file via CSTQuery). AST search is index-based (classes/functions/methods); CST search is tree-based (LibCST + CSTQuery).
- **CST search:** Use `cst_find_node` on a loaded tree (simple filters or XPath-like `query`) or `query_cst` on a file with a `selector`. Both use the same CSTQuery syntax and same kind/type model.
- **CST node types:** Every node has a **type** (LibCST class name). The project also assigns a **kind** (class, function, method, import, smallstmt, stmt, node). Selectors can use kind aliases or LibCST type names, with predicates and pseudos for precise targeting.
- **Effectiveness and tokens:** Prefer targeted search (limits, file_path, include_code=False), entity lookup when name is known, and compact editing workflows (query_cst → node_id → modify; avoid full-tree load and full-file diff when possible). See §5 for details.

For a quick reference of all search commands and when to use them, see `docs/SEARCH_TYPES.md`. For CST command usage and workflows, see `docs/commands/cst/`.
