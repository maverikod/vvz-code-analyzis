# CST paradigm fixes: root cause and tasks

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Purpose:** Two fixes: (1) query_cst must return UUID in `matches[].node_id`; (2) cst_find_node with `search_type=simple` must not return all nodes when the client sends a query string.

---

## 1. query_cst: synthetic node_id instead of UUID (paradigm violation)

**Observed:** File-based `query_cst` returns `matches[].node_id` in the form `function:main:FunctionDef:145:0-161:62` (span-based/synthetic), while tree-based commands (cst_load_file, cst_find_node, cst_get_node_info) use UUIDs. Same node must have one identity: UUID.

**Root cause:** In `code_analysis/commands/query_cst_command.py`, `query_source()` is called with only `source` and `selector`; `node_ids_by_exact_key` is not passed. In `code_analysis/cst_query/executor.py`, when `node_ids_by_exact_key` is None, `build_index` leaves `node_id` empty from that map, and `Match.node_id` is set from `info.node_id or _legacy_node_id(info)` — so the legacy span-based id is used. The tree (and thus UUIDs) is never loaded for the file in query_cst.

**Required fix:** When running the selector in query_cst (query-only path), build the CST tree for that file (same source), obtain `metadata_map`, build `node_ids_by_exact_key = build_exact_key_to_id_from_metadata(metadata_map)` (from `code_analysis/core/cst_tree/node_id_markers`), and call `query_source(source, selector_for_query, include_code=include_code, node_ids_by_exact_key=node_ids_by_exact_key)`. Then `matches[].node_id` will be UUID. Use `create_tree_from_code` (or equivalent) from `code_analysis/core/cst_tree/tree_builder.py` to get a tree from `source`; then pass the exact_key map into `query_source`. Do not persist the tree in global _trees if that would change semantics (or use a throwaway tree / helper that only builds the map).

**Task for executor:** See `steps/step_01_query_cst_return_uuid.md`.

---

## 2. cst_find_node simple: returns all nodes instead of filtering by query

**Observed:** With `search_type=simple` and `query="function[name='main']"`, the server returns thousands of nodes (entire tree) instead of one FunctionDef named `main`.

**Root cause:** In `code_analysis/core/cst_tree/tree_finder.py`, `find_nodes()` for `search_type="simple"` calls `_find_nodes_simple(tree, node_type, name, qualname, start_line, end_line)`. The **`query` parameter is never used** in the simple path. So when the client sends only `query=function[name='main']` and `search_type=simple` (and does not send `node_type=FunctionDef`, `name=main`), all of node_type, name, qualname, start_line, end_line are None. In `_find_nodes_simple`, the filters are applied as:

- `if node_type and metadata.type != node_type: continue`
- `if name and metadata.name != name: continue`
- …

When all are None, no `continue` is ever executed, so **every node in tree.metadata_map is appended** to the result. Hence the “all nodes” behavior.

**Required fix:** When `search_type=simple` and `query` is provided but the explicit filters (node_type, name, qualname, start_line, end_line) are not set, either:

- **Option A:** Parse the query string to extract node_type and name (e.g. `function[name='main']` → node_type=FunctionDef, name=main) and pass them to `_find_nodes_simple`; or  
- **Option B:** Delegate to the xpath path: if `search_type=simple` and `query` is set and no other filters are provided, call `_find_nodes_xpath(tree, query)` so behavior is consistent with xpath.

Option B is minimal and preserves a single semantics for selector strings. Option A requires a small parser for the “simple” selector form.

**Task for executor:** See `steps/step_02_cst_find_node_simple_respect_query.md`.
