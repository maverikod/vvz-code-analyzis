# Analysis: Insert/Replace by XPath-like Template

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Question

Should a command be extended to delegate "insert by template" (XPath-like selector) so that callers can insert or replace code by selector in one step?

## What Already Exists

### 1. XPath/CSTQuery selector usage

| Component | Role |
|-----------|------|
| **cst_query** (`code_analysis/cst_query/`) | jQuery/XPath-like selector engine over LibCST. Used by `query_source(source, selector)`. |
| **XPathFilter** (`core/database_client/objects/xpath_filter.py`) | Wraps a CSTQuery `selector` string + optional filters (node_type, name, qualname, start_line, end_line). Used by RPC handlers for `query_ast`, `query_cst`, `modify_ast`, `modify_cst`. |
| **tree_finder.find_nodes** (`core/cst_tree/tree_finder.py`) | Finds nodes by `search_type="xpath"` (CSTQuery) or `"simple"`. Returns `TreeNodeMetadata` list (with node_id). |
| **cst_find_node** (MCP) | Exposes find_nodes: `search_type="xpath"` + `query` (CSTQuery selector). Returns node_ids. |
| **query_cst** (MCP) | Queries file by CSTQuery selector; returns matches with node_id. Docs say: use with compose_cst_module selector kind `node_id` or `cst_query`. |

So **finding** by XPath-like selector is already available (cst_find_node, query_cst). **Modifying** by selector is only partly exposed.

### 2. Patcher: insert/replace by selector (not exposed to MCP)

In **cst_module**:

- **Selector** (`core/cst_module/models.py`): kinds `module`, `function`, `class`, `method`, `range`, `block_id`, **`node_id`**, **`cst_query`**.
- **ReplaceOp** / **InsertOp**: selector + new_code (+ position for insert: before/after/end).
- **apply_replace_ops** / **apply_insert_ops** (`patcher.py`, `patcher_insert.py`): take source + list of ops; resolve selector (including **cst_query** via `query_source(source, sel.query)`), then replace/insert.

So **insert/replace by XPath-like template (CSTQuery)** is already implemented in the patcher (selector kind `cst_query` + `match_index`). But **no MCP command** calls these functions. They are only used inside the cst_module package.

### 3. Current MCP commands

| Command | Selector / target | Insert/replace |
|---------|-------------------|----------------|
| **compose_cst_module** | `tree_id` + optional `node_id` | Inserts branch after one node or overwrites file. Does **not** accept a list of ops with selectors; does **not** use apply_replace_ops/apply_insert_ops. |
| **cst_modify_tree** | `tree_id` + operations: each has **node_id** (and code/code_lines) | Replace/insert/delete by **node_id** only. No selector. Workflow: cst_find_node(xpath) → then cst_modify_tree(node_ids). |
| **query_cst** | selector (CSTQuery) | Read-only: returns matches. |
| **cst_find_node** | query (CSTQuery when search_type=xpath) | Read-only: returns node_ids for use in cst_modify_tree. |

So today:

- **By selector (XPath-like)**: only **find** is exposed (query_cst, cst_find_node). **Insert/replace by selector** exists in the patcher but is **not** exposed to MCP.
- **By node_id**: **modify** is exposed (cst_modify_tree, compose_cst_module with node_id).

## Gap

- There is no single MCP command that accepts a **selector (CSTQuery/XPath-like)** and performs **insert** or **replace** in one call.
- The patcher already supports this (Selector kind `cst_query`, apply_replace_ops, apply_insert_ops) but is not wired to any MCP command.

## Recommendation

**Yes, it makes sense to expose “insert/replace by XPath-like template”** by delegating to the existing patcher.

Two concrete options:

### Option A: New MCP command `patch_cst_module` (or `compose_cst_patches`)

- **Input**: `project_id`, `file_path`, list of **ops**, each op:
  - selector: `{ "kind": "cst_query", "query": "class[name='MyClass']", "match_index": 0 }` or `block_id`, `node_id`, `function`/`class`/`method` + name, or `range` + lines.
  - `new_code` (or code_lines).
  - For insert: `position`: "before" | "after" | "end".
- **Implementation**: Read file → build `ReplaceOp`/`InsertOp` with existing `Selector` → call `apply_replace_ops` / `apply_insert_ops` → validate → write + DB update (reuse compose_cst_module’s backup/transaction/validation flow).
- **Effect**: One call = “patch this file by these selector-based ops”. No separate cst_find_node + cst_modify_tree.

### Option B: Extend `compose_cst_module` with optional `ops`

- Add optional parameter `ops`: list of `{ "action": "replace"|"insert", "selector": { "kind": "cst_query", "query": "..." }, "new_code": "...", "position": "after" }`.
- If `ops` is present (and non-empty), ignore `tree_id`/`node_id` for “generate source” and instead: read file → apply_replace_ops/apply_insert_ops(ops) → then same validation and DB flow as now.
- **Effect**: One command handles both “attach branch to node” (current behaviour) and “patch by selector template”.

Recommendation: **Option A** keeps compose_cst_module’s contract (tree_id + optional node_id) simple and avoids overloading it. A dedicated **patch_cst_module** (or **compose_cst_patches**) clearly means “patch by selector template” and reuses the same patcher and validation/DB logic.

## Summary

- **XPath-like (CSTQuery)**: already used for **finding** (cst_find_node, query_cst) and for **modify** in RPC (modify_ast/modify_cst with XPathFilter).  
- **Insert/replace by selector** (including CSTQuery) is already implemented in **cst_module** (Selector + apply_replace_ops/apply_insert_ops) but **not** exposed to MCP.  
- **Recommendation**: add an MCP command that delegates to the patcher with a list of ops (selector kind `cst_query` and others), so that “insert by XPath-like template” is available in one call.
