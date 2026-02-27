# Technical specification: CST token economy

**Author:** Vasiliy Zdanovskiy  
**email:** <vasilyvz@gmail.com>

---

## 1. Goal and scope

**Goal:** Reduce the number of tokens consumed when the model (or client) works with CST: less data in the response of CST commands, without extra round-trips and **without writing to file and reading back** (that does not save tokens).

**Scope:** In-memory tree and response payload only. No changes to file I/O, no new persistence layer.

**Principle:** Filter and trim what is **returned** to the client. The server still keeps the full tree in memory for `tree_id`; the client receives only what is needed for the current task.

---

## 2. Current state (reference)

### 2.1 Relevant code

- **CST load command** — `code_analysis/commands/cst_load_file_command.py`: `cst_load_file` builds tree, returns `tree_id` + `nodes` (list of node metadata dicts).
- **Tree builder** — `code_analysis/core/cst_tree/tree_builder.py`: `load_file_to_tree`, `_build_tree_index` build full tree and metadata; filters by `node_types`, `max_depth`, `include_children`.
- **Tree models** — `code_analysis/core/cst_tree/models.py`: `TreeNodeMetadata`, `to_dict()` — shape of each node in the response.
- **CSTQuery** — `code_analysis/cst_query/`: `parse_selector`, `query_source(source, selector)` — selector language (steps, combinators, predicates, `Def:*`, etc.).
- **Tree finder** — `code_analysis/core/cst_tree/tree_finder.py`: `find_nodes(tree_id, query, search_type="xpath")` — finds nodes by selector in an existing tree.

### 2.2 Current response size levers

- **`node_types`** — only nodes of these types are included in `metadata_map` and returned (e.g. `["FunctionDef", "ClassDef"]`).
- **`max_depth`** — only nodes with `depth <= max_depth` are included (e.g. `max_depth=1` ≈ top level).
- **`include_children`** — if `false`, `children_ids` are not filled in metadata (smaller payload per node).

The response is always:

```json
{
  "success": true,
  "data": {
    "tree_id": "...",
    "file_path": "...",
    "nodes": [ { "node_id": "...", "type": "...", ... }, ... ],
    "total_nodes": N
  }
}
```

All nodes that pass the filters are returned. For a large file with many functions/classes, `nodes` can be very long and dominate token usage.

### 2.3 What does not help

- **Writing the tree or response to a file and then reading it** does not reduce tokens: the model still has to consume the same data. Economy comes only from **returning less** in the first place.

---

## 3. Requirements

### 3.1 Optional: `node_selector` (CSTQuery)

- **Parameter:** `node_selector: Optional[str]` in `cst_load_file`.
- **Semantics:** After the tree is built (with existing `node_types` / `max_depth` / `include_children`), run the CSTQuery selector **in memory** over the module. Return only metadata for nodes that **match** the selector.
- **Execution:** Use existing `query_source(module.code, node_selector)` (or equivalent over the tree) to get matches; then restrict `nodes` in the response to `tree.metadata_map[node_id]` for those matches. If the current `query_source` returns matches by position/type, map them to `metadata_map` by `(start_line, start_col, end_line, end_col, type)` or by integrating with the tree’s `node_map`/`metadata_map`.
- **Backward compatibility:** If `node_selector` is absent or empty, behaviour unchanged: return all nodes that pass `node_types` / `max_depth` / `include_children`.
- **Examples:**
  - `node_selector="Def:*"` → only FunctionDef and ClassDef (same idea as `node_types=["FunctionDef","ClassDef"]`, but via selector).
  - `node_selector="FunctionDef[name='main']"` → one function.
  - `node_selector="ClassDef > FunctionDef:first"` → first method of each class.

So: **one** load returns a small, targeted list of nodes and `tree_id` for later use (e.g. `cst_find_node`, `cst_modify_tree`), without a second “find” round-trip and without touching the disk.

### 3.2 Optional: `top_level_only`

- **Parameter:** `top_level_only: Optional[bool]` in `cst_load_file` (default `false`).
- **Semantics:** If `true`, return only nodes at depth 1 (direct children of Module). Equivalent to `max_depth=1` but explicit and documented for “only top-level outline”.
- **Implementation:** When `top_level_only=true`, set effective `max_depth=1` (if `max_depth` not provided) or treat as “return only depth 1” regardless of `max_depth`.
- **Backward compatibility:** Default `false` preserves current behaviour.

### 3.3 Optional: `minimal_metadata`

- **Parameter:** `minimal_metadata: Optional[bool]` (default `false`).
- **Semantics:** If `true`, each node in `nodes` contains only: `node_id`, `type`, `kind`, `name`, `qualname`, `start_line`, `end_line` (and optionally `start_col`, `end_col`). Omit `children_ids`, `children_count`, `parent_id` to shrink payload. Useful when the client only needs to choose a node or show an outline.
- **Backward compatibility:** Default `false` keeps current full metadata.

### 3.4 No new round-trips or file I/O

- All filtering and trimming must happen **in memory** on the server before building the response.
- No “save tree to file then read” or “return file path instead of nodes” as a token-saving mechanism; that does not reduce tokens for the consumer.

---

## 4. Implementation notes (current codebase)

### 4.1 `node_selector` in `cst_load_file`

- In `cst_load_file_command.py` `execute()`:
  - After `load_file_to_tree(...)` and before building `nodes = [meta.to_dict() for meta in tree.metadata_map.values()]`:
  - If `node_selector` is present and non-empty:
    - Call CSTQuery over the tree. The existing `tree_finder.find_nodes(tree_id, query=node_selector, search_type="xpath")` works on an already stored tree; alternatively run `query_source(tree.module.code, node_selector)` and map matches to `metadata_map` by position/type (see `tree_finder._find_nodes_xpath` for current matching logic).
    - Build the list of `node_id` that matched.
    - Set `nodes = [tree.metadata_map[nid].to_dict() for nid in matched_ids if nid in tree.metadata_map]` (and optionally keep order of matches).
  - Else: keep current behaviour (all metadata_map values).
- Add `node_selector` to the command schema (optional string).
- Document that when `node_selector` is used, `nodes` may be a subset of what `node_types`/`max_depth` would allow; `tree_id` still refers to the full tree for subsequent commands.

### 4.2 `top_level_only`

- In `execute()`, if `top_level_only is True` and `max_depth is None`, set `max_depth = 1` before calling `load_file_to_tree`. If both are set, either treat `top_level_only` as “at most depth 1” (force max_depth=1) or document that `max_depth` wins. Prefer: `top_level_only` implies effective `max_depth=1`.

### 4.3 `minimal_metadata`

- In `TreeNodeMetadata.to_dict()` (or in the command): add an optional parameter or a separate path that omits `children_ids`, `children_count`, `parent_id` when minimal payload is requested. Command passes `minimal_metadata` through and uses a reduced `to_dict(minimal=True)` or a small helper that builds a minimal dict from metadata.

### 4.4 Tree builder

- No change required for `_build_tree_index` if we filter **after** index build: we still build the full index (or the same as today with node_types/max_depth), then in the command we restrict which metadata entries go into the response. If we want to avoid building metadata for nodes that will be dropped by `node_selector`, we could later optimize by running the selector first and then only building metadata for matched nodes — that is an optional performance improvement, not required for token economy (economy is from response size).

---

## 5. Acceptance criteria

1. **Backward compatibility:** Existing calls without new parameters behave exactly as today.
2. **Token reduction:** For a file with many nodes, a call with `node_selector="Def:*"` or `top_level_only=true` returns fewer nodes (and preferably smaller per-node payload with `minimal_metadata=true`) than a call with no filters.
3. **Same tree_id:** Responses with `node_selector` / `top_level_only` / `minimal_metadata` still return a valid `tree_id` that can be used with `cst_find_node`, `cst_modify_tree`, `cst_save_tree`, etc.
4. **No file write/read:** No new logic that writes the tree or the response to disk for the purpose of “economy”; all filtering is in memory and only the response payload is reduced.
5. **Docs and schema:** Command schema and `docs/commands/cst/cst_load_file.md` updated with the new parameters and short examples (e.g. “load only outline” with `top_level_only=true`, “load only main” with `node_selector="FunctionDef[name='main']"`).

---

## 6. Targeted node access and subtree (one–two commands)

**Goal:** Allow the model to reach the needed node (and its subnodes or only direct children) in one or two commands, without transferring the whole file.

### 6.1 Precise addressing

- **cst_find_node** must support a “single match” mode: when the client needs exactly one node (e.g. by selector), return that node or an explicit error.
- **Parameter:** `require_one: Optional[bool]` (default `false`). If `true`:
  - 0 matches → error `NoMatch` (selector, tree_id).
  - \>1 matches → error `NonUniqueMatch` with a short list of candidates (e.g. node_id, file position, snippet or name) so the client can narrow the selector.
  - 1 match → return that one node as usual (e.g. `nodes: [match]`).
- This gives **one command** to resolve “the node that matches X” and get its `node_id`.

### 6.2 Node + direct children vs full subtree

- **cst_get_node_info** currently returns the node and, if `include_children=true`, only **direct children**.
- **Parameter:** `children_depth: Optional[int]` (default `1`). Meaning:
  - `1` — only direct children (current behaviour).
  - `2` — direct children and their children (two levels).
  - `N` — up to N levels of descendants.
  - `0` or omit for “all” in API: use a separate value (e.g. `-1` or string `"all"`) to mean **full subtree** (all descendants).
- **Return format:** When `children_depth > 1` or “all”, return a **flat** list of descendants (not nested), each with a `depth` (or `level`) field (1 = direct child, 2 = grandchild, …). This keeps the response predictable and easy to consume. The existing `children` field can be the first level; add e.g. `descendants` for the flat list when depth \> 1 or “all”.
- So: **one command** (cst_get_node_info with node_id + children_depth=1) gives node + direct children; **same command** with children_depth=2 or “all” gives node + full subtree (flat list with depth).

### 6.3 One- vs two-command flows

- **Two commands (current + new params):**
  1. `cst_find_node(tree_id, query="FunctionDef[name='main']", require_one=true)` → single node_id.
  2. `cst_get_node_info(tree_id, node_id, include_children=true, children_depth=1)` → node + direct children; or `children_depth=-1` for full subtree.
- **One command (optional convenience):** A single command that takes `tree_id` + selector (must match one node) + `children_depth`, and returns that node + its descendants (direct only or subtree). This can be implemented as a thin wrapper: resolve selector with require_one, then call get_node_info with children_depth. If added, name e.g. `cst_get_node_by_selector`; same response shape as get_node_info (node + children/descendants).

### 6.4 Implementation points

- **tree_metadata.py:** Add `get_node_descendants(tree_id, node_id, max_depth: int = 1, include_code: bool = False) -> List[Tuple[TreeNodeMetadata, int]]` (or list of dicts with `depth`). Recursively collect from `metadata.children_ids` up to `max_depth`; when `max_depth <= 0` treat as “no limit”.
- **cst_get_node_info_command.py:** Add `children_depth` (default 1). When `include_children` is true and `children_depth > 1` (or “all”), call `get_node_descendants` and return `descendants` (flat list with depth). When `children_depth == 1`, keep current behaviour (direct children in `children`).
- **cst_find_node_command.py:** Add `require_one`. After `find_nodes`, if `require_one` and `len(matches) != 1`, return ErrorResult with code `NoMatch` or `NonUniqueMatch` and details (e.g. candidate node_ids and positions). Otherwise return the single node or list as today.

### 6.5 Acceptance (targeted access)

1. With `require_one=true`, cst_find_node returns exactly one node or a clear error with candidates.
2. With `children_depth=1`, cst_get_node_info returns the node and its direct children (unchanged).
3. With `children_depth=2` (or `"all"`), cst_get_node_info returns the node and a flat list of descendants with a depth/level field.
4. The combined flow “find one node by selector + get its subtree” is achievable in two commands (find with require_one, then get_node_info with children_depth).

### 6.6 Reserved service identifier for root

- **Name:** `__root__` (reserved value for `node_id`).
- **Meaning:** Denotes the Module (root) node of the tree. Any command that accepts `node_id` (e.g. `cst_get_node_info`, `cst_modify_tree`) must resolve `__root__` to the actual root `node_id` for the given `tree_id` before lookup.
- **Rules:**
  - The value `__root__` is reserved and must not be used as a real node identifier in responses.
  - When `node_id == "__root__"`, the server substitutes the stored root node id for that tree (set at index build time). The root (Module) is always indexed so that `__root__` resolves even when `node_types` / `max_depth` filter other nodes.
- **Benefit:** One command to get the top-level outline: `cst_get_node_info(tree_id, node_id="__root__", include_children=True, children_depth=1)` without a prior `cst_find_node` for Module.

---

## 7. Out of scope (this spec)

- Selector language extensions (`:has`, `:not`, etc.) — separate spec.
- Two-phase apply, transactions, ops protocol — separate spec.
- Storing or querying the tree from a database (SQL/closure) — separate spec.
- Any change that “saves tokens” by writing to file and reading later — explicitly not in scope.

---

## 8. Summary

- **node_selector** — return only nodes matching CSTQuery → fewer nodes in `nodes`.
- **top_level_only** — return only top-level nodes → fewer nodes (same as max_depth=1).
- **minimal_metadata** — omit children/parent in each node → smaller payload per node.
- **Reserved node_id** — `__root__` always refers to the Module (root) node of the tree; no search step needed to get the root.

All processing stays in memory; the only change is **what is put into the response**. Writing to file and reading back does not reduce token usage and is not part of this spec.
