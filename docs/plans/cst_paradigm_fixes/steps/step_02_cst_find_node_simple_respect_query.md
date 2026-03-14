# Step 02: cst_find_node simple — respect query when provided

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Context:** [../ROOT_CAUSE_AND_TASKS.md](../ROOT_CAUSE_AND_TASKS.md) (section 2)

---

## Executor role

Implementer: fix `cst_find_node` so that when `search_type=simple` and the client sends a `query` (e.g. `function[name='main']`), the server returns **only nodes matching that selector**, not the entire tree. Root cause: in the simple path, `query` is ignored and only `node_type`, `name`, `qualname`, `start_line`, `end_line` are used; when none are set, every node passes the filter.

---

## Execution directive

- Execute only this step. Do not change step 01 or other files except as required by this step.
- Read every file listed in "Read first" before writing code.
- All commands (black, flake8, mypy, tests) from **project root**.
- Mandatory validation: run black, flake8, mypy on modified files; run any existing tests for cst_find_node or tree_finder.

---

## Step scope

- **Target:** `code_analysis/core/cst_tree/tree_finder.py` (function `find_nodes` and possibly `_find_nodes_simple`).
- **Change:** When `search_type == "simple"` and `query` is provided (non-empty string), delegate to the same logic as xpath: call `_find_nodes_xpath(tree, query)` and return its result. When `search_type == "simple"` and `query` is not provided (or empty), keep current behavior: `_find_nodes_simple(tree, node_type, name, qualname, start_line, end_line)`.
- **Documentation:** In `docs/` (e.g. command doc for cst_find_node or standards), state explicitly: for **search by name/type via selector string** (e.g. `function[name='main']`) use **xpath**; **simple** is for filtering by explicit parameters (node_type, name, qualname, line range). After this fix, passing `query` with `simple` will behave like xpath for that query.

---

## Dependency contract

- **Prerequisites:** None.
- **Unlocks:** None.
- **Forbidden scope:** Do not change the signature of `find_nodes` or the MCP command schema; only change the branching inside `find_nodes` and optionally add a sentence to docs.

---

## Read first

- `docs/plans/cst_paradigm_fixes/ROOT_CAUSE_AND_TASKS.md` (section 2)
- `code_analysis/core/cst_tree/tree_finder.py` (`find_nodes`, `_find_nodes_simple`, `_find_nodes_xpath`)
- `code_analysis/commands/cst_find_node_command.py` (how `query`, `search_type`, `node_type`, `name` are passed to `find_nodes`)

---

## Expected behavior

- **Before:** `cst_find_node(tree_id, search_type="simple", query="function[name='main']")` returns hundreds/thousands of nodes (entire tree).
- **After:** Same call returns only the node(s) matching the selector (e.g. one `FunctionDef` named `main`), i.e. same as `search_type="xpath"` with the same `query`.

---

## Implementation notes

1. In `find_nodes`, in the branch `search_type == "simple"`: if `query` is not None and `query.strip()`, call `return _find_nodes_xpath(tree, query)`; else keep `return _find_nodes_simple(tree, node_type, name, qualname, start_line, end_line)`.
2. Optionally in the same change: if `search_type == "simple"` and the client sent only `query` without other filters, you may log or document that simple+query is handled via xpath for predictability.
3. Add one sentence to the relevant command doc or standards: for finding by name/type using a selector string, use **xpath**; **simple** is for explicit node_type/name/qualname/line filters (and if query is provided with simple, it is evaluated as xpath).
